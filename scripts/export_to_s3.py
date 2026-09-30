"""Exports each curated ticker's report -- exactly the shape get_report()
already returns -- to S3 as one {ticker}.json per ticker, plus a small
_index.json ({finding_id: ticker}) so get_finding_citation() can look up a
single finding without scanning every ticker's file. See
docs/DROP_RDS_SPEC.md.

Run this any time you want to republish current data: after run_pipeline.py
computes new findings for a ticker, or as a one-time migration of everything
already in the local database.

Usage: uv run python -m scripts.export_to_s3 BUCKET_NAME [TICKER ...]
       (omit tickers to export every curated ticker)
"""

import sys

from dotenv import load_dotenv

from src.storage.db import (
    get_connection,
    get_filings_for_ticker,
    get_findings_for_filing_pair,
)
from src.storage.s3_store import get_client, put_json


def _list_all_tickers(conn) -> list[str]:
    rows = conn.execute("SELECT DISTINCT ticker FROM filings ORDER BY ticker").fetchall()
    return [row["ticker"] for row in rows]


def _build_report(conn, ticker: str) -> dict | None:
    """Reads straight from the local SQLite DB that scripts/run_pipeline.py
    writes to -- this is the one-time/each-time bridge from local storage to
    the published S3 report; src/api/queries.py (what the live API reads)
    no longer touches SQLite at all once this script has run.
    """
    filings = get_filings_for_ticker(conn, ticker, form_type="10-K", limit=2)
    if len(filings) < 2:
        return None
    newer, older = filings[0], filings[1]  # get_filings_for_ticker orders DESC by filing_date
    findings = get_findings_for_filing_pair(conn, older["id"], newer["id"])
    return {
        "ticker": ticker.upper(),
        "older_filing": older,
        "newer_filing": newer,
        "findings": findings,
    }


def export_all(conn, s3_client, bucket: str, tickers: list[str]) -> dict[int, str]:
    """Exports each ticker's report, returns the finding_id -> ticker index
    built along the way (not yet uploaded -- the caller uploads it once,
    after every ticker has succeeded, so a partial run never leaves a stale
    index pointing at reports that were never written).
    """
    index: dict[int, str] = {}
    for ticker in tickers:
        report = _build_report(conn, ticker)
        if report is None:
            print(f"{ticker}: no report available, skipped")
            continue
        put_json(s3_client, bucket, f"{ticker}.json", report)
        for finding in report["findings"]:
            index[finding["id"]] = ticker
        print(f"{ticker}: exported {len(report['findings'])} findings")
    return index


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python -m scripts.export_to_s3 BUCKET_NAME [TICKER ...]")
        sys.exit(1)

    load_dotenv()
    bucket = sys.argv[1]
    conn = get_connection()
    tickers = sys.argv[2:] or _list_all_tickers(conn)

    s3_client = get_client()
    index = export_all(conn, s3_client, bucket, tickers)
    put_json(s3_client, bucket, "_index.json", index)

    print(f"\n{len(index)} finding(s) indexed across {len(tickers)} ticker(s) -> s3://{bucket}")


if __name__ == "__main__":
    main()
