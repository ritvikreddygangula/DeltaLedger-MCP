"""Manual end-to-end verification -- NOT run in CI (needs a real DATABASE_URL
pointing at Postgres with data already ingested via scripts/ingest_ticker.py,
and a real OPENAI_API_KEY -- this makes real, billed OpenAI chat calls for
both classification and verification). Runs the full align+classify+verify
LangGraph pipeline, prints the alignment report plus every finding's
classification AND verification result, then persists everything to the
`findings` table -- this is the first script in the project that writes its
own output back to the database, not just filings/sections.

Usage: uv run python -m scripts.run_pipeline AAPL
"""

import sys

from dotenv import load_dotenv

from src.agents.graph import build_graph
from src.storage.db import (
    get_connection,
    get_filing_sections,
    get_filings_for_ticker,
    insert_findings,
)


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

    verified_findings = result["verified_findings"]
    print(f"\n{len(verified_findings)} finding(s) after verification:")
    for vf in verified_findings:
        finding = vf.finding
        tier_note = (
            f"{finding.tier} -> {vf.final_tier}" if finding.tier != vf.final_tier else finding.tier
        )
        print(f"\n  [{tier_note.upper()}] Item {finding.item_key} -- {finding.category}")
        print(f"    classifier: {finding.reasoning}")
        print(
            f"    verifier (confidence={vf.confidence:.2f}, "
            f"excerpt_verified={vf.excerpt_verified}): {vf.verifier_reasoning}"
        )
        if finding.older_excerpt:
            print(f'    OLDER: "{finding.older_excerpt}"')
        if finding.newer_excerpt:
            print(f'    NEWER: "{finding.newer_excerpt}"')

    insert_findings(conn, older["id"], newer["id"], verified_findings)
    conn.close()

    unverified = sum(1 for vf in verified_findings if not vf.excerpt_verified)
    print(
        f"\nPersisted {len(verified_findings)} finding(s) to Postgres "
        f"({unverified} failed excerpt verification)."
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "AAPL")
