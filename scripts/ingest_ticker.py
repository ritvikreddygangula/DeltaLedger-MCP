"""Manual end-to-end verification -- NOT run in CI (needs real network + a
real EDGAR_USER_AGENT in .env). Pulls the two most recent 10-Ks for a ticker,
parses their sections, and writes both into the local SQLite DB.

Usage: uv run python scripts/ingest_ticker.py AAPL
"""

import sys

from dotenv import load_dotenv

from src.connectors.edgar import EDGARConnector
from src.connectors.section_parser import parse_10k_sections
from src.storage.db import get_connection, init_db, insert_sections, upsert_filing


def main(ticker: str) -> None:
    load_dotenv()
    connector = EDGARConnector()
    filings = connector.get_recent_filings(ticker, form_type="10-K", count=2)

    conn = get_connection()
    init_db(conn)

    for filing in filings:
        html = connector.fetch_filing_document(filing)
        sections = parse_10k_sections(html)
        filing_id = upsert_filing(conn, filing)
        insert_sections(conn, filing_id, sections)
        print(
            f"{filing.accession_number} ({filing.filing_date}): "
            f"tagged {[s.item_key for s in sections]}"
        )

    conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "AAPL")
