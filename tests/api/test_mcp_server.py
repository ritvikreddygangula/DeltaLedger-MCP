import json
import logging

import pytest
from mcp import Client

import src.api.mcp_server as mcp_server_module
from src.api.mcp_server import mcp


@pytest.fixture
def seeded(seeded_conn, patch_connection):
    patch_connection(mcp_server_module, seeded_conn)
    return seeded_conn


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_list_tickers_tool(seeded):

    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("list_tickers", {})

    assert result.structured_content["result"] == ["AAPL"]


@pytest.mark.anyio
async def test_tool_calls_are_logged_with_timing(seeded, caplog):

    with caplog.at_level(logging.INFO):
        async with Client(mcp, raise_exceptions=True) as client:
            await client.call_tool("list_tickers", {})

    events = [r for r in caplog.records if getattr(r, "fields", {}).get("event") == "mcp_tool_call"]
    assert len(events) == 1
    assert events[0].fields["tool"] == "list_tickers"
    assert events[0].fields["ticker_count"] == 1
    assert "duration_ms" in events[0].fields


@pytest.mark.anyio
async def test_get_materiality_report_tool_returns_report(seeded):

    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("get_materiality_report", {"ticker": "aapl"})

    report = result.structured_content
    assert report["ticker"] == "AAPL"
    # Dates must reach the MCP client as the same ISO strings REST returns.
    assert report["newer_filing"]["filing_date"] == "2025-11-01"
    assert isinstance(report["findings"][0]["created_at"], str)
    json.dumps(report)


@pytest.mark.anyio
async def test_get_materiality_report_tool_error_when_not_found(seeded):

    async with Client(mcp, raise_exceptions=False) as client:
        result = await client.call_tool("get_materiality_report", {"ticker": "UNKNOWN"})

    assert result.is_error is True
    assert "No report available" in result.content[0].text


@pytest.mark.anyio
async def test_get_finding_citation_tool_returns_finding(seeded):
    finding_id = seeded.execute("SELECT min(id) AS id FROM findings").fetchone()["id"]

    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("get_finding_citation", {"finding_id": finding_id})

    assert result.structured_content["id"] == finding_id
    assert isinstance(result.structured_content["created_at"], str)


@pytest.mark.anyio
async def test_get_finding_citation_tool_error_when_not_found(seeded):

    async with Client(mcp, raise_exceptions=False) as client:
        result = await client.call_tool("get_finding_citation", {"finding_id": 999999})

    assert result.is_error is True
    assert "No finding with id 999999" in result.content[0].text
