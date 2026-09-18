from src.api.queries import get_finding, get_report, list_curated_tickers


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

    def execute(self, query, params=None):
        self.calls.append({"query": query, "params": params})
        value = self._results.pop(0) if self._results else None
        return _StubResult(value)


def test_list_curated_tickers_returns_ticker_strings():
    rows = [{"ticker": "AAPL"}, {"ticker": "LYV"}]
    conn = _StubConnection(results=[rows])

    result = list_curated_tickers(conn)

    assert result == ["AAPL", "LYV"]


def test_get_report_returns_older_and_newer_filing_with_findings():
    filings = [
        {"id": 2, "filing_date": "2025-01-01"},  # newer, first per DESC order
        {"id": 1, "filing_date": "2024-01-01"},  # older
    ]
    findings = [{"id": 10, "item_key": "1A"}]
    conn = _StubConnection(results=[filings, findings])

    result = get_report(conn, "aapl")

    assert result["ticker"] == "AAPL"
    assert result["newer_filing"]["id"] == 2
    assert result["older_filing"]["id"] == 1
    assert result["findings"] == findings
    # get_findings_for_filing_pair called with (older_id, newer_id, older_id, newer_id)
    assert conn.calls[1]["params"] == (1, 2, 1, 2)


def test_get_report_returns_none_when_fewer_than_two_filings():
    conn = _StubConnection(results=[[{"id": 1}]])

    result = get_report(conn, "aapl")

    assert result is None


def test_get_finding_returns_row_when_found():
    conn = _StubConnection(results=[{"id": 5, "item_key": "8"}])

    result = get_finding(conn, 5)

    assert result == {"id": 5, "item_key": "8"}
    assert conn.calls[0]["params"] == (5,)


def test_get_finding_returns_none_when_not_found():
    conn = _StubConnection(results=[None])

    result = get_finding(conn, 999)

    assert result is None
