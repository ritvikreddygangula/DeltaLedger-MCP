from contextlib import contextmanager

import pytest

from src.agents.classifier import Finding
from src.agents.verifier import VerifiedFinding
from src.connectors.base import FilingMetadata
from src.storage.db import insert_findings, upsert_filing


def _filing(ticker: str, accession: str, filing_date: str) -> FilingMetadata:
    return FilingMetadata(
        ticker=ticker,
        cik=1,
        form_type="10-K",
        filing_date=filing_date,
        accession_number=accession,
        primary_document="x.htm",
        source_url="https://example.com/x.htm",
    )


def _vf(item_key: str) -> VerifiedFinding:
    return VerifiedFinding(
        finding=Finding(
            item_key=item_key, category="substantive_change", tier="high",
            reasoning="Something changed.", older_excerpt="old", newer_excerpt="new",
        ),
        excerpt_verified=True,
        confidence=0.9,
        verifier_reasoning="Well supported.",
        final_tier="high",
        classifier_model="gpt-5.4-mini",
        classifier_prompt_version="v1",
        verifier_model="gpt-5.4-mini",
        verifier_prompt_version="v1",
    )


@pytest.fixture
def seeded_conn(pg_conn):
    """AAPL: two 10-Ks with two findings (items 1A, 7). LYV: only one 10-K,
    so it has no report and must not show up as a curated ticker."""
    older = upsert_filing(pg_conn, _filing("AAPL", "0000000000-24-000001", "2024-11-01"))
    newer = upsert_filing(pg_conn, _filing("AAPL", "0000000000-25-000001", "2025-11-01"))
    insert_findings(pg_conn, older, newer, [_vf("1A"), _vf("7")])
    upsert_filing(pg_conn, _filing("LYV", "0000000001-25-000001", "2025-02-01"))
    return pg_conn


@pytest.fixture
def patch_connection(monkeypatch):
    """Points a module's db_pool.connection() at a given test connection
    instead of the real pool."""

    def _patch(module, conn):
        @contextmanager
        def _connection():
            yield conn

        monkeypatch.setattr(module, "connection", _connection)

    return _patch
