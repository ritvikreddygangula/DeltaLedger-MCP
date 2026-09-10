from src.agents.classifier import Finding
from src.agents.graph import build_graph
from src.agents.verifier import VerifiedFinding


def _section(item_key: str, body_text: str = "") -> dict:
    return {"item_key": item_key, "heading_text": f"Item {item_key}.", "body_text": body_text}


def _no_op_classify(alignment):
    """Fake classify_fn for tests that only care about earlier steps --
    must be passed explicitly everywhere, since build_graph's real default
    would otherwise make a live OpenAI call the moment classify runs."""
    return []


def _no_op_verify(findings, alignment):
    """Fake verify_fn (batched signature), same reasoning as
    _no_op_classify -- must be passed explicitly everywhere, since
    build_graph's real default would otherwise make a live OpenAI call the
    moment verify runs."""
    return [
        VerifiedFinding(
            finding=finding,
            excerpt_verified=True,
            confidence=1.0,
            verifier_reasoning="stub",
            final_tier=finding.tier,
            classifier_model="stub",
            classifier_prompt_version="stub",
            verifier_model="stub",
            verifier_prompt_version="stub",
        )
        for finding in findings
    ]


def test_graph_flows_state_through_align_node():
    embeddings_by_text = {"older text": [1.0, 0.0], "newer text": [1.0, 0.0]}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [embeddings_by_text[t] for t in texts]

    graph = build_graph(embed_fn=fake_embed, classify_fn=_no_op_classify, verify_fn=_no_op_verify)
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

    graph = build_graph(
        embed_fn=fake_embed, classify_fn=_no_op_classify, verify_fn=_no_op_verify, threshold=0.9
    )
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

    graph = build_graph(embed_fn=fake_embed, classify_fn=_no_op_classify, verify_fn=_no_op_verify)
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

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify, verify_fn=_no_op_verify)
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

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify, verify_fn=_no_op_verify)
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

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify, verify_fn=_no_op_verify)
    graph.invoke(
        {
            "older_sections": [_section("1A", "x")],
            "newer_sections": [_section("1A", "y")],
        }
    )

    assert len(classify_calls) == 1


def test_graph_flows_classified_pairs_into_verify_node():
    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def fake_classify(alignment):
        return [
            Finding(
                item_key=(alignment.older_section or alignment.newer_section)["item_key"],
                category="other",
                tier="high",
                reasoning="stub",
                older_excerpt=None,
                newer_excerpt=None,
            )
        ]

    verify_calls = []

    def fake_verify(findings, alignment):
        verify_calls.append((findings, alignment))
        return [
            VerifiedFinding(
                finding=f,
                excerpt_verified=True,
                confidence=0.5,
                verifier_reasoning="stub",
                final_tier="medium",
                classifier_model="m",
                classifier_prompt_version="v1",
                verifier_model="m",
                verifier_prompt_version="v1",
            )
            for f in findings
        ]

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify, verify_fn=fake_verify)
    result = graph.invoke(
        {
            "older_sections": [_section("1A", "x")],
            "newer_sections": [_section("1A", "y")],
        }
    )

    assert len(verify_calls) == 1
    called_findings, called_alignment = verify_calls[0]
    assert len(called_findings) == 1
    assert called_findings[0].item_key == "1A"
    assert called_alignment.status == "matched"
    assert len(result["verified_findings"]) == 1
    assert result["verified_findings"][0].final_tier == "medium"


def test_multiple_findings_for_one_alignment_are_batched_into_a_single_verify_call():
    # The whole point of batching: one alignment producing several findings
    # should hit verify_fn exactly once (with all of them together), not
    # once per finding -- this is what actually removes the redundant
    # resending of a section's full text that motivated this change.
    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def fake_classify(alignment):
        item_key = (alignment.older_section or alignment.newer_section)["item_key"]
        return [
            Finding(
                item_key=item_key,
                category="other",
                tier="low",
                reasoning=f"finding {i}",
                older_excerpt=None,
                newer_excerpt=None,
            )
            for i in range(3)
        ]

    verify_calls = []

    def fake_verify(findings, alignment):
        verify_calls.append(findings)
        return _no_op_verify(findings, alignment)

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify, verify_fn=fake_verify)
    result = graph.invoke(
        {
            "older_sections": [_section("1A", "x")],
            "newer_sections": [_section("1A", "y")],
        }
    )

    assert len(verify_calls) == 1  # one batched call, not three
    assert len(verify_calls[0]) == 3
    assert len(result["verified_findings"]) == 3


def test_classified_pairs_correlates_finding_to_correct_alignment_when_item_keys_collide():
    # Two independent alignments sharing the same item_key -- a real
    # scenario when a Hungarian-forced pairing falls below threshold and
    # the older/newer sides become separate "removed"/"new" alignments.
    # Finding.item_key alone can't disambiguate which alignment produced
    # which finding; grouping by alignment identity must carry the real
    # relationship. Each finding's reasoning is stamped with its source
    # alignment's body_text so the correlation can actually be checked.
    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def fake_classify(alignment):
        return [
            Finding(
                item_key="1A",  # same item_key regardless of which alignment
                category="other",
                tier="low",
                reasoning=f"from {alignment.older_section['body_text']}",
                older_excerpt=None,
                newer_excerpt=None,
            )
        ]

    verify_calls = []

    def fake_verify(findings, alignment):
        verify_calls.append((findings, alignment))
        return _no_op_verify(findings, alignment)

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify, verify_fn=fake_verify)
    result = graph.invoke(
        {
            "older_sections": [_section("1A", "a"), _section("1A", "b")],
            "newer_sections": [],
        }
    )

    assert len(result["alignments"]) == 2
    assert {a.status for a in result["alignments"]} == {"removed"}
    assert len(verify_calls) == 2  # two separate alignment groups
    for findings, alignment in verify_calls:
        assert len(findings) == 1
        assert findings[0].reasoning == f"from {alignment.older_section['body_text']}"


def test_graph_never_imports_real_openai_client_for_verify_either():
    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def fake_classify(alignment):
        return [
            Finding(
                item_key="1A",
                category="other",
                tier="low",
                reasoning="stub",
                older_excerpt=None,
                newer_excerpt=None,
            )
        ]

    verify_calls = []

    def fake_verify(findings, alignment):
        verify_calls.append(findings)
        return _no_op_verify(findings, alignment)

    graph = build_graph(embed_fn=fake_embed, classify_fn=fake_classify, verify_fn=fake_verify)
    graph.invoke(
        {
            "older_sections": [_section("1A", "x")],
            "newer_sections": [_section("1A", "y")],
        }
    )

    assert len(verify_calls) == 1
