"""One-time migration: copies every published report (filings + findings)
from the old AWS deployment into Postgres, keeping every id, so finding ids
already cited elsewhere keep resolving to the same evidence.

The source is either the old public API base URL (reads /tickers and
/reports/{ticker}, no AWS credentials needed) or a JSONL backup with one
report per line, e.g. data/published_reports_backup.jsonl.

Sections and the LLM cache were never published, so they aren't imported.
Sections can be re-fetched free with scripts/ingest_ticker.py (upsert by
accession number keeps the imported filing ids).

After importing, every report is read back through the API's own
get_report() and compared to the source. Exits non-zero on any mismatch.

Usage:
  uv run python -m scripts.import_published_reports https://<old-api>/api
  uv run python -m scripts.import_published_reports data/published_reports_backup.jsonl
"""

import json
import sys
import urllib.request

import psycopg
from dotenv import load_dotenv

from src.api.queries import get_report
from src.storage.db import get_connection, init_db

_FILING_COLUMNS = [
    "id", "cik", "ticker", "form_type", "filing_date", "accession_number", "source_url", "fetched_at",
]
_FINDING_COLUMNS = [
    "id", "older_filing_id", "newer_filing_id", "item_key", "category", "tier", "reasoning",
    "older_excerpt", "newer_excerpt", "excerpt_verified", "confidence", "verifier_reasoning",
    "final_tier", "classifier_model", "classifier_prompt_version", "verifier_model",
    "verifier_prompt_version", "created_at",
]


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 -- operator-supplied URL
        return json.loads(resp.read())


def load_reports(source: str) -> list[dict]:
    if source.startswith(("http://", "https://")):
        base = source.rstrip("/")
        return [_get_json(f"{base}/reports/{t}") for t in _get_json(f"{base}/tickers")]
    with open(source) as f:
        return [json.loads(line) for line in f if line.strip()]


def _insert(conn: psycopg.Connection, table: str, columns: list[str], row: dict) -> int:
    placeholders = ", ".join(["%s"] * len(columns))
    cur = conn.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
        [row[c] for c in columns],
    )
    return cur.rowcount


def import_reports(conn: psycopg.Connection, reports: list[dict]) -> dict[str, int]:
    """Returns how many rows were newly inserted per table (0 on a re-run)."""
    inserted = {"filings": 0, "findings": 0}
    for report in reports:
        for key in ("older_filing", "newer_filing"):
            inserted["filings"] += _insert(conn, "filings", _FILING_COLUMNS, report[key])
        for finding in report["findings"]:
            inserted["findings"] += _insert(conn, "findings", _FINDING_COLUMNS, finding)
    # Explicit ids don't advance identity sequences. Without this, the next
    # pipeline run would try id=1 and collide with an imported row.
    for table in ("filings", "findings"):
        conn.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(max(id), 1)) FROM {table}"
        )
    conn.commit()
    return inserted


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    load_dotenv()
    reports = load_reports(sys.argv[1])
    conn = get_connection()
    init_db(conn)
    inserted = import_reports(conn, reports)
    print(f"Loaded {len(reports)} report(s); newly inserted: {inserted}")

    mismatched = [r["ticker"] for r in reports if get_report(conn, r["ticker"]) != r]
    conn.close()
    if mismatched:
        print(f"MISMATCH after import for: {mismatched}")
        sys.exit(1)
    print(f"Verified: all {len(reports)} report(s) read back identical to the source.")


if __name__ == "__main__":
    main()
