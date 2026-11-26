import json

from fastapi.testclient import TestClient

import src.api.mcp_server as mcp_server_module
import src.api.rest as rest_module
from src.api.app import app

_MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    },
}


def test_rest_and_mcp_both_served_from_one_app_across_requests(seeded_conn, patch_connection):
    # Several requests through one running app (one lifespan), across both
    # mounts. This is the shape uvicorn runs on Render.
    patch_connection(rest_module, seeded_conn)
    patch_connection(mcp_server_module, seeded_conn)

    with TestClient(app) as client:
        first = client.get("/api/tickers")
        second = client.get("/api/tickers")
        report = client.get("/api/reports/aapl")
        mcp_init = client.post("/mcp", headers=_MCP_HEADERS, content=json.dumps(_INITIALIZE))

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == ["AAPL"]
    assert report.status_code == 200
    assert report.json()["newer_filing"]["filing_date"] == "2025-11-01"
    assert mcp_init.status_code == 200
    assert mcp_init.json()["result"]["serverInfo"]["name"] == "materiality-engine"
