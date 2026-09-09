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

## Part 3 — Aligner Agent (branch `part-3-aligner-agent`)

**What this Part actually adds over Part 2:** Part 2's `compare_sections.py` did an ad-hoc comparison — each older-filing section independently picked whichever newer-filing section scored highest against it. That's not a real alignment: nothing stopped two older sections from both claiming the same best-scoring newer section, and nothing ever said "this section is genuinely new" or "this one disappeared." Part 3 replaces that with a proper one-to-one assignment (`scipy.optimize.linear_sum_assignment`, the Hungarian algorithm) that finds the single pairing maximizing total similarity across *all* sections at once, then gates each pairing through a similarity threshold so a forced-but-bad pairing becomes explicit "removed" + "new" findings instead of a false match. `tests/agents/test_aligner.py` has a concrete constructed case proving this matters: two older sections both score highest against the same newer section (1.0 and 0.8), so naive argmax would double-claim it — the optimal assignment instead separates them (1.0 and 0.6) since that's the pairing that maximizes total similarity.

**LangGraph decision:** set up now, not deferred to Part 4, even though there's only one real node (`align`) — `src/agents/state.py` defines one flat `PipelineState` schema (not per-Part subclasses) with `NotRequired` placeholder fields for Part 4's `classifications` and Part 5's `verified_findings`, so those Parts add a node + a field without ever touching this Part's code. Verified LangGraph's actual current API (1.2.11) before building against it rather than assuming: `TypedDict` state, `START`/`END` sentinel edges (not the older `set_entry_point`), node functions returning partial-state-update dicts.

**Threshold is a judgment call, not a calibrated value:** `DEFAULT_MATCH_THRESHOLD = 0.75` in `src/agents/aligner.py`. Part 2's live run showed genuine same-company year-over-year matches scoring 0.96-0.99 — that's the only real data point available. 0.75 leaves headroom below that for legitimately-matched-but-reworded sections while still rejecting a forced pairing between unrelated ones, but SEC filings share a lot of generic boilerplate/legal language that could score misleadingly high on cosine similarity — this needs revisiting once Part 6's eval harness has real cross-company or renamed-section data to tune against. Kept as a function parameter specifically so that recalibration is a one-line change, not a rewrite.

- [x] Dependencies (`langgraph`, `scipy`)
- [x] `align_sections` core function + `SectionAlignment` (`src/agents/aligner.py`)
- [x] Aligner tests including the Hungarian-vs-argmax proof (`tests/agents/test_aligner.py`)
- [x] Shared `PipelineState` schema (`src/agents/state.py`)
- [x] LangGraph wiring with injectable embedding function (`src/agents/graph.py`)
- [x] Graph tests with a fake embed function, no real API calls (`tests/agents/test_graph.py`)
- [x] `scripts/align_filing.py`; deleted superseded `scripts/compare_sections.py`; updated README
- [ ] Bookkeeping (this update)
- [ ] Live verification (see below)

**Current sub-step:** bookkeeping, then live verification.

**Open decisions / blockers:** live verification (`uv run python -m scripts.align_filing AAPL` against real Postgres + OpenAI) not yet run — expect AAPL's structurally-stable filings to show all 4 sections as MATCHED with scores in the same 0.96-0.99 ballpark Part 2 observed, and zero spurious NEW/REMOVED noise; any deviation from that is worth investigating before calling this Part done.

## Up next: Part 4 — Materiality Classifier Agent (not started)
