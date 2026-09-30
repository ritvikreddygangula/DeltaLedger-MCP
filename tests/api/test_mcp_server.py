import io
import json
import logging

import pytest
from mcp import Client

import src.api.mcp_server as mcp_server_module
from src.api.mcp_server import mcp


class _NoSuchKey(Exception):
    pass


class _StubExceptions:
    NoSuchKey = _NoSuchKey


class _StubS3Client:
    exceptions = _StubExceptions

    def __init__(self, objects: dict | None = None):
        self._objects = objects or {}

    def list_objects_v2(self, Bucket):
        return {"Contents": [{"Key": k} for k in self._objects]}

    def get_object(self, Bucket, Key):
        if Key not in self._objects:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(json.dumps(self._objects[Key]).encode("utf-8"))}


def _patch_client(monkeypatch, objects):
    client = _StubS3Client(objects=objects)
    monkeypatch.setattr(mcp_server_module, "get_client", lambda: client)
    return client


@pytest.fixture(autouse=True)
def _s3_bucket_env(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "test-bucket")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_list_tickers_tool(monkeypatch):
    _patch_client(monkeypatch, objects={"AAPL.json": {}})

    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("list_tickers", {})

    assert result.structured_content["result"] == ["AAPL"]


@pytest.mark.anyio
async def test_tool_calls_are_logged_with_timing(monkeypatch, caplog):
    _patch_client(monkeypatch, objects={"AAPL.json": {}})

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
    report = {"ticker": "AAPL", "older_filing": {"id": 1}, "newer_filing": {"id": 2}, "findings": [{"id": 10}]}
    _patch_client(monkeypatch, objects={"AAPL.json": report})

    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("get_materiality_report", {"ticker": "aapl"})

    assert result.structured_content["ticker"] == "AAPL"


@pytest.mark.anyio
async def test_get_materiality_report_tool_error_when_not_found(monkeypatch):
    _patch_client(monkeypatch, objects={})

    async with Client(mcp, raise_exceptions=False) as client:
        result = await client.call_tool("get_materiality_report", {"ticker": "UNKNOWN"})

    assert result.is_error is True
    assert "No report available" in result.content[0].text


@pytest.mark.anyio
async def test_get_finding_citation_tool_returns_finding(monkeypatch):
    report = {"ticker": "AAPL", "findings": [{"id": 5, "item_key": "8"}]}
    _patch_client(monkeypatch, objects={"AAPL.json": report, "_index.json": {"5": "AAPL"}})

    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("get_finding_citation", {"finding_id": 5})

    assert result.structured_content["id"] == 5


@pytest.mark.anyio
async def test_get_finding_citation_tool_error_when_not_found(monkeypatch):
    _patch_client(monkeypatch, objects={})

    async with Client(mcp, raise_exceptions=False) as client:
        result = await client.call_tool("get_finding_citation", {"finding_id": 999})

    assert result.is_error is True
    assert "No finding with id 999" in result.content[0].text
