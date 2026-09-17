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
- [x] Bookkeeping
- [x] Live verification: `uv run python -m scripts.align_filing AAPL` against real Postgres + OpenAI — all 4 sections came back MATCHED (Item 1A: 0.9651, Item 3: 0.9872, Item 7: 0.9842, Item 8: 0.9725), zero spurious NEW/REMOVED noise. Scores are identical to Part 2's naive `compare_sections.py` output, which is expected and not a red flag: AAPL's filings are the "easy case" (4 sections per side, cleanly one-to-one, no ambiguity), so the naive and optimal-assignment approaches necessarily agree here. The Hungarian algorithm's actual value only shows up when sections compete for the same match or structure changes across filings — that behavior is proven by `test_optimal_assignment_beats_naive_per_row_argmax` instead, since no real filing pair with that kind of ambiguity exists in this project's test data yet.

**Current sub-step:** none — Part 3 complete, ready to merge.

**Open decisions / blockers:** none.

## Part 4 — Materiality Classifier Agent (branch `part-4-materiality-classifier`)

**What this Part adds:** the first LLM reasoning in the pipeline — everything before this (embeddings, cosine similarity, Hungarian assignment) was pure math. Given the Aligner's `alignments`, the classifier reads the actual section text and decides *what* changed and *how much it matters*, producing structured `Finding`s (category, tier, reasoning, verbatim excerpts) instead of just a similarity score.

**Model choice was verified empirically, not assumed** — training knowledge about OpenAI model names goes stale fast, so before designing anything a few real (tiny-cost, ~$0.001 total) API calls were made against the project's real account: `client.models.list()` to see what's actually available, then live test calls exercising the exact structured-output shape being designed around. Landed on **`gpt-5.4-mini`** ($0.75/1M input, $4.50/1M output tokens) — a full 4-section filing-pair classification run costs roughly $0.10-$0.20, trivial against the project's "tens of dollars total" budget. Also confirmed live: `client.responses.parse(text_format=SomePydanticModel)` is the SDK's current designated structured-output path (not the older `chat.completions.parse`, which still works but is documented as legacy), `reasoning` takes a dict (`{"effort": "low"}`) not a flat string param, and `response.output_parsed` can genuinely be `None` on a refusal — `classify_alignment` guards this by returning `[]` rather than crashing.

**No truncation needed here, unlike Part 2** — worth stating explicitly since it'd be easy to assume the same 8192-token embedding cap applies. `gpt-5.4-mini` has a 272K-input-token context window; the worst case (a "matched" pair sending both full older and newer section text) is ~40K tokens, about 15% of the cap.

**Zero findings is a valid, expected output**, not an error case — a "matched" pair with only trivial rewording should produce nothing, not a forced "no material change" finding. This keeps `classifications` independent in length from `alignments`, consistent with how `align_sections` already produces variable-length output relative to its own input. The prompt explicitly tells the model not to invent a finding just to have something to report.

**Pydantic is only at the API boundary.** `responses.parse` requires a real `pydantic.BaseModel`, but results convert immediately into the plain frozen `Finding` dataclass — the rest of the codebase never imports `pydantic`, matching the existing dataclass convention from `aligner.py`/`section_parser.py`.

**Bug caught before it shipped:** wiring the `classify` node into `build_graph`'s default parameters would have made the three pre-existing graph tests from Part 3 silently start making real OpenAI calls, since they didn't override `classify_fn`. Caught and fixed (all graph tests now explicitly inject a fake `classify_fn`) before ever running the full suite with the new wiring in place — worth remembering as a general hazard: extending a function's default behavior can make old tests that relied on the old default start doing something new without any code change to the tests themselves.

