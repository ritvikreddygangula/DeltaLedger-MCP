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
