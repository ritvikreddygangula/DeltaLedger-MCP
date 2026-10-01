import json
import sqlite3

from scripts.export_to_s3 import export_all
from src.agents.classifier import Finding
from src.agents.verifier import VerifiedFinding
from src.connectors.base import FilingMetadata
from src.storage.db import get_connection, init_db, insert_findings, upsert_filing


class _StubS3Client:
    def __init__(self):
        self.put_calls = []

    def put_object(self, Bucket, Key, Body, ContentType):
        self.put_calls.append({"bucket": Bucket, "key": Key, "body": json.loads(Body), "content_type": ContentType})


def _filing(ticker, accession, filing_date) -> FilingMetadata:
    return FilingMetadata(
        ticker=ticker,
        cik=1,
        form_type="10-K",
        filing_date=filing_date,
        accession_number=accession,
        primary_document="x.htm",
        source_url="https://example.com/x.htm",
    )


def _verified_finding(item_key="1A") -> VerifiedFinding:
    finding = Finding(
        item_key=item_key,
        category="substantive_change",
        tier="high",
        reasoning="Something changed.",
        older_excerpt="old",
        newer_excerpt="new",
    )
    return VerifiedFinding(
        finding=finding,
        excerpt_verified=True,
        confidence=0.9,
        verifier_reasoning="Well supported.",
        final_tier="high",
        classifier_model="gpt-5.4-mini",
        classifier_prompt_version="v1",
        verifier_model="gpt-5.4-mini",
        verifier_prompt_version="v1",
    )


def _seeded_conn(ticker="AAPL", n_findings=2) -> sqlite3.Connection:
    conn = get_connection(":memory:")
    init_db(conn)
    older_id = upsert_filing(conn, _filing(ticker, "0000000000-24-000001", "2024-01-01"))
    newer_id = upsert_filing(conn, _filing(ticker, "0000000000-25-000001", "2025-01-01"))
    insert_findings(
        conn,
        older_filing_id=older_id,
        newer_filing_id=newer_id,
        verified_findings=[_verified_finding(f"item{i}") for i in range(n_findings)],
    )
    return conn


def test_export_all_uploads_one_json_file_per_ticker():
    conn = _seeded_conn(ticker="AAPL", n_findings=2)
    s3 = _StubS3Client()

    export_all(conn, s3, "test-bucket", ["AAPL"])

    assert len(s3.put_calls) == 1
    call = s3.put_calls[0]
    assert call["bucket"] == "test-bucket"
    assert call["key"] == "AAPL.json"
    assert call["content_type"] == "application/json"
    assert call["body"]["ticker"] == "AAPL"
    assert len(call["body"]["findings"]) == 2


def test_export_all_returns_finding_id_to_ticker_index():
    conn = _seeded_conn(ticker="AAPL", n_findings=2)
    s3 = _StubS3Client()

    index = export_all(conn, s3, "test-bucket", ["AAPL"])

    assert len(index) == 2
    assert all(ticker == "AAPL" for ticker in index.values())


def test_export_all_skips_ticker_with_no_report_without_crashing():
    conn = _seeded_conn(ticker="AAPL", n_findings=1)
    s3 = _StubS3Client()

    index = export_all(conn, s3, "test-bucket", ["AAPL", "NONEXISTENT"])

    assert len(s3.put_calls) == 1  # only AAPL actually uploaded
    assert len(index) == 1


def test_export_all_handles_multiple_tickers_independently():
    conn = _seeded_conn(ticker="AAPL", n_findings=1)
    # Add a second, independent ticker to the same connection.
    older_id = upsert_filing(conn, _filing("MSFT", "0000000001-24-000001", "2024-02-01"))
    newer_id = upsert_filing(conn, _filing("MSFT", "0000000001-25-000001", "2025-02-01"))
    insert_findings(
        conn, older_filing_id=older_id, newer_filing_id=newer_id, verified_findings=[_verified_finding()]
    )
    s3 = _StubS3Client()

    index = export_all(conn, s3, "test-bucket", ["AAPL", "MSFT"])

    uploaded_keys = {call["key"] for call in s3.put_calls}
    assert uploaded_keys == {"AAPL.json", "MSFT.json"}
    assert set(index.values()) == {"AAPL", "MSFT"}
