from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ..storage.db import get_connection
from .queries import get_finding, get_report, list_curated_tickers

mcp = MCPServer("materiality-engine")


@mcp.tool()
def list_tickers() -> list[str]:
    """Lists the curated tickers with cached materiality analysis available."""
    conn = get_connection()
    try:
        return list_curated_tickers(conn)
    finally:
        conn.close()


@mcp.tool()
def get_materiality_report(ticker: str) -> dict[str, Any]:
    """Returns the cached materiality analysis comparing a curated ticker's
    two most recent 10-K filings: both filings plus every finding (category,
    materiality tier, reasoning, confidence, and source excerpts).
    """
    conn = get_connection()
    try:
        report = get_report(conn, ticker)
        if report is None:
            raise ToolError(f"No report available for ticker {ticker!r}")
        return report
    finally:
        conn.close()


@mcp.tool()
def get_finding_citation(finding_id: int) -> dict[str, Any]:
    """Returns a single finding's full detail (source citation, confidence,
    reasoning) by its id.
    """
    conn = get_connection()
    try:
        finding = get_finding(conn, finding_id)
        if finding is None:
            raise ToolError(f"No finding with id {finding_id}")
        return finding
    finally:
        conn.close()
