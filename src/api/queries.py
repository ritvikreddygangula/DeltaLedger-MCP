from datetime import date, datetime

import psycopg

from ..storage.db import get_filings_for_ticker, get_findings_for_filing_pair


def _jsonable(row: dict) -> dict:
    """Postgres hands back date/datetime objects, but the public API's
    contract (and the old S3-published JSON) has them as ISO strings. FastAPI
    would serialize them on its own, but MCP tool results go through a
    different serializer, so normalize once here and both surfaces return
    exactly the same shape.
    """
    return {k: v.isoformat() if isinstance(v, (date, datetime)) else v for k, v in row.items()}


def list_curated_tickers(conn: psycopg.Connection) -> list[str]:
    """'Curated' means every ticker the offline pipeline has ingested at
    least two 10-Ks for, i.e. everything get_report() can actually answer.
    There's no separate allowlist to maintain. The set only grows through
    the CLI scripts, never through this API.
    """
    rows = conn.execute(
        """SELECT ticker FROM filings WHERE form_type = '10-K'
           GROUP BY ticker HAVING count(*) >= 2 ORDER BY ticker"""
    ).fetchall()
    return [r["ticker"] for r in rows]


def get_report(conn: psycopg.Connection, ticker: str) -> dict | None:
    """Returns the two most recent 10-Ks for a ticker plus the latest pipeline
    run's findings for that pair, or None if fewer than two are ingested.
    """
    filings = get_filings_for_ticker(conn, ticker, form_type="10-K", limit=2)
    if len(filings) < 2:
        return None
    newer, older = filings[0], filings[1]  # get_filings_for_ticker orders DESC by filing_date
    findings = get_findings_for_filing_pair(conn, older["id"], newer["id"])
    return {
        "ticker": ticker.upper(),
        "older_filing": _jsonable(older),
        "newer_filing": _jsonable(newer),
        "findings": [_jsonable(f) for f in findings],
    }


def get_finding(conn: psycopg.Connection, finding_id: int) -> dict | None:
    """Any finding by id, including ones from earlier pipeline runs. A
    finding id is a citation, and findings are append-only, so an id someone
    quoted keeps resolving to the same evidence.
    """
    if not 0 < finding_id < 2**63:  # outside BIGINT: Postgres would raise, not just miss
        return None
    row = conn.execute("SELECT * FROM findings WHERE id = %s", (finding_id,)).fetchone()
    return _jsonable(row) if row else None
