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

## Up next: Part 1 — EDGAR Ingestion (branch `part-1-edgar-ingestion`, not started)

Blocked on manual setup: `EDGAR_USER_AGENT` needs to be added to a local `.env` (no signup/key required, see `.env.example`) before EDGAR connector work can hit real endpoints.
