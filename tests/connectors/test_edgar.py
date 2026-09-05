import pytest

from src.connectors.edgar import EDGARConnector, TickerNotFoundError


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
