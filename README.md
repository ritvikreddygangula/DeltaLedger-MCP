# materiality-engine

A research/diligence copilot that ingests a public company's sequential SEC filings, detects and classifies material changes (new risk factors, MD&A shifts, litigation, accounting policy changes), and surfaces every finding with a source citation and a calibrated confidence score.

**What this is not:** it does not make buy/sell/investment decisions. It surfaces and verifies *what changed and why it might matter*, with full traceability back to source text.

## Try it live

No setup needed to see it in action:

- **Frontend**: [materiality-engine.vercel.app](https://materiality-engine.vercel.app). Pick a ticker, see every finding with its tier, category, reasoning, confidence, and source excerpts from both filings.
- **MCP server**: point any MCP client at `https://materiality-engine-api.onrender.com/mcp`, or add it to Claude Code directly:
  ```bash
  claude mcp add --transport http materiality-engine https://materiality-engine-api.onrender.com/mcp
  ```
- **REST API**: `https://materiality-engine-api.onrender.com`
  ```
  GET /api/tickers                # the curated set of covered companies
  GET /api/reports/{ticker}       # both filings + every finding for that pair
  GET /api/findings/{finding_id}  # a single finding's full detail
  GET /api/health                 # DB connectivity check
  ```

### MCP tools

| Tool | What it does |
|---|---|
| `list_tickers()` | Lists the curated tickers with cached materiality analysis available. |
| `get_materiality_report(ticker)` | Returns a ticker's two most recent 10-K filings plus every finding: category, materiality tier, reasoning, confidence, and source excerpts. |
| `get_finding_citation(finding_id)` | Returns a single finding's full detail (source citation, confidence, reasoning) by its id. |

**Coverage is a curated set of about 10 companies, not a live "type any ticker" search.** Analyzing a new company makes real, billed OpenAI API calls, so the set only grows through a manual step, never from a public request. Scaling coverage toward hundreds of companies while keeping per-company LLM cost minimal is an ongoing area of exploration, not a solved problem yet, candidates include pushing the diffing/caching approach further and running ingestion as a slow, cost-capped background process rather than an interactive one.

The API runs on Render's free tier, which sleeps after 15 idle minutes, so the first request after a quiet spell can take up to a minute to wake it.

## Architecture

```
SEC EDGAR ──> ingest_ticker ──> run_pipeline (align → classify → verify) ──┐
              (local CLI)         (local CLI, OpenAI)                       │ writes
                                                                            ▼
                                                     Supabase Postgres (one database)
                                                                            │ reads
                                   FastAPI REST /api/*  +  MCP /mcp  <──────┘
                                   (one uvicorn app on Render)
                                            ▲
                       Vercel static frontend, MCP clients (Claude Code, ...)
```

- **One database, no sync step.** The pipeline writes filings, sections, findings, and its LLM cache to Postgres. The API reads the same tables. Findings are append-only (every pipeline run is kept as an audit trail), and the API serves the latest run.
- **Read-only serving.** Public requests never trigger ingestion or LLM calls. Coverage only grows through the CLI scripts.
- **Locked down by default.** Supabase exposes every `public` table over its auto-generated REST API to anyone holding the project's anon key, so every table has row-level security enabled with no policies. The server connects as the table owner and bypasses RLS.
- **Why this stack.** It previously ran on AWS (Lambda + API Gateway via SAM, S3 + CloudFront, plus an S3 export step between the pipeline and the API). That was a lot of infrastructure for a read-only API over a few hundred rows. Supabase + Render + Vercel replaced it with three free-tier services and one source of truth. It also puts the data in Postgres, where pgvector is one `CREATE EXTENSION` away.

## Observability & CI

Every layer (pipeline stages, OpenAI calls, REST requests, MCP tool calls) logs structured JSON to stdout, visible and searchable in Render's log stream: per-stage latency, cache hit/miss counts, and real token usage per OpenAI call. CI runs the full test suite, including integration tests against a real Postgres service container, plus dependency vulnerability scanning (`pip-audit`) and committed-secret scanning (`gitleaks`) on every push and pull request. A daily scheduled workflow pings `/api/health` (a real `SELECT 1`) so the free-tier database never pauses for inactivity.

## Running it yourself

```bash
uv sync
cp .env.example .env
```

Fill in your own `.env`:

- `OPENAI_API_KEY`: yours. Every analysis run below bills to it.
- `EDGAR_USER_AGENT`: SEC EDGAR requires an identifying string on every request, e.g. `"Your Name your@email.com"`.
- `DATABASE_URL`: any Postgres. A free Supabase project works (use its **Session pooler** connection string), or a local one:
  ```bash
  docker run -d --name me-pg -e POSTGRES_PASSWORD=postgres -p 54329:5432 postgres:17
  # DATABASE_URL=postgresql://postgres:postgres@localhost:54329/postgres
  ```
  Tables are created automatically on first run.

Add a company:

```bash
uv run python -m scripts.ingest_ticker AAPL   # pulls the last 2 10-Ks from SEC EDGAR, free
uv run python -m scripts.run_pipeline AAPL    # runs the analysis, real OpenAI calls, a few cents
```

Serve it locally (REST at `http://localhost:8000/api/...`, MCP at `http://localhost:8000/mcp`):

```bash
uv run uvicorn src.api.app:app --port 8000
```

Run the test suite. No API key is needed, since every LLM call is mocked. The storage and API tests run against a real Postgres when `TEST_DATABASE_URL` points at a throwaway database (they drop and recreate its tables), and skip otherwise:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54329/postgres uv run pytest
```

## Deploying

- **Database:** create a Supabase project and copy its Session pooler URI. The schema is applied by the first script run.
- **API:** Render → New → Blueprint → this repo. `render.yaml` defines the service, and Render prompts for `DATABASE_URL`.
- **Frontend:** Vercel → import this repo with Root Directory `frontend`, no build step. The backend URL is the `API_ORIGIN` constant in `frontend/index.html`.
