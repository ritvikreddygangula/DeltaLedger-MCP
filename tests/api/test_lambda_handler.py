import json

from src.api.lambda_handler import handler
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


def _api_gateway_v2_event(method: str, path: str, body: str | None = None, headers: dict | None = None) -> dict:
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": headers or {},
        "requestContext": {
            "http": {"method": method, "path": path, "sourceIp": "127.0.0.1"},
        },
        "body": body,
        "isBase64Encoded": False,
    }


def test_handler_survives_multiple_invocations_on_a_warm_container():
    # Regression test for a real production bug: Mangum's "auto"/"on"
    # lifespan modes re-run the ASGI lifespan protocol on EVERY invocation
    # (a fresh LifespanCycle is built inside Mangum.__call__), but
    # StreamableHTTPSessionManager.run() can only be entered once per
    # instance, ever. Confirmed live via CloudWatch logs after deploying
    # with the naive `Mangum(app, lifespan="auto")`: the first request on a
    # warm Lambda container succeeded, and every request after it on that
    # same container crashed with "StreamableHTTPSessionManager .run() can
    # only be called once per instance". A TestClient(app)-based test (the
    # original version of this test) never caught this, because TestClient
    # exercises uvicorn-style lifespan semantics (run once for the whole
    # process), not Mangum's per-invocation semantics -- this test instead
    # calls the actual `handler()` entry point multiple times, simulating
    # several requests hitting the same warm container, against both the
    # REST and MCP mounts.
    rest_app.dependency_overrides[_get_conn] = _override_conn([[{"ticker": "AAPL"}]])

    response_1 = handler(_api_gateway_v2_event("GET", "/api/tickers"), object())
    response_2 = handler(_api_gateway_v2_event("GET", "/api/tickers"), object())

    rest_app.dependency_overrides.clear()

    assert response_1["statusCode"] == 200
    assert json.loads(response_1["body"]) == ["AAPL"]
    assert response_2["statusCode"] == 200
    assert json.loads(response_2["body"]) == ["AAPL"]

    mcp_event = _api_gateway_v2_event(
        "POST",
        "/mcp",
        body=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
        ),
        headers={
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
            "host": "localhost:8000",
        },
    )
    mcp_response = handler(mcp_event, object())

    assert mcp_response["statusCode"] == 200
    mcp_body = json.loads(mcp_response["body"])
    assert mcp_body["result"]["serverInfo"]["name"] == "materiality-engine"
