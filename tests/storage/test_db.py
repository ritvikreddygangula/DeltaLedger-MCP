from src.agents.classifier import Finding
from src.agents.verifier import VerifiedFinding
from src.connectors.base import FilingMetadata
from src.connectors.section_parser import TaggedSection
from src.storage.db import (
    get_filing_sections,
    get_filings_for_ticker,
    get_findings_for_filing_pair,
    insert_findings,
    insert_sections,
    upsert_filing,
)


class _StubResult:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return self._value

    def fetchall(self):
        return self._value if self._value is not None else []


class _StubCursor:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self._conn.calls.append({"query": query, "params": params})
        return self._conn._pop_result()

    def executemany(self, query, params_seq):
        self._conn.calls.append({"query": query, "params_seq": list(params_seq)})
        return self


class _StubConnection:
    def __init__(self, results=None):
        self.calls = []
        self.committed = False
        self._results = list(results or [])

    def _pop_result(self):
        value = self._results.pop(0) if self._results else None
        return _StubResult(value)

    def execute(self, query, params=None):
        self.calls.append({"query": query, "params": params})
        return self._pop_result()

    def cursor(self):
        return _StubCursor(self)

    def commit(self):
        self.committed = True


def _make_filing(accession_number="0000320193-25-000079") -> FilingMetadata:
    return FilingMetadata(
        ticker="AAPL",
        cik=320193,
        form_type="10-K",
        filing_date="2025-11-01",
        accession_number=accession_number,
        primary_document="aapl-20250927.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
    )


def test_upsert_filing_returns_id_from_returning_clause():
    conn = _StubConnection(results=[{"id": 42}])
    filing = _make_filing()

    filing_id = upsert_filing(conn, filing)

    assert filing_id == 42
    assert conn.committed is True
    call = conn.calls[0]
    assert "INSERT INTO filings" in call["query"]
    assert "ON CONFLICT" in call["query"]
    assert call["params"][4] == filing.accession_number


def test_insert_sections_deletes_then_bulk_inserts():
    conn = _StubConnection()
    sections = [
        TaggedSection(item_key="1A", heading_text="Item 1A.", body_text="Risk text"),
        TaggedSection(item_key="7", heading_text="Item 7.", body_text="MD&A text"),
    ]

    insert_sections(conn, filing_id=7, sections=sections)

    assert conn.committed is True
    delete_call, insert_call = conn.calls
    assert "DELETE FROM sections" in delete_call["query"]
    assert delete_call["params"] == (7,)
    assert "INSERT INTO sections" in insert_call["query"]
    assert insert_call["params_seq"] == [
        (7, "1A", "Item 1A.", "Risk text"),
        (7, "7", "Item 7.", "MD&A text"),
    ]


def test_get_filing_sections_returns_query_result():
    rows = [{"item_key": "1A", "body_text": "Risk text"}]
    conn = _StubConnection(results=[rows])

    result = get_filing_sections(conn, filing_id=7)

    assert result == rows
    assert conn.calls[0]["params"] == (7,)


def test_get_filings_for_ticker_uppercases_and_limits():
    rows = [{"accession_number": "0000320193-25-000079"}]
    conn = _StubConnection(results=[rows])

    result = get_filings_for_ticker(conn, "aapl", form_type="10-K", limit=2)

    assert result == rows
    assert conn.calls[0]["params"] == ("AAPL", "10-K", 2)


def _make_verified_finding(**overrides) -> VerifiedFinding:
    finding = Finding(
        item_key="1A",
        category="substantive_change",
        tier="high",
        reasoning="Something changed.",
        older_excerpt="old text",
        newer_excerpt="new text",
    )
    data = {
        "finding": finding,
        "excerpt_verified": True,
        "confidence": 0.85,
        "verifier_reasoning": "Well supported.",
        "final_tier": "high",
        "classifier_model": "gpt-5.4-mini",
        "classifier_prompt_version": "v1",
        "verifier_model": "gpt-5.4-mini",
        "verifier_prompt_version": "v1",
    }
    data.update(overrides)
    return VerifiedFinding(**data)


def test_insert_findings_bulk_inserts_with_correct_params():
    conn = _StubConnection()
    verified_findings = [_make_verified_finding()]

    insert_findings(conn, older_filing_id=1, newer_filing_id=2, verified_findings=verified_findings)

    assert conn.committed is True
    (insert_call,) = conn.calls
    assert "INSERT INTO findings" in insert_call["query"]
    (params,) = insert_call["params_seq"]
    assert params[0] == 1  # older_filing_id
    assert params[1] == 2  # newer_filing_id
    assert params[2] == "1A"  # item_key
    assert params[3] == "substantive_change"  # category


def test_insert_findings_never_issues_delete():
    conn = _StubConnection()

    insert_findings(
        conn, older_filing_id=1, newer_filing_id=2, verified_findings=[_make_verified_finding()]
    )

    assert not any("DELETE" in call["query"] for call in conn.calls)


def test_get_findings_for_filing_pair_returns_query_result():
    rows = [{"id": 1, "item_key": "1A", "category": "substantive_change"}]
    conn = _StubConnection(results=[rows])

    result = get_findings_for_filing_pair(conn, older_filing_id=1, newer_filing_id=2)

    assert result == rows
    assert conn.calls[0]["params"] == (1, 2, 1, 2)
