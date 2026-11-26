import logging
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import src.api.rest as rest_module
from src.api.rest import _get_conn, app


@pytest.fixture
def client(seeded_conn):
    app.dependency_overrides[_get_conn] = lambda: seeded_conn
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_read_tickers_returns_list(client):
    response = client.get("/tickers")

    assert response.status_code == 200
    assert response.json() == ["AAPL"]


def test_cors_header_present_for_cross_origin_frontend(client):
    # The frontend (Vercel) is a different origin than this API (Render), so
    # a real browser fetch() needs this header or it gets silently blocked
    # client-side regardless of the response body.
    response = client.get("/tickers", headers={"Origin": "https://example.vercel.app"})

    assert response.headers.get("access-control-allow-origin") == "*"


def test_read_report_returns_404_when_not_found(client):
    assert client.get("/reports/UNKNOWN").status_code == 404
    assert client.get("/reports/LYV").status_code == 404  # only one 10-K ingested


def test_read_report_returns_full_report(client):
    response = client.get("/reports/aapl")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert set(body) == {"ticker", "older_filing", "newer_filing", "findings"}
    assert [f["item_key"] for f in body["findings"]] == ["1A", "7"]
    assert body["newer_filing"]["filing_date"] == "2025-11-01"


def test_read_finding_returns_404_when_not_found(client):
    assert client.get("/findings/999999").status_code == 404


def test_read_finding_returns_finding(client):
    finding_id = client.get("/reports/AAPL").json()["findings"][0]["id"]

    response = client.get(f"/findings/{finding_id}")

    assert response.status_code == 200
    assert response.json()["id"] == finding_id


def test_health_returns_ok_when_db_reachable(monkeypatch, seeded_conn):
    @contextmanager
    def _connection():
        yield seeded_conn

    monkeypatch.setattr(rest_module, "connection", _connection)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "storage": "connected"}


def test_health_returns_503_when_db_unreachable(monkeypatch):
    @contextmanager
    def _connection():
        raise ConnectionError(
            "connection to server at db.secret-ref.supabase.co failed: password authentication failed"
        )
        yield  # pragma: no cover

    monkeypatch.setattr(rest_module, "connection", _connection)

    response = TestClient(app).get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "storage": "unreachable"}
    assert "secret-ref" not in response.text


def test_health_returns_503_when_database_url_missing(monkeypatch):
    # The real pool path, not a stub: a missing DATABASE_URL must degrade
    # the health check, not crash the request.
    import src.api.db_pool as db_pool

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db_pool, "_pool", None)

    response = TestClient(app).get("/health")

    assert response.status_code == 503


def test_requests_are_logged_with_method_path_status_and_duration(client, caplog):
    with caplog.at_level(logging.INFO):
        client.get("/tickers")

    events = [r for r in caplog.records if getattr(r, "fields", {}).get("event") == "http_request"]
    assert len(events) == 1
    fields = events[0].fields
    assert fields["method"] == "GET"
    assert fields["path"] == "/tickers"
    assert fields["status_code"] == 200
    assert "duration_ms" in fields
