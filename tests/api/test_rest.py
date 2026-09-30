import io
import json
import logging

import pytest
from fastapi.testclient import TestClient

import src.api.rest as rest_module
from src.api.rest import _get_client, app


@pytest.fixture(autouse=True)
def _s3_bucket_env(monkeypatch):
    # queries.py reads S3_BUCKET from the environment when no explicit
    # bucket is passed, same as rest.py's route handlers call it -- every
    # test here needs this set, whether or not it uses the stub client.
    monkeypatch.setenv("S3_BUCKET", "test-bucket")


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

    def head_bucket(self, Bucket):
        return {}


def _override_client(objects):
    def _get():
        return _StubS3Client(objects=objects)

    return _get


def test_read_tickers_returns_list():
    app.dependency_overrides[_get_client] = _override_client({"AAPL.json": {}})
    client = TestClient(app)

    response = client.get("/tickers")

    assert response.status_code == 200
    assert response.json() == ["AAPL"]
    app.dependency_overrides.clear()


def test_cors_header_present_for_cross_origin_frontend():
    # The frontend (S3 + CloudFront) is a different origin than this API
    # (API Gateway), so a real browser fetch() needs this header or it gets
    # silently blocked client-side regardless of the response body.
    app.dependency_overrides[_get_client] = _override_client({"AAPL.json": {}})
    client = TestClient(app)

    response = client.get("/tickers", headers={"Origin": "https://example.cloudfront.net"})

    assert response.headers.get("access-control-allow-origin") == "*"
    app.dependency_overrides.clear()


def test_read_report_returns_404_when_not_found():
    app.dependency_overrides[_get_client] = _override_client({})
    client = TestClient(app)

    response = client.get("/reports/UNKNOWN")

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_read_report_returns_full_report():
    report = {"ticker": "AAPL", "older_filing": {"id": 1}, "newer_filing": {"id": 2}, "findings": [{"id": 10}]}
    app.dependency_overrides[_get_client] = _override_client({"AAPL.json": report})
    client = TestClient(app)

    response = client.get("/reports/AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["findings"] == [{"id": 10}]
    app.dependency_overrides.clear()


def test_read_finding_returns_404_when_not_found():
    app.dependency_overrides[_get_client] = _override_client({})
    client = TestClient(app)

    response = client.get("/findings/999")

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_read_finding_returns_finding():
    report = {"ticker": "AAPL", "findings": [{"id": 5, "item_key": "8"}]}
    app.dependency_overrides[_get_client] = _override_client(
        {"AAPL.json": report, "_index.json": {"5": "AAPL"}}
    )
    client = TestClient(app)

    response = client.get("/findings/5")

    assert response.status_code == 200
    assert response.json()["id"] == 5
    app.dependency_overrides.clear()


def test_health_returns_ok_when_storage_reachable(monkeypatch):
    monkeypatch.setattr(rest_module, "get_client", lambda: _StubS3Client())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "storage": "connected"}


def test_health_returns_503_without_leaking_details_when_storage_unreachable(monkeypatch):
    class _RaisingClient:
        def head_bucket(self, Bucket):
            raise ConnectionError("AccessDenied for arn:aws:iam::123456789012:role/secret-internal-role")

    monkeypatch.setattr(rest_module, "get_client", lambda: _RaisingClient())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "degraded", "storage": "unreachable"}
    assert "secret-internal-role" not in response.text


def test_requests_are_logged_with_method_path_status_and_duration(caplog):
    app.dependency_overrides[_get_client] = _override_client({"AAPL.json": {}})
    client = TestClient(app)

    with caplog.at_level(logging.INFO):
        client.get("/tickers")

    app.dependency_overrides.clear()
    events = [r for r in caplog.records if getattr(r, "fields", {}).get("event") == "http_request"]
    assert len(events) == 1
    fields = events[0].fields
    assert fields["method"] == "GET"
    assert fields["path"] == "/tickers"
    assert fields["status_code"] == 200
    assert "duration_ms" in fields
