"""Manual end-to-end verification -- NOT run in CI (needs a real DATABASE_URL
pointing at Postgres with data already ingested via scripts/ingest_ticker.py,
and a real OPENAI_API_KEY). Embeds both filings' sections and prints each
older-filing section's best cross-filing match by cosine similarity.

Usage: uv run python -m scripts.compare_sections AAPL
"""

import sys

import numpy as np
from dotenv import load_dotenv

from src.embeddings.openai_client import get_embeddings
from src.embeddings.similarity import cosine_similarity_matrix
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

    older_vectors = get_embeddings([s["body_text"] for s in older_sections])
    newer_vectors = get_embeddings([s["body_text"] for s in newer_sections])

    similarity = cosine_similarity_matrix(older_vectors, newer_vectors)

    print(
        f"{older['accession_number']} ({older['filing_date']}) -> "
        f"{newer['accession_number']} ({newer['filing_date']})"
    )
    for i, section in enumerate(older_sections):
        best_j = int(np.argmax(similarity[i]))
        match = newer_sections[best_j]
        print(
            f"  Item {section['item_key']} ({section['heading_text']!r}) best matches "
            f"Item {match['item_key']} ({match['heading_text']!r}) "
            f"score={similarity[i, best_j]:.4f}"
        )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "AAPL")
