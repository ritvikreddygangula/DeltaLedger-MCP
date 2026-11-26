"""Integration tests against a real Postgres (see the pg_conn fixture in
tests/conftest.py). The stub-based tests in test_db.py only check which SQL
gets sent. These check that the SQL actually runs and returns the right
rows."""

from datetime import date

from src.agents.classifier import Finding
from src.agents.verifier import VerifiedFinding
from src.connectors.base import FilingMetadata
from src.connectors.section_parser import TaggedSection
from src.storage.db import (
    get_filing_sections,
    get_filings_for_ticker,
    get_findings_for_filing_pair,
    insert_findings,
    insert_sections,
    upsert_filing,
)
from src.storage.llm_cache import get_cached, set_cached


def _make_filing(accession_number="0000320193-25-000079", filing_date="2025-11-01") -> FilingMetadata:
    return FilingMetadata(
        ticker="AAPL",
        cik=320193,
        form_type="10-K",
        filing_date=filing_date,
        accession_number=accession_number,
        primary_document="aapl-20250927.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/x/aapl-20250927.htm",
    )


def _vf(reasoning: str) -> VerifiedFinding:
    return VerifiedFinding(
        finding=Finding(
            item_key="1A", category="substantive_change", tier="high", reasoning=reasoning,
            older_excerpt="old", newer_excerpt="new",
        ),
        excerpt_verified=True,
        confidence=0.85,
        verifier_reasoning="ok",
        final_tier="high",
        classifier_model="m",
        classifier_prompt_version="v1",
        verifier_model="m",
        verifier_prompt_version="v1",
    )


def test_upsert_filing_is_idempotent_on_accession(pg_conn):
    a = upsert_filing(pg_conn, _make_filing())
    b = upsert_filing(pg_conn, _make_filing())
    assert a == b


def test_get_filings_for_ticker_orders_newest_first(pg_conn):
    upsert_filing(pg_conn, _make_filing("A-1", "2024-11-01"))
    upsert_filing(pg_conn, _make_filing("A-2", "2025-11-01"))

    rows = get_filings_for_ticker(pg_conn, "aapl", form_type="10-K", limit=2)

    assert [r["accession_number"] for r in rows] == ["A-2", "A-1"]
    assert rows[0]["filing_date"] == date(2025, 11, 1)


def test_insert_and_read_sections_roundtrip(pg_conn):
    filing_id = upsert_filing(pg_conn, _make_filing())
    insert_sections(pg_conn, filing_id, [
        TaggedSection("1A", "Item 1A.", "Risk text"),
        TaggedSection("7", "Item 7.", "MD&A text"),
    ])
    # Re-inserting replaces rather than duplicates.
    insert_sections(pg_conn, filing_id, [
        TaggedSection("1A", "Item 1A.", "Risk text"),
        TaggedSection("7", "Item 7.", "MD&A text"),
    ])

    rows = get_filing_sections(pg_conn, filing_id)

    assert sorted((r["item_key"], r["heading_text"], r["body_text"]) for r in rows) == [
        ("1A", "Item 1A.", "Risk text"),
        ("7", "Item 7.", "MD&A text"),
    ]


def test_findings_for_pair_returns_only_latest_run(pg_conn):
    older_id = upsert_filing(pg_conn, _make_filing("A-1", "2024-11-01"))
    newer_id = upsert_filing(pg_conn, _make_filing("A-2", "2025-11-01"))
    insert_findings(pg_conn, older_id, newer_id, [_vf("run1-a")])
    pg_conn.execute("UPDATE findings SET created_at = now() - interval '5 minutes'")
    pg_conn.commit()
    insert_findings(pg_conn, older_id, newer_id, [_vf("run2-a"), _vf("run2-b")])

    rows = get_findings_for_filing_pair(pg_conn, older_id, newer_id)

    assert [r["reasoning"] for r in rows] == ["run2-a", "run2-b"]
    assert rows[0]["excerpt_verified"] is True  # native boolean, no coercion


def test_llm_cache_roundtrip_and_do_nothing_on_conflict(pg_conn):
    set_cached(pg_conn, "k", "classify", '{"x": 1}', "m", "v1")
    set_cached(pg_conn, "k", "classify", '{"x": 2}', "m", "v1")

    assert get_cached(pg_conn, "k") == '{"x": 1}'
    assert get_cached(pg_conn, "missing") is None


def test_all_tables_have_rls_enabled(pg_conn):
    # Supabase exposes the public schema over PostgREST to anyone holding
    # the project's anon key. RLS with no policies blocks that path entirely.
    rows = pg_conn.execute(
        """SELECT relname, relrowsecurity FROM pg_class
           WHERE relname IN ('filings', 'sections', 'findings', 'llm_cache')
             AND relkind = 'r'"""
    ).fetchall()
    assert len(rows) == 4
    assert all(r["relrowsecurity"] for r in rows)


def test_init_db_is_idempotent(pg_conn):
    from src.storage.db import init_db

    init_db(pg_conn)
    init_db(pg_conn)
