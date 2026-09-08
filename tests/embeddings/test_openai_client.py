import tiktoken

from src.embeddings.openai_client import MAX_INPUT_TOKENS, get_embeddings


class _StubEmbeddingData:
    def __init__(self, embedding, index):
        self.embedding = embedding
        self.index = index


class _StubEmbeddingResponse:
    def __init__(self, data):
        self.data = data


class _StubEmbeddings:
    def __init__(self, vectors_by_input):
        self._vectors_by_input = vectors_by_input
        self.calls = []

    def create(self, model, input):
        self.calls.append({"model": model, "input": input})
        data = [
            _StubEmbeddingData(self._vectors_by_input[text], i)
            for i, text in enumerate(input)
        ]
        return _StubEmbeddingResponse(data)


class _StubOpenAIClient:
    def __init__(self, vectors_by_input):
        self.embeddings = _StubEmbeddings(vectors_by_input)


class _RecordingEmbeddings:
    """Records whatever input text is actually sent, without needing to know
    it in advance -- used to test truncation, where the exact truncated
    string isn't known ahead of time."""

    def __init__(self):
        self.calls = []

    def create(self, model, input):
        self.calls.append({"model": model, "input": input})
        data = [_StubEmbeddingData([0.0], i) for i in range(len(input))]
        return _StubEmbeddingResponse(data)


class _RecordingClient:
    def __init__(self):
        self.embeddings = _RecordingEmbeddings()


def test_get_embeddings_returns_vectors_in_input_order():
    client = _StubOpenAIClient(
        vectors_by_input={"hello": [0.1, 0.2], "world": [0.3, 0.4]}
    )

    vectors = get_embeddings(["hello", "world"], client=client)

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_get_embeddings_sends_correct_model_and_input():
    client = _StubOpenAIClient(vectors_by_input={"hello": [0.1, 0.2]})

    get_embeddings(["hello"], client=client)

    call = client.embeddings.calls[0]
    assert call["model"] == "text-embedding-3-small"
    assert call["input"] == ["hello"]


def test_get_embeddings_reorders_by_response_index():
    # Simulate a response returning results out of input order -- the
    # function should still return vectors matching the ORIGINAL input order.
    client = _StubOpenAIClient(vectors_by_input={"a": [1.0], "b": [2.0]})
    out_of_order_data = [
        _StubEmbeddingData([2.0], index=1),
        _StubEmbeddingData([1.0], index=0),
    ]
    client.embeddings.create = lambda model, input: _StubEmbeddingResponse(
        out_of_order_data
    )

    vectors = get_embeddings(["a", "b"], client=client)

    assert vectors == [[1.0], [2.0]]


def test_long_text_is_truncated_to_token_limit():
    encoding = tiktoken.encoding_for_model("text-embedding-3-small")
    long_text = "risk factor sentence. " * 5000  # comfortably over 8192 tokens
    client = _RecordingClient()

    get_embeddings([long_text], client=client)

    sent_text = client.embeddings.calls[0]["input"][0]
    assert len(encoding.encode(sent_text)) <= MAX_INPUT_TOKENS
    assert len(sent_text) < len(long_text)


def test_short_text_is_not_truncated():
    client = _RecordingClient()

    get_embeddings(["short text"], client=client)

    assert client.embeddings.calls[0]["input"][0] == "short text"
