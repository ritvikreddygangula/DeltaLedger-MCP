from fastapi.testclient import TestClient

from src.api.lambda_handler import app
from src.api.rest import _get_conn
from src.api.rest import app as rest_app


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


def _override_conn(results):
    def _get():
        yield _StubConnection(results=results)

    return _get


def test_rest_and_mcp_both_reachable_through_combined_app():
    # Both assertions have to share one TestClient/lifespan context: the MCP
    # SDK's session manager refuses a second .run() call on the same
    # instance for the life of the process, and `mcp` (and therefore its
    # session manager) is a module-level singleton shared by the whole test
    # session -- a second `with TestClient(app)` block in another test
    # function would crash with "can only be called once per instance".
    #
    # Overrides must go on `rest_app` (the mounted sub-app), not the
    # combined `app` -- confirmed empirically: setting it on `app` still hit
    # the real get_connection() and blew up on a missing DATABASE_URL,
    # because a Mount delegates straight to the sub-app's own DI container.
    rest_app.dependency_overrides[_get_conn] = _override_conn([[{"ticker": "AAPL"}]])

    with TestClient(app, base_url="http://localhost:8000") as client:
        rest_response = client.get("/api/tickers")

        # mcp_app registers its own route at "/mcp" internally (confirmed by
        # inspecting mcp_app.routes), so it's mounted at "/" in
        # lambda_handler.py rather than "/mcp" -- otherwise this would 404 on
        # a doubled-up "/mcp/mcp" path. A bare GET against "/mcp" isn't a
        # meaningful check here since MCP's own routing 404s on non-protocol
        # requests regardless of whether the mount is wired correctly; a
        # real initialize call is the only way to prove the mount resolves.
        mcp_response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )

    rest_app.dependency_overrides.clear()

    assert rest_response.status_code == 200
    assert rest_response.json() == ["AAPL"]

    assert mcp_response.status_code == 200
    assert mcp_response.json()["result"]["serverInfo"]["name"] == "materiality-engine"
