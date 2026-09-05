# xlverhuur_leadfinder

Search for a business service or topic, such as `Kraan huren`, and collect available public business contact details from web result pages and linked contact pages using Exa Agent.

- Enter a search term before starting a run.
- Businesses qualify with or without a website; any email provider is allowed.
- Results contain business name, email, phone and business address. Unavailable values stay empty.
- Download the visible results as CSV. Spreadsheet formula prefixes are escaped in the download.
- Results are deduplicated within each search; earlier searches do not suppress matches.
- Small and empty result sets are valid. Search batches have configured limits, so results are not exhaustive.

The search provider is Exa. This implementation does **not** directly fetch Google's search result pages or guarantee Google's rankings. Literal Google search requires a separate provider integration.

## Run locally

Install `requirements.txt`, configure `EXA_API_KEY` and `DATABASE_URL` (Postgres), then run `python app.py`. The application creates its task table on startup. Completed searches are saved in the database.

Each search creates exactly one Exa Agent run requesting at most 15 businesses. Fewer results (including zero) are valid. The old quota/batch environment variables are ignored.

The app saves the Exa run ID before returning from `/generate`. Each `/status` request checks that same run once and saves its result when complete. No daemon thread or hour-long HTTP request is required. Failed status checks never launch replacement runs.

Active searches appear in history. Open one to resume polling after a reload or deployment; older tasks with an ID stored in `progress.generation_run_id` are also recoverable, retaining all their results. Tasks without a saved provider ID cannot be automatically recovered.

`POST /generate` requires a JSON body such as `{"query":"Kraan huren"}`. Search terms must contain 1–500 characters. The response contains the task ID; poll `/status/<task_id>` and use `/history` for saved runs.
