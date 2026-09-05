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

Existing environment variable names are retained for deployment compatibility:

```env
MARKETPOST_FINAL_LEAD_TARGET=100
MARKETPOST_LEADS_PER_AGENT_RUN=25
MARKETPOST_MAX_GENERATION_PASSES=7
MARKETPOST_MAX_CANDIDATES_PER_PASS=25
```

Website verification is removed and the old secondary-verification setting is ignored. Each batch uses one paid Exa Agent run; actual usage depends on research performed.

`POST /generate` requires a JSON body such as `{"query":"Kraan huren"}`. Search terms must contain 1–500 characters. The response contains the task ID; poll `/status/<task_id>` and use `/history` for saved runs.
