import json

from src.api.queries import get_finding, get_report, list_curated_tickers


def test_list_tickers_excludes_single_filing_ticker(seeded_conn):
    assert list_curated_tickers(seeded_conn) == ["AAPL"]


def test_list_tickers_empty_database(pg_conn):
    assert list_curated_tickers(pg_conn) == []


def test_get_report_is_case_insensitive(seeded_conn):
    assert get_report(seeded_conn, "aapl")["ticker"] == "AAPL"


def test_get_report_returns_none_for_unknown_or_single_filing(seeded_conn):
    assert get_report(seeded_conn, "ZZZZ") is None
    assert get_report(seeded_conn, "LYV") is None


def test_get_report_orders_newer_and_older(seeded_conn):
    report = get_report(seeded_conn, "AAPL")

    assert report["newer_filing"]["filing_date"] == "2025-11-01"
    assert report["older_filing"]["filing_date"] == "2024-11-01"
    assert [f["item_key"] for f in report["findings"]] == ["1A", "7"]


def test_get_report_values_are_json_strings(seeded_conn):
    report = get_report(seeded_conn, "AAPL")

    json.dumps(report)  # must not raise on date/datetime
    assert isinstance(report["newer_filing"]["fetched_at"], str)
    assert isinstance(report["findings"][0]["created_at"], str)
    assert report["findings"][0]["excerpt_verified"] is True


def test_timestamps_are_utc_with_z_suffix_like_the_old_api(seeded_conn):
    # The previous S3-published JSON used "2026-09-15T14:24:52.889724Z".
    # Keep that exact format so existing consumers see no change.
    seeded_conn.execute("SET TIME ZONE 'America/Phoenix'")  # result must not depend on session tz
    seeded_conn.execute(
        "UPDATE filings SET fetched_at = '2026-09-15T14:24:52.889724Z' WHERE ticker = 'AAPL'"
    )

    report = get_report(seeded_conn, "AAPL")

    assert report["newer_filing"]["fetched_at"] == "2026-09-15T14:24:52.889724Z"


def test_get_finding_by_id(seeded_conn):
    finding_id = get_report(seeded_conn, "AAPL")["findings"][1]["id"]

    finding = get_finding(seeded_conn, finding_id)

    assert finding["id"] == finding_id
    assert finding["item_key"] == "7"
    json.dumps(finding)


def test_get_finding_missing_or_out_of_range(seeded_conn):
    assert get_finding(seeded_conn, 999_999) is None
    assert get_finding(seeded_conn, 0) is None
    assert get_finding(seeded_conn, 2**70) is None  # beyond BIGINT, must not raise
