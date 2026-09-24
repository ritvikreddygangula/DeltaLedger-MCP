import logging

import pytest
from mcp import Client

import src.api.mcp_server as mcp_server_module
from src.api.mcp_server import mcp


class _StubResult:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return self._value

    def fetchall(self):
        return self._value if self._value is not None else []


class _StubConnection:
    def __init__(self, results=None):
        self.calls = []
        self._results = list(results or [])
        self.closed = False

    def execute(self, query, params=None):
        self.calls.append({"query": query, "params": params})
        value = self._results.pop(0) if self._results else None
        return _StubResult(value)

    def close(self):
        self.closed = True


def _patch_connection(monkeypatch, results):
    conn = _StubConnection(results=results)
    monkeypatch.setattr(mcp_server_module, "get_connection", lambda: conn)
    return conn


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_list_tickers_tool(monkeypatch):
    _patch_connection(monkeypatch, results=[[{"ticker": "AAPL"}]])

    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("list_tickers", {})

    assert result.structured_content["result"] == ["AAPL"]


@pytest.mark.anyio
async def test_tool_calls_are_logged_with_timing(monkeypatch, caplog):
    _patch_connection(monkeypatch, results=[[{"ticker": "AAPL"}]])

    with caplog.at_level(logging.INFO):
        async with Client(mcp, raise_exceptions=True) as client:
            await client.call_tool("list_tickers", {})

    events = [r for r in caplog.records if getattr(r, "fields", {}).get("event") == "mcp_tool_call"]
    assert len(events) == 1
    assert events[0].fields["tool"] == "list_tickers"
    assert events[0].fields["ticker_count"] == 1
    assert "duration_ms" in events[0].fields


@pytest.mark.anyio
async def test_get_materiality_report_tool_returns_report(monkeypatch):
    filings = [
        {"id": 2, "filing_date": "2025-01-01"},
        {"id": 1, "filing_date": "2024-01-01"},
    ]
    findings = [{"id": 10, "item_key": "1A"}]
    conn = _patch_connection(monkeypatch, results=[filings, findings])

    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("get_materiality_report", {"ticker": "aapl"})

    assert result.structured_content["ticker"] == "AAPL"
    assert conn.closed is True


@pytest.mark.anyio
async def test_get_materiality_report_tool_error_when_not_found(monkeypatch):
    _patch_connection(monkeypatch, results=[[{"id": 1}]])  # only 1 filing found

    async with Client(mcp, raise_exceptions=False) as client:
        result = await client.call_tool("get_materiality_report", {"ticker": "UNKNOWN"})

    assert result.is_error is True
    assert "No report available" in result.content[0].text


@pytest.mark.anyio
async def test_get_finding_citation_tool_returns_finding(monkeypatch):
    _patch_connection(monkeypatch, results=[{"id": 5, "item_key": "8"}])

    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("get_finding_citation", {"finding_id": 5})

    assert result.structured_content["id"] == 5


@pytest.mark.anyio
async def test_get_finding_citation_tool_error_when_not_found(monkeypatch):
    _patch_connection(monkeypatch, results=[None])

    async with Client(mcp, raise_exceptions=False) as client:
        result = await client.call_tool("get_finding_citation", {"finding_id": 999})

    assert result.is_error is True
    assert "No finding with id 999" in result.content[0].text
