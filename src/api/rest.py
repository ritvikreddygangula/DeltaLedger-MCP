import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..observability import get_logger, log_event
from ..storage.db import get_connection
from .queries import get_finding, get_report, list_curated_tickers

logger = get_logger(__name__)

app = FastAPI(title="materiality-engine API")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    log_event(
        logger, "http_request",
        method=request.method, path=request.url.path,
        status_code=response.status_code, duration_ms=duration_ms,
    )
    return response

# The frontend (S3 + CloudFront) is a different origin than this API
# (API Gateway), so the browser enforces CORS on every fetch() call from it.
# Wide open on purpose: every route here is an unauthenticated GET against
# public SEC filing analysis, no cookies/credentials involved, so there's no
# session or secret a hostile origin could ride on -- same public/read-only
# reasoning already applied to the RDS security group and the MCP
# transport's DNS-rebinding protection.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _get_conn():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/health")
def health() -> JSONResponse:
    """Deliberately doesn't use the _get_conn dependency -- that assumes a
    successful connection and lets a DB failure surface as an unhandled 500.
    A health check's whole job is to report that failure cleanly instead.
    The raw exception is logged server-side only; the public response stays
    generic so it doesn't hand a stranger infrastructure details (hostnames,
    driver internals) for free.
    """
    try:
        conn = get_connection()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except Exception:
        logger.exception("health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unreachable"})
    return JSONResponse(status_code=200, content={"status": "ok", "database": "connected"})


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
