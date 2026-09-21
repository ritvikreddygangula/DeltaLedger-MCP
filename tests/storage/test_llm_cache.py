from src.storage.llm_cache import compute_cache_key, get_cached, set_cached


class _StubResult:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return self._value


class _StubConnection:
    def __init__(self, results=None):
        self.calls = []
        self.committed = False
        self._results = list(results or [])

    def execute(self, query, params=None):
        self.calls.append({"query": query, "params": params})
        value = self._results.pop(0) if self._results else None
        return _StubResult(value)

    def commit(self):
        self.committed = True


def test_compute_cache_key_is_deterministic():
    assert compute_cache_key(kind="classify", a="x") == compute_cache_key(kind="classify", a="x")


def test_compute_cache_key_differs_on_different_input():
    assert compute_cache_key(kind="classify", a="x") != compute_cache_key(kind="classify", a="y")


def test_get_cached_returns_none_when_missing():
    conn = _StubConnection(results=[None])
    assert get_cached(conn, "somekey") is None


def test_get_cached_returns_stored_output():
    conn = _StubConnection(results=[{"output_json": '{"x": 1}'}])
    assert get_cached(conn, "somekey") == '{"x": 1}'


def test_set_cached_inserts_with_on_conflict_do_nothing():
    conn = _StubConnection()
    set_cached(conn, "somekey", "classify", '{"x": 1}', "gpt-5.4-mini", "v1")
    assert conn.committed is True
    call = conn.calls[0]
    assert "ON CONFLICT" in call["query"]
    assert call["params"][0] == "somekey"