- [x] Dependencies (`pydantic` promoted from transitive to explicit)
- [x] `Finding` model + `classify_alignment` (`src/agents/classifier.py`)
- [x] Classifier tests with a stubbed OpenAI client (`tests/agents/test_classifier.py`)
- [x] `PipelineState.classifications` typed as `list[Finding]` (was `list[dict]`, an inconsistency left over from Part 3)
- [x] `classify` node wired into the graph (`align -> classify -> END`)
- [x] Graph tests extended for the new node; fixed the silent-real-API-call bug above
- [x] `scripts/classify_filing.py`; deleted superseded `scripts/align_filing.py`; updated README
- [x] Bookkeeping
- [x] Live verification: `uv run python -m scripts.classify_filing AAPL` against real Postgres + OpenAI — all 4 sections MATCHED (same scores as Part 3), and the classifier produced **18 material findings**, correctly tiered and citing real, specific events: the EU's €500M DMA fine and cease-and-desist order (Item 3, HIGH), the California District Court finding Apple in violation of the Epic injunction and referring it for possible criminal contempt (Item 3, HIGH), new tariff/Section 232 risk language (Item 1A and Item 7, HIGH), the Google antitrust remedies threatening search-revenue licensing (Item 1A, HIGH), the State Aid Decision's resolution and tax impact (Item 8, HIGH), two new FASB accounting standard adoptions (Item 7/8, MEDIUM), and several lower-tier balance-sheet/disclosure changes (debt issuance, lease liabilities, receivables concentration). Every excerpt read as genuine verbatim filing language, not paraphrase, exactly as the prompt instructed. This is a strong, encouraging result for the project's core "verification/eval layer" pitch — full output saved for reference if needed later.

