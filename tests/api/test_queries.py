import io
import json

from src.api.queries import get_finding, get_report, list_curated_tickers


class _NoSuchKey(Exception):
    pass


class _StubExceptions:
    NoSuchKey = _NoSuchKey


class _StubS3Client:
    exceptions = _StubExceptions

    def __init__(self, objects: dict | None = None):
        self._objects = objects or {}  # key -> already-JSON-serializable value

    def list_objects_v2(self, Bucket):
        return {"Contents": [{"Key": k} for k in self._objects]}

    def get_object(self, Bucket, Key):
        if Key not in self._objects:
            raise self.exceptions.NoSuchKey()
        body = json.dumps(self._objects[Key]).encode("utf-8")
        return {"Body": io.BytesIO(body)}


def test_list_curated_tickers_strips_json_suffix_and_sorts():
    client = _StubS3Client(objects={"LYV.json": {}, "AAPL.json": {}})

    result = list_curated_tickers(client, bucket="test-bucket")

    assert result == ["AAPL", "LYV"]


def test_list_curated_tickers_excludes_underscore_prefixed_keys():
    # _index.json is metadata, not a ticker report.
    client = _StubS3Client(objects={"AAPL.json": {}, "_index.json": {"1": "AAPL"}})

    result = list_curated_tickers(client, bucket="test-bucket")

    assert result == ["AAPL"]


def test_get_report_returns_published_report():
    report = {"ticker": "AAPL", "older_filing": {}, "newer_filing": {}, "findings": [{"id": 10}]}
    client = _StubS3Client(objects={"AAPL.json": report})

    result = get_report(client, "aapl", bucket="test-bucket")

    assert result == report


def test_get_report_returns_none_when_not_published():
    client = _StubS3Client(objects={})

    result = get_report(client, "unknown", bucket="test-bucket")

    assert result is None


def test_get_finding_looks_up_ticker_via_index_then_finds_it_in_that_report():
    report = {
        "ticker": "AAPL",
        "findings": [{"id": 10, "item_key": "1A"}, {"id": 11, "item_key": "3"}],
    }
    client = _StubS3Client(objects={"AAPL.json": report, "_index.json": {"10": "AAPL", "11": "AAPL"}})

    result = get_finding(client, 11, bucket="test-bucket")

    assert result == {"id": 11, "item_key": "3"}


def test_get_finding_returns_none_when_id_not_in_index():
    client = _StubS3Client(objects={"_index.json": {"10": "AAPL"}})

    result = get_finding(client, 999, bucket="test-bucket")

    assert result is None


def test_get_finding_returns_none_when_index_missing_entirely():
    client = _StubS3Client(objects={})

    result = get_finding(client, 10, bucket="test-bucket")

    assert result is None
