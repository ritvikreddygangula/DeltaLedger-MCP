"""Manual end-to-end verification -- NOT run in CI (needs a real DATABASE_URL
pointing at Postgres with data already ingested via scripts/ingest_ticker.py,
and a real OPENAI_API_KEY). Runs the Part 3 LangGraph pipeline (currently
just the "align" node) and prints matched pairs plus any new/removed
sections as distinct findings.

Usage: uv run python -m scripts.align_filing AAPL
"""

import sys

from dotenv import load_dotenv

from src.agents.graph import build_graph
from src.storage.db import get_connection, get_filing_sections, get_filings_for_ticker


def main(ticker: str) -> None:
    load_dotenv()
    conn = get_connection()
    filings = get_filings_for_ticker(conn, ticker, form_type="10-K", limit=2)
    if len(filings) < 2:
        conn.close()
        raise SystemExit(
            f"Need 2 ingested 10-Ks for {ticker!r}, found {len(filings)}. "
            "Run scripts/ingest_ticker.py first."
        )
    older, newer = sorted(filings, key=lambda f: f["filing_date"])

    older_sections = get_filing_sections(conn, older["id"])
    newer_sections = get_filing_sections(conn, newer["id"])
    conn.close()

    graph = build_graph()
    result = graph.invoke(
        {"older_sections": older_sections, "newer_sections": newer_sections}
    )

    print(
        f"{older['accession_number']} ({older['filing_date']}) -> "
        f"{newer['accession_number']} ({newer['filing_date']})"
    )
    for alignment in result["alignments"]:
        if alignment.status == "matched":
            print(
                f"  MATCHED  Item {alignment.older_section['item_key']} -> "
                f"Item {alignment.newer_section['item_key']}  "
                f"score={alignment.similarity:.4f}"
            )
        elif alignment.status == "removed":
            print(
                f"  REMOVED  Item {alignment.older_section['item_key']} "
                f"({alignment.older_section['heading_text']!r}) -- no match in newer filing"
            )
        else:
            print(
                f"  NEW      Item {alignment.newer_section['item_key']} "
                f"({alignment.newer_section['heading_text']!r}) -- not present in older filing"
            )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "AAPL")
