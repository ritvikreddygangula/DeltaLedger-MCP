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

Copy `.env.example` to `.env` and fill in the required values (see the file for what each one is used for and which build Part introduces it).

## Ingesting a company's filings

```bash
uv run python -m scripts.ingest_ticker AAPL
```

Pulls the two most recent 10-Ks for the given ticker from SEC EDGAR, tags each one's Item 1A (Risk Factors), Item 3 (Legal Proceedings), Item 7 (MD&A), and Item 8 (Financial Statements) sections, and stores everything in Postgres. Requires `EDGAR_USER_AGENT` and `DATABASE_URL` to be set in `.env`.

## Aligning sections across two filings

```bash
uv run python -m scripts.align_filing AAPL
```

For a ticker already ingested via the command above, runs the Aligner agent (embeddings + optimal one-to-one assignment, not just each section's best guess) and prints every section as MATCHED (with a similarity score), REMOVED (present in the older filing only), or NEW (present in the newer filing only). Requires `DATABASE_URL` and `OPENAI_API_KEY`.
