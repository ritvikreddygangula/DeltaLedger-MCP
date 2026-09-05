import pytest

from src.connectors.base import FilingMetadata
from src.connectors.edgar import (
    EDGARConnector,
    NoFilingsFoundError,
    TickerNotFoundError,
)


class _StubResponse:
    def __init__(self, json_data=None, text=""):
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


class _StubSession:
    def __init__(self, responses_by_url):
        self._responses_by_url = responses_by_url
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        return self._responses_by_url[url]


TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

SAMPLE_TICKER_MAP = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
}


def test_resolve_cik_happy_path():
    session = _StubSession({TICKER_MAP_URL: _StubResponse(json_data=SAMPLE_TICKER_MAP)})
    connector = EDGARConnector(user_agent="Test test@example.com", session=session)

    cik = connector.resolve_cik("aapl")

    assert cik == 320193


def test_resolve_cik_not_found():
    session = _StubSession({TICKER_MAP_URL: _StubResponse(json_data=SAMPLE_TICKER_MAP)})
    connector = EDGARConnector(user_agent="Test test@example.com", session=session)

    with pytest.raises(TickerNotFoundError):
        connector.resolve_cik("NOPE")


def test_resolve_cik_caches_ticker_map():
    session = _StubSession({TICKER_MAP_URL: _StubResponse(json_data=SAMPLE_TICKER_MAP)})
    connector = EDGARConnector(user_agent="Test test@example.com", session=session)

    connector.resolve_cik("AAPL")
    connector.resolve_cik("MSFT")

    assert len(session.calls) == 1


def test_get_sends_user_agent_header():
    session = _StubSession({TICKER_MAP_URL: _StubResponse(json_data=SAMPLE_TICKER_MAP)})
    connector = EDGARConnector(user_agent="Test test@example.com", session=session)

    connector.resolve_cik("AAPL")

    assert session.calls[0]["headers"] == {"User-Agent": "Test test@example.com"}


def test_missing_user_agent_raises(monkeypatch):
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)

    with pytest.raises(RuntimeError):
        EDGARConnector()


SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0000320193.json"


def _submissions_response(recent_filings: dict, files: list | None = None):
    return _StubResponse(
        json_data={"filings": {"recent": recent_filings, "files": files or []}}
    )


def _connector_with(session) -> EDGARConnector:
    return EDGARConnector(user_agent="Test test@example.com", session=session)


def test_get_recent_filings_happy_path():
    recent = {
        "form": ["10-K", "10-Q", "10-K", "10-K"],
        "filingDate": ["2025-11-01", "2025-08-01", "2024-11-01", "2023-11-01"],
        "accessionNumber": [
            "0000320193-25-000079",
            "0000320193-25-000050",
            "0000320193-24-000079",
            "0000320193-23-000079",
        ],
        "primaryDocument": [
            "aapl-20250927.htm",
            "aapl-20250628.htm",
            "aapl-20240928.htm",
            "aapl-20230930.htm",
        ],
    }
    session = _StubSession(
        {
            TICKER_MAP_URL: _StubResponse(json_data=SAMPLE_TICKER_MAP),
            SUBMISSIONS_URL: _submissions_response(recent),
        }
    )
    connector = _connector_with(session)

    filings = connector.get_recent_filings("AAPL", form_type="10-K", count=2)

    assert [f.filing_date for f in filings] == ["2025-11-01", "2024-11-01"]
    assert filings[0].accession_number == "0000320193-25-000079"
    assert filings[0].source_url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019325000079/aapl-20250927.htm"
    )


def test_get_recent_filings_falls_back_to_paginated_files():
    recent = {
        "form": ["10-K"],
        "filingDate": ["2025-11-01"],
        "accessionNumber": ["0000320193-25-000079"],
        "primaryDocument": ["aapl-20250927.htm"],
    }
    older_page_url = "https://data.sec.gov/submissions/CIK0000320193-submissions-001.json"
    older_page = {
        "form": ["10-K"],
        "filingDate": ["2024-11-01"],
        "accessionNumber": ["0000320193-24-000079"],
        "primaryDocument": ["aapl-20240928.htm"],
    }
    session = _StubSession(
        {
            TICKER_MAP_URL: _StubResponse(json_data=SAMPLE_TICKER_MAP),
            SUBMISSIONS_URL: _submissions_response(
                recent, files=[{"name": "CIK0000320193-submissions-001.json"}]
            ),
            older_page_url: _StubResponse(json_data=older_page),
        }
    )
    connector = _connector_with(session)

    filings = connector.get_recent_filings("AAPL", form_type="10-K", count=2)

    assert [f.filing_date for f in filings] == ["2025-11-01", "2024-11-01"]


def test_get_recent_filings_raises_when_not_enough_found():
    recent = {
        "form": ["10-K"],
        "filingDate": ["2025-11-01"],
        "accessionNumber": ["0000320193-25-000079"],
        "primaryDocument": ["aapl-20250927.htm"],
    }
    session = _StubSession(
        {
            TICKER_MAP_URL: _StubResponse(json_data=SAMPLE_TICKER_MAP),
            SUBMISSIONS_URL: _submissions_response(recent),
        }
    )
    connector = _connector_with(session)

    with pytest.raises(NoFilingsFoundError):
        connector.get_recent_filings("AAPL", form_type="10-K", count=2)


def test_fetch_filing_document_returns_text_and_sends_user_agent():
    filing = FilingMetadata(
        ticker="AAPL",
        cik=320193,
        form_type="10-K",
        filing_date="2025-11-01",
        accession_number="0000320193-25-000079",
        primary_document="aapl-20250927.htm",
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019325000079/aapl-20250927.htm"
        ),
    )
    session = _StubSession({filing.source_url: _StubResponse(text="<html>10-K body</html>")})
    connector = _connector_with(session)

    html = connector.fetch_filing_document(filing)

    assert html == "<html>10-K body</html>"
    assert session.calls[0]["url"] == filing.source_url
    assert session.calls[0]["headers"] == {"User-Agent": "Test test@example.com"}
