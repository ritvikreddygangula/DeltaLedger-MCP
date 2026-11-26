import copy
import json

from scripts.import_published_reports import import_reports, load_reports
from src.api.queries import get_report


def _finding(finding_id: int, older_id: int, newer_id: int, item_key: str) -> dict:
    return {
        "id": finding_id,
        "older_filing_id": older_id,
        "newer_filing_id": newer_id,
        "item_key": item_key,
        "category": "substantive_change",
        "tier": "high",
        "reasoning": "Something changed.",
        "older_excerpt": "old",
        "newer_excerpt": None,
        "excerpt_verified": False,
        "confidence": 0.73,
        "verifier_reasoning": "ok",
        "final_tier": "medium",
        "classifier_model": "gpt-5.4-mini",
        "classifier_prompt_version": "v1",
        "verifier_model": "gpt-5.4-mini",
        "verifier_prompt_version": "v1",
        "created_at": "2026-09-10T03:26:47.363182Z",
    }


def _filing(filing_id: int, ticker: str, accession: str, filing_date: str) -> dict:
    return {
        "id": filing_id,
        "cik": 320193,
        "ticker": ticker,
        "form_type": "10-K",
        "filing_date": filing_date,
        "accession_number": accession,
        "source_url": "https://www.sec.gov/x.htm",
        "fetched_at": "2026-09-15T14:24:52.889724Z",
    }


def _report(ticker="AAPL", older_id=7, newer_id=1, finding_ids=(40, 41)) -> dict:
    return {
        "ticker": ticker,
        "older_filing": _filing(older_id, ticker, f"{ticker}-24", "2024-11-01"),
        "newer_filing": _filing(newer_id, ticker, f"{ticker}-25", "2025-10-31"),
        "findings": [_finding(fid, older_id, newer_id, "1A") for fid in finding_ids],
    }


def test_import_round_trips_to_identical_report(pg_conn):
    published = _report()

    import_reports(pg_conn, [copy.deepcopy(published)])

    assert get_report(pg_conn, "AAPL") == published


def test_import_preserves_ids_and_advances_sequences(pg_conn):
    import_reports(pg_conn, [_report(finding_ids=(40, 41))])

    new_id = pg_conn.execute(
        """INSERT INTO filings (cik, ticker, form_type, filing_date, accession_number, source_url, fetched_at)
           VALUES (1, 'X', '10-K', '2025-01-01', 'new-acc', 'u', now()) RETURNING id"""
    ).fetchone()["id"]

    assert new_id > 7  # a freshly ingested filing can't collide with an imported id


def test_import_is_idempotent(pg_conn):
    counts_first = import_reports(pg_conn, [_report()])
    counts_second = import_reports(pg_conn, [_report()])

    assert counts_first == {"filings": 2, "findings": 2}
    assert counts_second == {"filings": 0, "findings": 0}
    assert pg_conn.execute("SELECT count(*) AS n FROM findings").fetchone()["n"] == 2


def test_load_reports_from_jsonl_file(tmp_path):
    path = tmp_path / "reports.jsonl"
    path.write_text(json.dumps(_report("AAPL")) + "\n\n" + json.dumps(_report("KO", 3, 4, (50,))) + "\n")

    reports = load_reports(str(path))

    assert [r["ticker"] for r in reports] == ["AAPL", "KO"]
