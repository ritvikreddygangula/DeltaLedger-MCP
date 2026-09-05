from src.connectors.base import FilingMetadata
from src.connectors.section_parser import TaggedSection
from src.storage.db import (
    get_connection,
    get_filing_sections,
    init_db,
    insert_sections,
    upsert_filing,
)


def _make_filing(accession_number="0000320193-25-000079") -> FilingMetadata:
    return FilingMetadata(
        ticker="AAPL",
        cik=320193,
        form_type="10-K",
        filing_date="2025-11-01",
        accession_number=accession_number,
        primary_document="aapl-20250927.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
    )


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def test_upsert_filing_is_idempotent():
    conn = _conn()
    filing = _make_filing()

    first_id = upsert_filing(conn, filing)
    second_id = upsert_filing(conn, filing)

    assert first_id == second_id
    count = conn.execute("SELECT COUNT(*) AS n FROM filings").fetchone()["n"]
    assert count == 1


def test_insert_and_get_filing_sections_round_trip():
    conn = _conn()
    filing_id = upsert_filing(conn, _make_filing())
    sections = [
        TaggedSection(item_key="1A", heading_text="Item 1A.", body_text="Risk text"),
        TaggedSection(item_key="7", heading_text="Item 7.", body_text="MD&A text"),
    ]

    insert_sections(conn, filing_id, sections)
    rows = get_filing_sections(conn, filing_id)

    assert {r["item_key"] for r in rows} == {"1A", "7"}
    assert {r["body_text"] for r in rows} == {"Risk text", "MD&A text"}


def test_insert_sections_replaces_previous_sections_for_same_filing():
    conn = _conn()
    filing_id = upsert_filing(conn, _make_filing())

    insert_sections(
        conn, filing_id, [TaggedSection(item_key="1A", heading_text="h", body_text="old")]
    )
    insert_sections(
        conn, filing_id, [TaggedSection(item_key="1A", heading_text="h", body_text="new")]
    )

    rows = get_filing_sections(conn, filing_id)
    assert len(rows) == 1
    assert rows[0]["body_text"] == "new"


def test_deleting_filing_cascades_to_sections():
    conn = _conn()
    filing_id = upsert_filing(conn, _make_filing())
    insert_sections(
        conn, filing_id, [TaggedSection(item_key="1A", heading_text="h", body_text="b")]
    )

    conn.execute("DELETE FROM filings WHERE id = ?", (filing_id,))
    conn.commit()

    rows = get_filing_sections(conn, filing_id)
    assert rows == []
