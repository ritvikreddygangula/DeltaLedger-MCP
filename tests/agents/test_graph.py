from src.agents.classifier import Finding
from src.agents.graph import build_graph


def _section(item_key: str, body_text: str = "") -> dict:
    return {"item_key": item_key, "heading_text": f"Item {item_key}.", "body_text": body_text}


def _no_op_classify(alignment):
    """Fake classify_fn for tests that only care about the align step --
    must be passed explicitly everywhere, since build_graph's real default
    would otherwise make a live OpenAI call the moment classify runs."""
    return []


def test_graph_flows_state_through_align_node():
    embeddings_by_text = {"older text": [1.0, 0.0], "newer text": [1.0, 0.0]}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embeddings_by_text[t] for t in texts]

    graph = build_graph(embed_fn=fake_embed, classify_fn=_no_op_classify)
    result = graph.invoke(
        {
            "older_sections": [_section("1A", "older text")],
            "newer_sections": [_section("1A", "newer text")],
        }
    )

    assert len(result["alignments"]) == 1
    alignment = result["alignments"][0]
    assert alignment.status == "matched"
    assert alignment.older_section["item_key"] == "1A"
    assert alignment.newer_section["item_key"] == "1A"


def test_graph_respects_custom_threshold():
    embeddings_by_text = {"a": [1.0, 0.0], "b": [0.8, 0.6]}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embeddings_by_text[t] for t in texts]

    graph = build_graph(embed_fn=fake_embed, classify_fn=_no_op_classify, threshold=0.9)
    result = graph.invoke(
        {
            "older_sections": [_section("1A", "a")],
            "newer_sections": [_section("1A", "b")],
        }
    )

    # similarity(a, b) = 0.8, below the 0.9 threshold passed to build_graph
    assert {a.status for a in result["alignments"]} == {"removed", "new"}


def test_graph_never_imports_real_openai_client():
    calls = []

    def fake_embed(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        return [[1.0, 0.0] for _ in texts]

    graph = build_graph(embed_fn=fake_embed, classify_fn=_no_op_classify)
    graph.invoke(
        {
            "older_sections": [_section("1A", "x")],
            "newer_sections": [_section("1A", "y")],
        }
    )

    assert calls == [["x"], ["y"]]


def test_graph_flows_alignments_into_classify_node():
    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    classify_calls = []

    def fake_classify(alignment):
        classify_calls.append(alignment)
        return [
            Finding(
                item_key=(alignment.older_section or alignment.newer_section)["item_key"],
                category="other",
                tier="low",
                reasoning="stub reasoning",
                older_excerpt=None,
                newer_excerpt=None,
            )
        ]

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify)
    result = graph.invoke(
        {
            "older_sections": [_section("1A", "x")],
            "newer_sections": [_section("1A", "y")],
        }
    )

    assert len(classify_calls) == 1
    assert classify_calls[0].status == "matched"
    assert len(result["classifications"]) == 1
    assert result["classifications"][0].item_key == "1A"


def test_classify_node_flattens_findings_across_multiple_alignments():
    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def fake_classify(alignment):
        item_key = (alignment.older_section or alignment.newer_section)["item_key"]
        return [
            Finding(
                item_key=item_key,
                category="other",
                tier="low",
                reasoning="stub",
                older_excerpt=None,
                newer_excerpt=None,
            )
        ]

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify)
    result = graph.invoke(
        {
            "older_sections": [_section("1A", "x"), _section("3", "y")],
            "newer_sections": [_section("1A", "x2"), _section("3", "y2")],
        }
    )

    assert len(result["alignments"]) == 2
    assert {f.item_key for f in result["classifications"]} == {"1A", "3"}


def test_graph_never_imports_real_openai_client_for_classify_either():
    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    classify_calls = []

    def fake_classify(alignment):
        classify_calls.append(alignment)
        return []

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify)
    graph.invoke(
        {
            "older_sections": [_section("1A", "x")],
            "newer_sections": [_section("1A", "y")],
        }
    )

    assert len(classify_calls) == 1
