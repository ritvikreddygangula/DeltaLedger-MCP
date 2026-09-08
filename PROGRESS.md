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

## Part 2 — Postgres Storage & Embedding Pipeline (branch `part-2-embedding-pipeline`)

**Why this Part looks different from the original spec's sequencing:** the spec had deferred all AWS work to a later "Part 7," with Part 2 only needing "a" Postgres. When asked which Postgres provider, the user deliberately chose **AWS RDS** over lighter zero-setup options (Neon, Supabase) — meaning the AWS account/IAM/RDS-instance setup that was supposed to wait until Part 7 is happening now, just scoped to RDS only (not Lambda/Step Functions/etc., which are still genuinely Part 7). I can't create AWS accounts, IAM users, or RDS instances myself, so all of that is a manual step (see blockers below) — none of the code below needed to wait on it.

**What got built:**
- `src/storage/schema.py` and `src/storage/db.py` fully rewritten from SQLite (`sqlite3`) to Postgres (`psycopg[binary]` v3). Same five function names/signatures survive from Part 1 (`get_connection`, `init_db`, `upsert_filing`, `insert_sections`, `get_filing_sections`), plus one new one (`get_filings_for_ticker`) — so `scripts/ingest_ticker.py` needed zero changes. `upsert_filing` got simpler too: Postgres's `INSERT ... ON CONFLICT ... RETURNING id` collapsed Part 1's insert-then-separate-select into one round trip.
- `id` columns use `GENERATED ALWAYS AS IDENTITY` (modern Postgres idiom, not `SERIAL`); `fetched_at` is now a real `TIMESTAMPTZ` instead of an ISO string, since psycopg3 adapts Python `datetime` natively.
- New `src/embeddings/` package: `openai_client.get_embeddings()` (OpenAI `text-embedding-3-small`, defensively re-sorted by response index rather than trusting implicit ordering) and `similarity.cosine_similarity_matrix()` (scikit-learn). Verified the installed `openai` SDK's actual `embeddings.create()` signature by inspection before writing code against it, rather than assuming — the installed version is quite new (3.8.0).
- New `scripts/compare_sections.py`: pulls a ticker's two most recent ingested 10-Ks, embeds every section on both sides, and prints each older-filing section's best newer-filing match by cosine similarity — computing the *full* cross matrix rather than assuming sections pair up by matching `item_key`, since the point is previewing what the Part 3 Aligner agent needs even when section structure isn't identical across filings.

**Known trade-off (deliberate, not an oversight):** Part 1's storage tests ran against real SQLite `:memory:`, so they were genuine round-trip integration tests for free. Postgres has no equivalent, so `tests/storage/test_db.py` now uses stub connection/cursor objects (same DI pattern as the EDGAR connector tests) — they prove our SQL-building logic is right, not that Postgres actually accepts and executes it. That proof now lives entirely in the live verification below.

**Bug found and fixed during live verification:** `get_embeddings` crashed on real filing data with `openai.BadRequestError: maximum input length is 8192 tokens` — Item 1A (Risk Factors) and Item 8 (Financial Statements) sections routinely run 60K+ characters, well past the embedding model's per-input limit. Fixed by adding `tiktoken` (OpenAI's own tokenizer) to truncate each section to a safe token count before sending it (`src/embeddings/openai_client.py`). This loses the tail of very long sections for *this* similarity-preview pipeline specifically — acceptable here since the later LLM classifier agents (Part 4/5) will read full section text directly, not through an embedding.

**RDS setup saga (worth remembering if this ever needs debugging again):** getting a real, reachable RDS instance took several rounds — (1) a `.env` connection string with the literal `<placeholder>` angle brackets left in from copy-pasting instructions, (2) a security group with only the default self-referencing rule (source = the SG's own ID), which allows AWS resources to talk to each other but nothing external — had to add an explicit PostgreSQL/5432 rule with an actual source IP, (3) "Publicly accessible" not set, which meant the endpoint resolved to a private `172.x` VPC-internal address from outside AWS, (4) after rebuilding AWS from scratch with a new IAM user + new RDS instance, connections hung even with the security group wide open to `0.0.0.0/0` on two different networks (university wifi and a phone hotspot) — the actual cause turned out to be much simpler: the **`materiality` database itself was never created**, because the "Initial database name" field wasn't set this time during RDS creation. Fixed by connecting with `psql` directly and running `CREATE DATABASE materiality;`. Lesson: a bare TCP-level hang can look identical to several unrelated problems (routing, security groups, local firewalls) — `psql` connecting directly, bypassing the app entirely, was the diagnostic that actually cut through it.

- [x] Dependencies (`psycopg[binary]`, `openai`, `scikit-learn`, `numpy`, `tiktoken`) + `DATABASE_URL` added to `.env.example`
- [x] Schema ported to Postgres DDL
- [x] `db.py` rewritten for psycopg3
- [x] Storage tests rewritten with stubs
- [x] `src/embeddings/openai_client.py` + stub-based tests (including token-truncation tests)
- [x] `src/embeddings/similarity.py` + pure-math tests
- [x] `scripts/compare_sections.py`
- [x] Bookkeeping
- [x] Live verification — both real commands run successfully against the live AWS RDS instance and real OpenAI API:
  - `ingest_ticker AAPL`: both real 10-Ks (`0000320193-25-000079` filed 2025-10-31, `0000320193-24-000123` filed 2024-11-01) ingested into Postgres, all 4 sections tagged on each
  - `compare_sections AAPL`: every section correctly matched to its same-`item_key` counterpart across the two filings, with high similarity scores as expected for one-year-apart filings from the same company — Item 1A: 0.9651, Item 3: 0.9872, Item 7: 0.9842, Item 8: 0.9725

**Current sub-step:** none — Part 2 complete, ready to merge.

**Open decisions / blockers:** none.

## Up next: Part 3 — Aligner Agent (not started)
