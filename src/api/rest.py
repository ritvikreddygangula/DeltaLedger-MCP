from fastapi import Depends, FastAPI, HTTPException

from ..storage.db import get_connection
from .queries import get_finding, get_report, list_curated_tickers

app = FastAPI(title="materiality-engine API")


def _get_conn():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/tickers")
def read_tickers(conn=Depends(_get_conn)) -> list[str]:
    return list_curated_tickers(conn)


@app.get("/reports/{ticker}")
def read_report(ticker: str, conn=Depends(_get_conn)) -> dict:
    report = get_report(conn, ticker)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report available for ticker {ticker!r}")
    return report


@app.get("/findings/{finding_id}")
def read_finding(finding_id: int, conn=Depends(_get_conn)) -> dict:
    finding = get_finding(conn, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"No finding with id {finding_id}")
    return finding
