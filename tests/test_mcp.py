"""Exercise MCP transport and real search handlers without external services."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from test_generation import module, output_run, contact


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'MCP_ALLOWED_ORIGINS': 'https://trusted.example'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = module.app.test_client()
        self.headers = {'Accept': 'application/json, text/event-stream'}
        with module.app.app_context():
            module.db.session.query(module.Task).delete()
            module.db.session.commit()

    def rpc(self, method, params=None, **kwargs):
        return self.client.post('/mcp', headers=self.headers, json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}, **kwargs)

    def test_lifecycle_and_tools(self):
        init = self.rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}})
        self.assertEqual(init.json['result']['protocolVersion'], '2025-11-25')
        self.assertEqual(len(self.rpc('tools/list').json['result']['tools']), 3)
        notification = self.client.post('/mcp', headers=self.headers, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        self.assertEqual((notification.status_code, notification.data), (202, b''))
        with patch.object(module, 'create_agent_run', return_value=SimpleNamespace(id='agent_run_test')) as create:
            started = self.rpc('tools/call', {'name': 'start_search', 'arguments': {'query': 'crane rental'}}).json['result']
            self.assertFalse(started['isError'])
            task_id = started['structuredContent']['task_id']
            with patch.object(module, 'get_agent_run', return_value=output_run([contact()])):
                result = self.rpc('tools/call', {'name': 'get_search', 'arguments': {'task_id': task_id}}).json['result']
            self.assertEqual(result['structuredContent']['status'], 'incomplete')
            self.assertEqual(len(result['structuredContent']['result']['leads']), 1)
            self.assertEqual(len(self.rpc('tools/call', {'name': 'list_searches'}).json['result']['structuredContent']['runs']), 1)
            create.assert_called_once()

    def test_unauthenticated_origin_and_transport(self):
        response = self.rpc('ping')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('WWW-Authenticate', response.headers)
        self.headers['Origin'] = 'https://evil.example'
        self.assertEqual(self.rpc('ping').status_code, 403)
        self.headers['Origin'] = 'https://trusted.example'
        self.assertEqual(self.rpc('ping').status_code, 200)
        self.assertEqual(self.client.get('/mcp', headers=self.headers).status_code, 405)
        self.headers['MCP-Protocol-Version'] = 'bad'
        self.assertEqual(self.rpc('ping').status_code, 400)
        del self.headers['MCP-Protocol-Version']
        self.headers['Accept'] = 'text/html'
        self.assertEqual(self.rpc('ping').status_code, 406)

    def test_invalid_messages_and_tool_errors(self):
        self.assertEqual(self.client.post('/mcp', headers=self.headers, data='{', content_type='application/json').json['error']['code'], -32700)
        self.assertEqual(self.client.post('/mcp', headers=self.headers, json=[]).status_code, 400)
        self.assertEqual(self.rpc('missing').json['error']['code'], -32601)
        for name, arguments in [('start_search', {}), ('start_search', {'query': ' '}), ('list_searches', {'limit': True}), ('list_searches', {'limit': 101}), ('get_search', {'task_id': 'x', 'extra': 1})]:
            with self.subTest(name=name, arguments=arguments):
                self.assertEqual(self.rpc('tools/call', {'name': name, 'arguments': arguments}).json['error']['code'], -32602)
        result = self.rpc('tools/call', {'name': 'get_search', 'arguments': {'task_id': 'missing'}}).json['result']
        self.assertTrue(result['isError'])
        with patch.object(module, 'create_agent_run') as create:
            self.client.post('/mcp', headers=self.headers, json={'jsonrpc': '2.0', 'method': 'tools/call', 'params': {'name': 'start_search', 'arguments': {'query': 'cranes'}}})
            create.assert_not_called()
