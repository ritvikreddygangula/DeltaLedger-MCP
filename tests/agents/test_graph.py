from src.agents.graph import build_graph


def _section(item_key: str, body_text: str = "") -> dict:
    return {"item_key": item_key, "heading_text": f"Item {item_key}.", "body_text": body_text}


def test_graph_flows_state_through_align_node():
    embeddings_by_text = {"older text": [1.0, 0.0], "newer text": [1.0, 0.0]}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embeddings_by_text[t] for t in texts]

    graph = build_graph(embed_fn=fake_embed)
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

    graph = build_graph(embed_fn=fake_embed, threshold=0.9)
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

    graph = build_graph(embed_fn=fake_embed)
    graph.invoke(
        {
            "older_sections": [_section("1A", "x")],
            "newer_sections": [_section("1A", "y")],
        }
    )

    assert calls == [["x"], ["y"]]
