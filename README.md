# materiality-engine

A research/diligence copilot that ingests a public company's sequential SEC filings, detects and classifies material changes (new risk factors, MD&A shifts, litigation, accounting policy changes), and surfaces every finding with a source citation and a calibrated confidence score.

**What this is not:** it does not make buy/sell/investment decisions. It surfaces and verifies *what changed and why it might matter*, with full traceability back to source text.

## Try it live

No setup needed to see it in action:

- **Frontend**: [d30z0su1b3sesp.cloudfront.net](https://d30z0su1b3sesp.cloudfront.net). Pick a ticker, see every finding with its tier, category, reasoning, confidence, and source excerpts from both filings.
- **MCP server**: point any MCP client at `https://hev6qqrvhg.execute-api.us-east-2.amazonaws.com/mcp`, or add it to Claude Code directly:
  ```bash
  claude mcp add --transport http materiality-engine https://hev6qqrvhg.execute-api.us-east-2.amazonaws.com/mcp
  ```
- **REST API**: `https://hev6qqrvhg.execute-api.us-east-2.amazonaws.com`
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

## Observability & CI

Every layer (pipeline stages, OpenAI calls, REST requests, MCP tool calls) logs structured JSON, queryable directly in CloudWatch Logs Insights: per-stage latency, cache hit/miss counts, and real token usage per OpenAI call. CI runs the full test suite plus dependency vulnerability scanning (`pip-audit`) and committed-secret scanning (`gitleaks`) on every push and pull request.

## Running it yourself

```bash
uv sync
cp .env.example .env
```

Fill in your own `.env`: `OPENAI_API_KEY` (yours, every analysis run below bills to it), `DATABASE_URL` (a Postgres instance), and `EDGAR_USER_AGENT` (SEC EDGAR requires an identifying string on every request, e.g. `"Your Name your@email.com"`).

Add a company to your own database:

```bash
uv run python -m scripts.ingest_ticker AAPL   # pulls the last 2 10-Ks from SEC EDGAR, free
uv run python -m scripts.run_pipeline AAPL    # runs the analysis, real OpenAI calls, a few cents
```

Run the test suite (no API key needed, everything's mocked):

```bash
uv run pytest
```
