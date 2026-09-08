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

Each search creates exactly one Exa Agent run requesting exactly 30 unique businesses. Only results with 30 unique businesses are marked complete. Shorter results (including zero) are saved as incomplete and remain available for review and CSV export; no businesses are fabricated and no automatic extra paid runs are started. The old quota/batch environment variables are ignored.

The app saves the Exa run ID before returning from `/generate`. Each `/status` request checks that same run once and saves its result when complete. No daemon thread or hour-long HTTP request is required. Failed status checks never launch replacement runs.

Active searches appear in history. Open one to resume polling after a reload or deployment; older tasks with an ID stored in `progress.generation_run_id` are also recoverable, retaining all their results. Tasks without a saved provider ID cannot be automatically recovered.

`POST /generate` requires a JSON body such as `{"query":"Kraan huren"}`. Search terms must contain 1–500 characters. The response contains the task ID; poll `/status/<task_id>` and use `/history` for saved runs.

## HTTP MCP endpoint

Connect a Streamable HTTP MCP client to `https://<your-app-domain>/mcp`
(locally, `http://127.0.0.1:5000/mcp`). The existing Vercel routing includes this endpoint.
No API token or Authorization header is required. Anyone who can reach the endpoint
can start paid searches and access the shared search history. The server still needs
`EXA_API_KEY` to run Exa searches.

Available tools:

- `start_search({"query":"Kraan huren"})`: starts one paid Exa run and returns `task_id`.
- `get_search({"task_id":"..."})`: checks the same run and returns status and available leads/CSV.
- `list_searches({"limit":20})`: returns shared run history; limit is 1–100.

Search creation is not idempotent. After an ambiguous failure, inspect history before
retrying to avoid paying for another run. All clients can access all searches.

The transport follows the [MCP Streamable HTTP specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports),
using stateless JSON responses without SSE streams or session IDs. Supported protocol
versions are `2025-11-25`, `2025-06-18`, and `2025-03-26`. POST requests must include
`Content-Type: application/json` and `Accept: application/json, text/event-stream`;
send `MCP-Protocol-Version` after initialization. GET and DELETE return 405.
Requests containing an Origin header are rejected unless it exactly matches a
comma-separated entry in `MCP_ALLOWED_ORIGINS` (for example `https://your-app.example`).
Browser CORS clients are not enabled; this endpoint is intended for server/desktop clients.

Initialization smoke check (set `MCP_URL` in your shell):

```sh
curl "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"smoke-check","version":"1.0"}}}'
```

Run offline tests from this directory with `python -m unittest discover -s tests`.
