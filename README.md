# materiality-engine

A research/diligence copilot that ingests a public company's sequential SEC filings, detects and classifies material changes (new risk factors, MD&A shifts, litigation, accounting policy changes), and surfaces every finding with a source citation and a calibrated confidence score.

**What this is not:** it does not make buy/sell/investment decisions. It surfaces and verifies *what changed and why it might matter*, with full traceability back to source text.

Cross-session progress tracking: see `PROGRESS.md`.

## Setup

```bash
uv sync
```

## Running tests

```bash
uv run pytest
```

## Configuration

Copy `.env.example` to `.env` and fill in the required values (see the file for what each one is used for).

## Ingesting a company's filings

```bash
uv run python -m scripts.ingest_ticker AAPL
```

Pulls the two most recent 10-Ks for the given ticker from SEC EDGAR, tags each one's Item 1A (Risk Factors), Item 3 (Legal Proceedings), Item 7 (MD&A), and Item 8 (Financial Statements) sections, and stores everything in Postgres. Requires `EDGAR_USER_AGENT` and `DATABASE_URL` to be set in `.env`.

## Running the full pipeline

```bash
uv run python -m scripts.run_pipeline AAPL
```

For a ticker already ingested via the command above, runs the full Aligner + Materiality Classifier + Verifier pipeline: prints every section as MATCHED (with a similarity score), REMOVED, or NEW, then every finding with both the classifier's original claim and the verifier's independent re-check — a confidence score, whether the cited excerpt was actually found verbatim in the source text, and the verifier's own tier assessment (shown alongside the original if it was downgraded or upgraded). Every finding is then persisted to Postgres as a permanent audit record. Requires `DATABASE_URL` and `OPENAI_API_KEY`. Makes real, billed OpenAI chat calls (a few cents per run).

## Live deployment (Part 7)

A read-only API and MCP server, deployed to AWS Lambda behind API Gateway, serving already-cached findings for the curated set of ingested tickers. Nothing here triggers a live pipeline run from a public request — expanding the curated set stays a manual action, via the two scripts above.

**REST API** — `https://hev6qqrvhg.execute-api.us-east-2.amazonaws.com`

```
GET /api/tickers                # the curated set, e.g. ["AAPL","LYV","MGM","NKE","PG","SBUX"]
GET /api/reports/{ticker}       # both filings + every finding for that pair
GET /api/findings/{finding_id}  # a single finding's full detail
GET /api/health                 # DB connectivity check -- 200 if reachable, 503 (generic, no detail leaked) if not
```

**MCP server** — same backend, same three operations, exposed as tools (`list_tickers`, `get_materiality_report`, `get_finding_citation`) at `https://hev6qqrvhg.execute-api.us-east-2.amazonaws.com/mcp` via the Streamable HTTP transport. Point any MCP client at that URL directly, or add it to Claude Code in one command:

```bash
claude mcp add --transport http materiality-engine https://hev6qqrvhg.execute-api.us-east-2.amazonaws.com/mcp
```

**Frontend** — `https://d30z0su1b3sesp.cloudfront.net`

A minimal static page: pick a curated ticker, see every finding with its tier, category, reasoning, confidence, and source excerpts from both filings.

**Redeploying:**

```bash
./scripts/deploy.sh                                   # API + MCP server (Lambda via SAM)
./scripts/deploy_frontend.sh <bucket> <distribution-id>  # static frontend (S3 + CloudFront)
```

## Observability & CI (Part 9)

Every layer -- pipeline stages, OpenAI calls, REST requests, MCP tool calls -- logs structured JSON lines (`src/observability.py`, stdlib `logging` only, no new dependency). Both the deployed Lambda and any local script send stdout to a place that already captures it (CloudWatch, or a terminal), so these are immediately queryable in CloudWatch Logs Insights, e.g.:

```
fields @timestamp, duration_ms, event, ticker
| filter event = "http_request"
| sort duration_ms desc
```

CI runs a `security` job on every push and PR (`.github/workflows/ci.yml`): `pip-audit` against the exported lockfile for known dependency CVEs, and `gitleaks` for committed secrets.
