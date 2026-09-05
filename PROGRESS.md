# Progress

Cross-session tracker. Read this before starting new work in a fresh session.

## Part 0 — Boilerplate & Scaffolding

- [x] Repo skeleton (`src/*` packages, `tests/`, `infra/`, `.gitignore`)
- [x] Dependency setup (`uv init`, `pyproject.toml`, `uv.lock`, dev deps: pytest, ruff)
- [x] `.env.example` documenting required environment variables
- [x] `README.md` skeleton
- [x] `PROGRESS.md` initialized (this file)
- [x] Test scaffold (`tests/test_placeholder.py`, verified green via `uv run pytest`)
- [x] CI workflow placeholder (`.github/workflows/ci.yml`)

**Current sub-step:** none — Part 0 complete.

**Open decisions / blockers:** none.

## Part 1 — EDGAR Ingestion & Section Parsing (branch `part-1-edgar-ingestion`)

Scope decisions: storage is local SQLite for this Part (Postgres migration + embeddings deferred to Part 2); 10-K only (not 10-Q); `10-K/A` amendments excluded. User confirmed sticking with local SQLite over a cloud DB for now.

- [x] Dependencies (`requests`, `beautifulsoup4`, `lxml`, `python-dotenv`)
- [x] `FilingConnector` protocol + `FilingMetadata` (`src/connectors/base.py`)
- [x] EDGAR CIK resolution (`src/connectors/edgar.py`)
- [x] EDGAR recent-filings listing with pagination fallback
- [x] EDGAR document fetch
- [x] HTML section parser with ToC-vs-heading disambiguation (`src/connectors/section_parser.py`)
- [x] SQLite schema + write path (`src/storage/schema.py`, `src/storage/db.py`)
- [x] `scripts/ingest_ticker.py` wiring connector → parser → storage
- [x] Bookkeeping + delete superseded placeholder test
- [x] Live verification: `uv run python -m scripts.ingest_ticker AAPL` against real EDGAR data — both real 10-Ks (accession `0000320193-25-000079` filed 2025-10-31, `0000320193-24-000123` filed 2024-11-01) tagged with all 4 target sections and substantive body text, confirmed via direct SQLite query

**Current sub-step:** none — Part 1 complete, ready to merge.

**Open decisions / blockers:** none. Note: must run the script as `python -m scripts.ingest_ticker`, not `python scripts/ingest_ticker.py` directly — the latter doesn't put the repo root on `sys.path` so `import src...` fails.

## Up next: Part 2 — Structured Storage (Postgres) & Embedding Pipeline (not started)
