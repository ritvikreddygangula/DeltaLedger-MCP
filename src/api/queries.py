from ..storage.db import get_filings_for_ticker, get_findings_for_filing_pair


def list_curated_tickers(conn) -> list[str]:
    """'Curated' = 'whatever's already been ingested' -- no separate
    hardcoded allowlist to maintain. Expanding the curated set happens by
    running the existing CLI scripts, never through this API.
    """
    rows = conn.execute("SELECT DISTINCT ticker FROM filings ORDER BY ticker").fetchall()
    return [row["ticker"] for row in rows]


def get_report(conn, ticker: str) -> dict | None:
    """Returns the two most recent 10-Ks for a ticker plus every finding for
    that pair, or None if fewer than 2 filings have been ingested. Does not
    include alignment status (MATCHED/REMOVED/NEW) -- that was never
    persisted to Postgres, only printed by the CLI scripts; a documented
    known limitation, not silently worked around.
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


def get_finding(conn, finding_id: int) -> dict | None:
    return conn.execute(
        "SELECT * FROM findings WHERE id = %s", (finding_id,)
    ).fetchone()