**Connectivity note (not a code issue):** hit the same RDS timeout symptom as Part 2's original setup saga, twice, both times traced to the security group's IP-based rule going stale (the user's public IP changed) rather than anything wrong with the code or schema. Also: earlier in this project a sandboxed environment was concluded to categorically block outbound port 5432 (based on a test against an unrelated host) — that conclusion turned out not to hold on a later attempt from the same environment, so that claim should be treated as circumstantial, not a reliable fact about the environment going forward.

**Current sub-step:** none — Part 4 complete, ready to merge.

**Open decisions / blockers:** none.

## Part 5 — Verifier/Critic Agent + Audit Trail (branch `part5-verifier-agent`)

**What this Part adds:** a governance layer that re-checks every classifier finding instead of trusting it outright — the spec calls this the single most defensible design choice in the whole project. Two layers: (1) a free, deterministic check that each cited excerpt is actually a verbatim substring of the source text — a hallucinated quote fails here and never reaches the LLM at all; (2) for excerpts that check out, a second, deliberately skeptical LLM call judges whether the excerpt actually *supports* the claimed category/tier, producing a confidence score and an independent tier assessment. Also adds the audit trail: every finding — classifier's claim and verifier's re-check — persisted to a new Postgres `findings` table with full provenance (which model/prompt version produced each half, when).

**A live-tested prompt bug worth remembering:** the first version of the verifier's system prompt asked for "confidence" without specifying confidence in *what*. Empirically, the model interpreted this as confidence in its own re-assessment — so an overclaimed finding that got correctly downgraded still came back with confidence=0.98 (the model was very sure about the downgrade), which is useless for Part 6's planned calibration check ("do high-confidence findings hold up more often?"). Fixing the prompt to explicitly say confidence measures support for the *original* claim (0.0 = original claim baseless, 1.0 = original claim fully correct), independent of how certain the verifier is about its own downgrade decision, fixed it immediately: the same overclaimed case then scored 0.12, a well-supported case scored 0.79. Caught via a few cents of live test calls before writing any code against the ambiguous version — the same "verify before committing" practice that caught Part 4's model/API assumptions.

**`Finding.item_key` cannot be used to re-match a finding to its originating alignment.** Traced a real collision: when a Hungarian-forced pairing falls below threshold, the older section becomes a `"removed"` alignment and the newer section becomes a separate `"new"` alignment — both can carry the *same* `item_key` in one run. Fixed by having the classify node emit `classified_pairs: list[tuple[SectionAlignment, Finding]]` alongside the existing flat `classifications` list, so the verify node never needs to re-derive the relationship. Proven with a dedicated test (`test_classified_pairs_correlates_finding_to_correct_alignment_when_item_keys_collide`) using two same-`item_key` alignments with distinguishable content, not just asserted by reasoning about it.

**Same silent-real-API-call hazard as Part 4, pre-empted this time instead of discovered after the fact.** Every `build_graph(...)` call in `test_graph.py` — including the six pre-existing ones from Parts 3-4 — needed an explicit no-op `verify_fn` the moment `verify_fn` started defaulting to the real `verify_finding`. Fixed before ever running the suite with the new wiring in place, not after.

**The audit table is append-only, never upsert** — unlike `upsert_filing` (a filing is an immutable external document, safe to dedup), a findings row is evidence from one specific run with one specific model/prompt version; overwriting on rerun would destroy the audit trail this table exists to build. Locked in with a regression test asserting `insert_findings` never issues a `DELETE`.

**Script evolution:** `scripts/classify_filing.py` → `scripts/run_pipeline.py` — a bigger naming jump than the mechanical per-stage renames before it (`compare_sections` → `align_filing` → `classify_filing`), because the actual role changed: this is the first script that persists its own output rather than just printing a diagnostic. It's the closest thing to a production entry point this project has right now.

- [x] Empirical model check for the verifier's schema + prompt wording (see the confidence-calibration bug above)
- [x] `PROMPT_VERSION` constant added to `classifier.py` (additive only)
- [x] `VerifiedFinding` + two-layer `verify_finding` (`src/agents/verifier.py`)
- [x] Verifier tests including the zero-LLM-calls-on-hallucination proof (`tests/agents/test_verifier.py`)
- [x] `findings` table (`src/storage/schema.py`)
- [x] `insert_findings` write path (`src/storage/db.py`)
- [x] Storage tests including the append-only regression guard
- [x] State + graph wiring: `classified_pairs`, `verified_findings` typed correctly, `align -> classify -> verify -> END`
- [x] Graph tests extended; every pre-existing `build_graph()` call audited for the silent-real-API-call hazard
- [x] `scripts/run_pipeline.py`; deleted superseded `scripts/classify_filing.py`; updated README
- [x] Bookkeeping
- [x] Live verification: `uv run python -m scripts.run_pipeline AAPL` against real Postgres + OpenAI — all 4 sections MATCHED (same scores as Parts 3-4), 16-19 findings per run persisted to the `findings` table (count varies slightly run-to-run since the LLM's exact output isn't deterministic). The two-layer design caught real problems, not just theoretical ones: multiple runs each had 1-2 findings correctly hard-failed at `confidence=0.00, excerpt_verified=False` for citing text that wasn't actually verbatim in the source, and several legitimate tier downgrades with well-reasoned justification (e.g. a claimed "$4.5B debt increase" downgraded after the verifier noticed total term debt principal actually *fell* from $97.3B to $91.3B; the EU DMA fine downgraded HIGH->MEDIUM because "this is regulatory enforcement, not classic litigation"). First `init_db` bug found live: `run_pipeline.py` never called `init_db(conn)`, so the new `findings` table didn't exist on the first live attempt (`psycopg.errors.UndefinedTable`) — `ingest_ticker.py` calls it, this script didn't; fixed by adding the same call (idempotent, `CREATE TABLE IF NOT EXISTS`).
- [x] Performance: classify/verify nodes parallelized with a `ThreadPoolExecutor` (`MAX_WORKERS=8` in `src/agents/graph.py`) after live runs were taking ~80-90s sequentially for ~20 independent LLM calls. Verified with `superpowers:systematic-debugging` rather than assumed: an isolated diagnostic (identical real API calls) showed 9.21s sequential vs. 3.42s concurrent for 4 calls, and a real full-pipeline run afterward measured 36.66s (down from ~80-90s) — roughly a 2.2-2.5x real speedup, not just a theoretical one. Matters most for Part 6, which will run this same pipeline repeatedly against a golden set.

**Current sub-step:** none — Part 5 complete, merged to `main`.

**Open decisions / blockers:** none.

## Part 6 — Eval Harness (branch `part6-eval-harness`)

**What this Part adds:** the piece the spec calls non-optional, not a nice-to-have tacked on at the end — without it, "confidence score" is just a number an LLM made up. Built a hand-verified golden set (6 real filing pairs across AAPL, LYV, MGM, PG, SBUX, NKE — smaller than the spec's suggested 15-25, an explicit, documented tradeoff of a smaller honestly-labeled set over a larger rushed one), scored the pipeline's real output against it (section-level binary precision/recall, not exact category matching — v1 scope decision), added a confidence-calibration check (do true positives score higher than false positives, on average), wired a CI job that runs the real pipeline against cached filing-text fixtures (needs `OPENAI_API_KEY` as a GitHub secret — still pending on your end), and produced `EVAL_REPORT.md`.

**Two dropped golden-set candidates, kept as documented limitations rather than silently avoided:** Wells Fargo's 10-K incorporates all four target sections by reference to a separate exhibit the EDGAR connector doesn't fetch — nothing to evaluate. Costco's section parser grabbed the wrong "Item 8" span (the Exhibits list, not the real financial statements) — a genuine parsing edge case for that filing's structure, not a materiality-judgment issue.

**Bug #1, found live:** the first real eval run crashed — `classify_alignment` had no exception handling around its `responses.parse()` call, and the SDK can raise a validation error (not just return `output_parsed=None`) when the model's JSON output is truncated mid-string. `verify_finding` already guarded this from Part 5; `classify_alignment` never got the same treatment. Fixed with a matching try/except, backed by a regression test reproducing the exact failure.

**Bug #2, much bigger, found via a real cost complaint:** a full eval run showed a suspicious pattern — one company (MGM) went from 3-for-3 correct findings (in the CI test run) to 0-for-3 (in a report-generation run) with no code changes in between. Investigated with `superpowers:systematic-debugging` rather than assumed: re-ran MGM's exact 3 sections in isolation and got all the right findings back immediately, proving the earlier failure was a transient issue (very likely a rate limit under concurrent load) that got silently swallowed by `verify_finding`'s broad `except Exception: return None`-style fallback — the same class of bug as #1, but masking real, recoverable failures as "nothing material happened" instead of retrying. Root-caused further: `verify_finding` was also resending a section's *entire* body text (some sections run 60,000-140,000+ characters) once per individual finding rather than once per section — if a section had 5 findings, that huge block of text got sent 5 separate times. Fixed both at once: a shared retry helper (`src/agents/_llm_utils.py`, using `tenacity`, 3 attempts with backoff before degrading) used by both `classifier.py` and `verifier.py`, and `verify_finding` → `verify_findings_for_alignment`, now batching every finding for one alignment into a single LLM call (mirrors how `classify_alignment` already batches per section). `graph.py`'s verify node now groups findings by alignment *object identity* (`id()`) before calling verify — `SectionAlignment` holds dicts, which aren't hashable, so grouping by value equality wasn't an option.

**A real token-cost lesson, worth remembering.** Debugging bug #2 and re-running the eval to get post-fix numbers meant two full 6-company live runs plus roughly 9 individual diagnostic re-checks in one extended session — real, meaningful cost, called out directly when raised. The process mistake: iterating "fix one thing, rerun the whole 6-company set, find another issue, fix, rerun everything" instead of batching an investigation before re-running. Going forward: gather all suspected issues via targeted single-section checks first, apply every correction, then run the full set once — not after each individual fix.

**Ground-truth curation errors, discovered by taking high-confidence "false positives" seriously instead of dismissing them as model overclaiming.** The first full post-fix run showed 5 findings the golden set had labeled "no finding expected," each with high confidence (0.89-0.98). Rather than writing these off as calibration noise, each was individually re-investigated by reading the actual excerpt and reasoning. Four turned out to be real events the original ground truth missed entirely, because that ground truth was curated via *targeted keyword search* (checking for a few pre-selected terms) rather than a genuinely exhaustive read of every section:
- **NKE Item 1A**: a real S&P credit rating downgrade in July 2025 — missed because the original check only looked for tariff-mention counts.
- **NKE Item 8**: unrecognized tax benefits increased from $990M to $1,026M, with the 12-month reasonably-possible-decrease widening from $35M to $249M — missed because the original check only looked for restructuring/severance keywords.
- **SBUX Item 8**: a real $4.0 billion share repurchase resumption — missed by a targeted scan that found nothing.
- **SBUX Item 1A**: the same "Reinvention Plan" restructuring already correctly credited under Item 7 also appears in the risk factors with a real impairment charge — missed because the original check only looked for inflation/labor/wage/union keywords.
- **LYV Item 7** (found in a later run): a genuine restatement of 2022-2024 financial results, an Astroworld-litigation contingency that reduced 2024 operating income, a tax valuation-allowance release, and new financing activity — missed because the original check only looked for DOJ/antitrust keywords in that section.

All five were corrected in the golden-set fixtures. Only one flagged disagreement (**PG Item 8**, a single sentence adding "Russia-Ukraine War" to routine goodwill-impairment boilerplate) was judged genuinely borderline rather than a clear miss, and was left as a negative case. This whole episode is arguably the best validation this project has produced of its own core premise: a confidence score that disagreed with hand-labeled ground truth turned out, on inspection, to be correctly flagging real events the ground truth's shortcut methodology had missed — exactly the kind of thing a verification layer is supposed to catch. It's also a concrete lesson for any future golden-set expansion: keyword-based spot-checking is not a reliable substitute for a full read, especially on large sections.

**Final numbers** (from the run after the NKE/SBUX corrections, `EVAL_REPORT.md`): **Precision 89%, Recall 100%** (TP=17, FP=2, FN=0, TN=5), confidence calibration TP=0.95 vs FP=0.94 (still flat, largely because most of what looked like miscalibration turned out to be curation error — with the underlying findings now corrected, the *true* current numbers would likely score even higher, since LYV's Item 7 fix happened after this run and was not re-scored to avoid a third full live run in one session; the committed report and golden set are consciously left one correction apart rather than spending more real tokens purely for consistency).

- [x] Eval marker + pyproject.toml config keeping eval calls out of the default suite
- [x] Scoring module (`src/eval/scoring.py`) + pure-math tests
- [x] Golden set data model + JSON loader (`src/eval/golden_set.py`)
- [x] 6 curated, hand-reviewed golden-set cases (`tests/fixtures/eval_golden_set/*.json`)
- [x] Eval runner + markdown report generator (`src/eval/run_eval.py`)
- [x] Eval CI test with threshold-based soft-fail (`tests/eval/test_golden_set_eval.py`)
- [x] CI workflow extended with a real-API `eval` job
- [x] Bug #1 fixed: `classify_alignment` crash on truncated LLM output
- [x] Bug #2 fixed: retry logic (`_llm_utils.py`) + batched verification (`verify_findings_for_alignment`)
- [x] 5 ground-truth curation errors found and corrected (NKE ×2, SBUX ×2, LYV ×1)
- [x] `EVAL_REPORT.md` committed with real, final(-ish) numbers
- [x] Bookkeeping (this update)

**Current sub-step:** none — Part 6 complete, ready to merge.

**Open decisions / blockers:** `OPENAI_API_KEY` still needs to be added as a GitHub Actions repository secret before the CI `eval` job can actually run (Settings → Secrets and variables → Actions) — the code is in place, this is the same manual step the original spec anticipated for this Part.

## Part 7 — Ship It (branch `part7-ship-aws`)

**What this Part adds:** a live, shareable version of everything Parts 1-6 built — a read-only REST API and an MCP server (both thin wrappers over the same query functions, per the spec's own framing), deployed to AWS Lambda behind API Gateway via SAM. Deliberately scoped down from the original spec: no Step Functions, no SQS, no DynamoDB — the pipeline already self-orchestrates (LangGraph + Part 6's retry logic), and the deployed API only serves already-cached Postgres results for the 6 curated tickers, never triggers a live pipeline run from a public request. Expanding the curated set stays a manual CLI-script action, not an API capability.

**A real data gap found before it shipped: `findings` had accumulated 100 rows for AAPL, not ~17.** Hitting the deployed API for the first time (the first time anything ever read this table through a "what would a real consumer see" lens) surfaced this immediately. Traced with `superpowers:systematic-debugging`: `insert_findings` is deliberately append-only (its own docstring: "a findings row is evidence from one specific run... overwriting on rerun would destroy the audit trail this table exists to build"), and AAPL alone had been run through `run_pipeline.py` 5 separate times across Parts 5-6's manual testing (17+19+19+29+16 = 100 rows, all identical `gpt-5.4-mini`/prompt-`v1`, confirmed via a `date_trunc('minute', created_at)` grouping query — genuine duplicates, not evolving output). Rather than break the intentional audit trail, the fix stayed at the query layer: `get_findings_for_filing_pair` now selects only the rows within 10 seconds of `MAX(created_at)` for a filing pair (one run's `insert_findings` call is a single batch `INSERT`, so real-run rows land within microseconds of each other; separate runs are reliably minutes apart — confirmed against live data before picking the window). Every historical run stays queryable directly in Postgres; the API just stops stacking all of them together.

**Two more bugs found only by deploying for real, neither one catchable locally — the clearest evidence yet that "tests pass" and "works in production" are different claims.**

- **Bug: Lambda cold start crashed with `ModuleNotFoundError: No module named 'openai'`.** Root cause: `src/storage/db.py` eagerly imported `VerifiedFinding` (from `agents/verifier.py`), `FilingMetadata`, and `TaggedSection` — all pipeline-only types — purely for type hints on pipeline-only functions (`insert_findings`, `upsert_filing`, `insert_sections`). The API layer only calls the read functions in this same file, but Python imports a module all at once; this never broke locally because `uv sync`'s default groups install the full "pipeline" dependency group there. Fixed by moving those three imports under `if TYPE_CHECKING:` with `from __future__ import annotations` — confirmed the fix by installing *only* `infra/requirements.txt` into a scratch directory and importing `src.api.lambda_handler` directly before ever redeploying.
- **Bug: the API worked on a Lambda's first invocation, then 500'd on every request after it on the same warm container.** Root cause, traced via real CloudWatch logs (`aws logs get-log-events`), not guessed: Mangum's `lifespan="auto"` re-runs the full ASGI lifespan startup/shutdown protocol on *every single invocation*, but `mcp`'s `StreamableHTTPSessionManager.run()` can only be entered once per instance, ever — confirmed by reading the MCP SDK's own source. Mangum does reuse one event loop across warm invocations (set up once in `Mangum.__init__`, not per `__call__` — confirmed by reading `mangum/adapter.py`), so the fix was to stop relying on the ASGI lifespan protocol for the Lambda path entirely: `handler()` now lazily enters the session manager exactly once, on that same shared loop, on the first real invocation, then constructs `Mangum(app, lifespan="off")` so Mangum never touches lifespan again. Local uvicorn testing still uses the original `lifespan=` callback unchanged (uvicorn owns one event loop for the whole process and calls it exactly once already — that path was never broken). A first version of this fix still crashed one request later with `RuntimeError: Task group is not initialized` — the session manager's context-manager object was constructed inline and never assigned to a variable, so it was garbage-collected right after `__aenter__()` returned, tearing down the very task group it had just set up; fixed by holding a persistent module-level reference to it. The regression test for this (`tests/api/test_lambda_handler.py`) deliberately calls the real `handler()` function multiple times with fabricated API-Gateway-v2 events, rather than `TestClient(app)` — `TestClient` exercises uvicorn-style once-per-process lifespan semantics and would never have caught this class of bug, which is exactly why the original version of this test didn't.
- **Bug: every real request to the deployed MCP endpoint got rejected with `421 Invalid Host header`, including from the official `mcp.Client`.** Root cause: `streamable_http_app()`'s DNS-rebinding protection defaults to a restrictive `allowed_hosts` (`127.0.0.1:*`, `localhost:*`, `[::1]:*`) whenever `host` isn't overridden from its own default of `"127.0.0.1"` — fine for local testing (and for the earlier Lambda regression test above, which deliberately sent a `localhost:8000` Host header to dodge exactly this), but it rejects API Gateway's real hostname unconditionally. Fixed with `TransportSecuritySettings(enable_dns_rebinding_protection=False)`, on the same reasoning already applied to opening the RDS security group to `0.0.0.0/0`: this is a browser-focused mitigation, and the server is deliberately public, read-only, and serving public SEC filing analysis — protecting nothing extra here, while hardcoding today's CloudFormation-generated hostname into `allowed_hosts` would just break on the next stack recreation.

**Packaging decision, made with real numbers instead of guessing:** a naive `uv export` for the Lambda pulled in `scipy`/`scikit-learn`/`numpy`/`openai`/`tiktoken`/`langgraph` — none of it imported by `src/api/*`, all of it dead weight there — producing a 228MB unzipped package, dangerously close to Lambda's 250MB ceiling (measured directly: `uv pip install --target` into a scratch directory, not estimated from `.venv` size). Fixed by splitting `pyproject.toml` into API-only main dependencies (`fastapi`, `mangum`, `mcp`, `psycopg[binary]`, `pydantic`) plus a new `pipeline` dependency group for everything the offline ingestion pipeline needs; `[tool.uv] default-groups = ["dev", "pipeline"]` keeps local dev installing everything as before. `infra/requirements.txt` (via `uv export --no-group pipeline`) dropped to 46MB.

**A related, real "why do we need Docker" question led to dropping Docker as a deploy dependency entirely.** `sam build --use-container` exists because `psycopg[binary]` ships a compiled C extension that must match Lambda's Amazon Linux runtime, not the local macOS/arm64 dev machine — but psycopg-binary (and pydantic-core, rpds-py) already publish prebuilt `manylinux` wheels on PyPI. Confirmed empirically: `pip install --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 --implementation cp` downloads real Linux ELF binaries (checked with `file`) from a plain macOS host, no container involved. The build `Makefile` uses this directly; `sam build` (no `--use-container`) and the real deploy both confirmed this works end to end.

**Two manual account-level steps hit and resolved during this Part**, consistent with the standing rule that the agent stops and states what's needed rather than attempting them: the `materiality-engine-dev` IAM user initially lacked `cloudformation:CreateChangeSet` and other permissions needed for a SAM deploy — resolved by attaching `AdministratorAccess` (a personal dev-only AWS account, not shared/production) — and the RDS security group needed widening to `0.0.0.0/0` on 5432 with `sslmode=require` enforced on `DATABASE_URL`, the same non-VPC-Lambda tradeoff confirmed with the user back when this Part was scoped.

**Real live verification, not assumed:** deployed via `sam deploy` to `https://hev6qqrvhg.execute-api.us-east-2.amazonaws.com`. `/api/tickers`, `/api/reports/{ticker}` (both found and 404 cases), and `/api/findings/{id}` all hit directly with `curl` — 5 consecutive requests against the same warm container to specifically confirm the lifespan bug's fix, not just a single lucky request. A real `mcp.Client` from a separate process ran a full `list_tools` → `list_tickers` (×3) → `get_materiality_report` → `get_finding_citation` → not-found-ticker round trip against the live URL.

- [x] Dependencies: `fastapi`, `mangum`, `mcp` added; `mcp` v2 API re-verified empirically (no `FastMCP`, `stateless_http` moved to `.streamable_http_app()`, `mcp.session_manager` lazy-initialized after that call)
- [x] `get_findings_for_filing_pair` (`src/storage/db.py`) + test
- [x] Query layer (`src/api/queries.py`) — "curated" = "whatever's already been ingested," no separate allowlist
- [x] REST layer (`src/api/rest.py`): `GET /tickers`, `GET /reports/{ticker}`, `GET /findings/{finding_id}`
- [x] MCP layer (`src/api/mcp_server.py`): `list_tickers`, `get_materiality_report`, `get_finding_citation`, using `ToolError` (not a bare exception) so not-found messages survive to the client
- [x] Combined Lambda handler (`src/api/lambda_handler.py`) — REST mounted at `/api`, MCP mounted at `/` (its own `streamable_http_app()` already registers `/mcp` internally; mounting it at `/mcp` too would have doubled up into an unreachable `/mcp/mcp`, caught before ever deploying)
- [x] `.env.example` cleanup — trimmed the stale Step Functions/SQS reference now permanently ruled out
- [x] `pyproject.toml` dependency-group split (API vs. `pipeline`), `infra/requirements.txt`, `infra/template.yaml` (SAM, one `AWS::Serverless::Function` + implicit `HttpApi`), root `Makefile` (`BuildMethod: makefile`, manylinux wheels, no Docker), `scripts/deploy.sh`
- [x] RDS security group widened to `0.0.0.0/0` on 5432; `sslmode=require` confirmed on `DATABASE_URL` (your action)
- [x] Local testing: `uvicorn src.api.lambda_handler:app` against real RDS — both REST routes and a real MCP `initialize` round trip
- [x] Duplicate-findings bug found and fixed (query-layer "latest run only" filter, audit trail preserved)
- [x] Real deploy via `sam deploy`; IAM permissions gap hit and resolved (`AdministratorAccess`)
- [x] Lambda cold-start `ModuleNotFoundError` found and fixed (`TYPE_CHECKING` guard in `db.py`)
- [x] Per-invocation lifespan/session-manager crash found and fixed (lazy single-entry `handler()`, `lifespan="off"`); regression test exercises the real `handler()` entry point across multiple invocations, not `TestClient`
- [x] DNS-rebinding `421 Invalid Host header` found and fixed (`enable_dns_rebinding_protection=False`)
- [x] Full live re-verification after both fixes: REST (multiple consecutive requests), MCP (`mcp.Client` against the real deployed URL, including the not-found error path)

**Current sub-step:** 11 of 14 complete (dependencies through real deploy + live verification). Remaining: frontend (S3 + CloudFront, manual console setup, matching the RDS precedent), final live verification of the frontend loading real data, and closing bookkeeping (this entry + README API/MCP usage section).

**Open decisions / blockers:** none currently blocking. AWS SAM CLI and `aws` CLI credentials both required manual one-time setup on your end (SAM CLI install, IAM policy attachment) — both done.
