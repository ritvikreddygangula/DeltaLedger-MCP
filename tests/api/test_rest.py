from fastapi.testclient import TestClient

from src.api.rest import _get_conn, app


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


def test_read_tickers_returns_list():
    app.dependency_overrides[_get_conn] = _override_conn([[{"ticker": "AAPL"}]])
    client = TestClient(app)

    response = client.get("/tickers")

    assert response.status_code == 200
    assert response.json() == ["AAPL"]
    app.dependency_overrides.clear()


def test_cors_header_present_for_cross_origin_frontend():
    # The frontend (S3 + CloudFront) is a different origin than this API
    # (API Gateway), so a real browser fetch() needs this header or it gets
    # silently blocked client-side regardless of the response body.
    app.dependency_overrides[_get_conn] = _override_conn([[{"ticker": "AAPL"}]])
    client = TestClient(app)

    response = client.get("/tickers", headers={"Origin": "https://example.cloudfront.net"})

    assert response.headers.get("access-control-allow-origin") == "*"
    app.dependency_overrides.clear()


def test_read_report_returns_404_when_not_found():
    app.dependency_overrides[_get_conn] = _override_conn([[{"id": 1}]])  # only 1 filing
    client = TestClient(app)

    response = client.get("/reports/UNKNOWN")

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_read_report_returns_full_report():
    filings = [
        {"id": 2, "filing_date": "2025-01-01"},
        {"id": 1, "filing_date": "2024-01-01"},
    ]
    findings = [{"id": 10, "item_key": "1A"}]
    app.dependency_overrides[_get_conn] = _override_conn([filings, findings])
    client = TestClient(app)

    response = client.get("/reports/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["findings"] == findings
    app.dependency_overrides.clear()


def test_read_finding_returns_404_when_not_found():
    app.dependency_overrides[_get_conn] = _override_conn([None])
    client = TestClient(app)

    response = client.get("/findings/999")

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_read_finding_returns_finding():
    app.dependency_overrides[_get_conn] = _override_conn([{"id": 5, "item_key": "8"}])
    client = TestClient(app)

    response = client.get("/findings/5")

    assert response.status_code == 200
    assert response.json()["id"] == 5
    app.dependency_overrides.clear()
