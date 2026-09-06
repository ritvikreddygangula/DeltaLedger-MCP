from src.embeddings.openai_client import get_embeddings


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
