from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ..observability import get_logger, timed
from ..storage.s3_store import get_client
from .queries import get_finding, get_report, list_curated_tickers

logger = get_logger(__name__)

mcp = MCPServer("materiality-engine")


@mcp.tool()
def list_tickers() -> list[str]:
    """Lists the curated tickers with cached materiality analysis available."""
    with timed(logger, "mcp_tool_call", tool="list_tickers") as extra:
        client = get_client()
        result = list_curated_tickers(client)
        extra["ticker_count"] = len(result)
        return result


@mcp.tool()
def get_materiality_report(ticker: str) -> dict[str, Any]:
    """Returns the cached materiality analysis comparing a curated ticker's
    two most recent 10-K filings: both filings plus every finding (category,
    materiality tier, reasoning, confidence, and source excerpts).
    """
    with timed(logger, "mcp_tool_call", tool="get_materiality_report", ticker=ticker) as extra:
        client = get_client()
        report = get_report(client, ticker)
        extra["found"] = report is not None
        if report is None:
            raise ToolError(f"No report available for ticker {ticker!r}")
        return report


@mcp.tool()
def get_finding_citation(finding_id: int) -> dict[str, Any]:
    """Returns a single finding's full detail (source citation, confidence,
    reasoning) by its id.
    """
    with timed(logger, "mcp_tool_call", tool="get_finding_citation", finding_id=finding_id) as extra:
        client = get_client()
        finding = get_finding(client, finding_id)
        extra["found"] = finding is not None
        if finding is None:
            raise ToolError(f"No finding with id {finding_id}")
        return finding
