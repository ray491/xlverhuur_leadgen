"""No network or production database: exercise the HTTP lifecycle with fake Exa runs."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['EXA_API_KEY'] = 'test-key'
os.environ['MARKETPOST_FINAL_LEAD_TARGET'] = '100'
os.environ['MARKETPOST_MAX_GENERATION_PASSES'] = '100'
# NullPool creates a new connection each time; use a temporary file for test DB.
import tempfile
_test_db = tempfile.NamedTemporaryFile(suffix='.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + _test_db.name
spec = importlib.util.spec_from_file_location('contact_app', Path(__file__).parents[1] / 'app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def output_run(leads, status='completed'):
    csv_text = module.leads_to_csv(leads).replace('\n', ' ')
    return SimpleNamespace(id='agent_run_test', status=status,
                           output=SimpleNamespace(text=csv_text, structured=None))


def contact(index=0):
    return dict(zip(module.CSV_COLUMNS, [f'Crane {index}', f' Crane {index}@example.com', '', f'Address {index}', '']))


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.client = module.app.test_client()
        with module.app.app_context():
            module.db.session.query(module.Task).delete()
            module.db.session.commit()

    def start(self):
        with patch.object(module, 'create_agent_run', return_value=SimpleNamespace(id='agent_run_test')) as create:
            response = self.client.post('/generate', json={'query': 'kraan verhuur'})
            self.assertEqual(response.status_code, 202)
            create.assert_called_once()
            prompt = create.call_args.args[0]
            self.assertEqual(json.loads(prompt.split('Search request:\n')[1])['maximum_rows'], 30)
            return response.json['task_id']

    def test_single_run_survives_session_restart_and_short_result(self):
        task_id = self.start()
        with module.app.app_context():
            module.db.session.remove()
        with patch.object(module, 'get_agent_run', return_value=output_run([contact()])) as get, patch.object(module, 'create_agent_run') as create:
            result = self.client.get('/status/' + task_id).json
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(len(result['result']['leads']), 1)
            self.assertIn('Required 30', result['error'])
            self.assertEqual(self.client.get('/status/' + task_id).json['status'], 'incomplete')
            get.assert_called_once_with('agent_run_test')
            create.assert_not_called()

    def test_empty_results_are_incomplete(self):
        task_id = self.start()
        with patch.object(module, 'get_agent_run', return_value=output_run([])):
            self.assertEqual(self.client.get('/status/' + task_id).json['status'], 'incomplete')

    def test_running_then_transient_error_then_completed_without_replacement(self):
        task_id = self.start()
        with patch.object(module, 'get_agent_run', side_effect=[output_run([], 'running'), RuntimeError('temporary'), output_run([contact()])]), patch.object(module, 'create_agent_run') as create:
            self.assertEqual(self.client.get('/status/' + task_id).json['status'], 'generating')
            self.assertEqual(self.client.get('/status/' + task_id).status_code, 503)
            self.assertEqual(self.client.get('/status/' + task_id).json['status'], 'incomplete')
            create.assert_not_called()

    def test_failed_and_invalid_output_are_terminal(self):
        for run in [output_run([], 'failed'), SimpleNamespace(status='completed', output=SimpleNamespace(text='invalid CSV', structured=None))]:
            task_id = self.start()
            with patch.object(module, 'get_agent_run', return_value=run):
                result = self.client.get('/status/' + task_id).json
                self.assertEqual(result['status'], 'error')
                self.assertTrue(result['error'])

    def test_new_search_caps_at_30(self):
        task_id = self.start()
        with patch.object(module, 'get_agent_run', return_value=output_run([contact(i) for i in range(35)])):
            result = self.client.get('/status/' + task_id).json
            self.assertEqual(len(result['result']['leads']), 30)
            self.assertEqual(result['status'], 'done')

    def test_legacy_stuck_run_visible_and_recovered_with_all_25_rows(self):
        with module.app.app_context():
            module.db.session.add(module.Task(id='legacy', status='generating', result={
                'progress': {'generation_run_id': 'agent_run_legacy', 'pass_number': 1},
            }))
            module.db.session.commit()
        self.assertIn('legacy', [run['id'] for run in self.client.get('/history').json['runs']])
        with patch.object(module, 'get_agent_run', return_value=output_run([contact(i) for i in range(25)])) as get:
            result = self.client.get('/status/legacy').json
            self.assertEqual(result['status'], 'done')
            self.assertEqual(len(result['result']['leads']), 25)
            get.assert_called_once_with('agent_run_legacy')

    def test_30_rows_with_duplicate_is_incomplete(self):
        task_id = self.start()
        leads = [contact(i) for i in range(29)] + [contact(0)]
        with patch.object(module, 'get_agent_run', return_value=output_run(leads)):
            result = self.client.get('/status/' + task_id).json
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(len(result['result']['leads']), 29)

    def test_query_validation(self):
        for payload in [{}, {'query': ''}, {'query': 'a' * 501}]:
            self.assertEqual(self.client.post('/generate', json=payload).status_code, 400)


if __name__ == '__main__':
    unittest.main()
