import pytest

from src.agents.aligner import align_sections


def _section(item_key: str) -> dict:
    return {"item_key": item_key, "heading_text": f"Item {item_key}.", "body_text": ""}


def test_perfect_one_to_one_match():
    older = [_section("1A"), _section("7")]
    newer = [_section("1A"), _section("7")]
    older_embeddings = [[1.0, 0.0], [0.0, 1.0]]
    newer_embeddings = [[1.0, 0.0], [0.0, 1.0]]

    alignments = align_sections(older, newer, older_embeddings, newer_embeddings)

    assert {a.status for a in alignments} == {"matched"}
    assert len(alignments) == 2
    for a in alignments:
        assert a.similarity == pytest.approx(1.0)


def test_extra_older_section_is_removed():
    older = [_section("1A"), _section("3")]
    newer = [_section("1A")]
    older_embeddings = [[1.0, 0.0], [0.0, 1.0]]
    newer_embeddings = [[1.0, 0.0]]

    alignments = align_sections(older, newer, older_embeddings, newer_embeddings)

    statuses = {a.status for a in alignments}
    assert statuses == {"matched", "removed"}
    matched = next(a for a in alignments if a.status == "matched")
    removed = next(a for a in alignments if a.status == "removed")
    assert matched.older_section["item_key"] == "1A"
    assert removed.older_section["item_key"] == "3"


def test_extra_newer_section_is_new():
    older = [_section("1A")]
    newer = [_section("1A"), _section("3")]
    older_embeddings = [[1.0, 0.0]]
    newer_embeddings = [[1.0, 0.0], [0.0, 1.0]]

    alignments = align_sections(older, newer, older_embeddings, newer_embeddings)

    statuses = {a.status for a in alignments}
    assert statuses == {"matched", "new"}
    matched = next(a for a in alignments if a.status == "matched")
    new = next(a for a in alignments if a.status == "new")
    assert matched.newer_section["item_key"] == "1A"
    assert new.newer_section["item_key"] == "3"


def test_optimal_assignment_beats_naive_per_row_argmax():
    # older[0] and older[1] both score highest against newer[0] (1.0 and 0.8
    # respectively), so independent per-row argmax would have BOTH claim
    # newer[0], leaving newer[1] completely unmatched. The optimal
    # assignment instead pairs older[0]->newer[0] (1.0) and
    # older[1]->newer[1] (0.6), since that maximizes total similarity
    # (1.6) over the alternative (0.8). A low threshold isolates this
    # assignment-quality property from threshold-gating, tested separately.
    older = [_section("1A"), _section("7")]
    newer = [_section("1A"), _section("7")]
    older_embeddings = [[1.0, 0.0], [0.8, 0.6]]
    newer_embeddings = [[1.0, 0.0], [0.0, 1.0]]

    alignments = align_sections(
        older, newer, older_embeddings, newer_embeddings, threshold=0.5
    )

    assert {a.status for a in alignments} == {"matched"}
    by_older_key = {a.older_section["item_key"]: a for a in alignments}
    assert by_older_key["1A"].newer_section["item_key"] == "1A"
    assert by_older_key["1A"].similarity == pytest.approx(1.0)
    assert by_older_key["7"].newer_section["item_key"] == "7"
    assert by_older_key["7"].similarity == pytest.approx(0.6)


def test_below_threshold_pairing_splits_into_removed_and_new():
    older = [_section("1A")]
    newer = [_section("3")]
    older_embeddings = [[1.0, 0.0]]
    newer_embeddings = [[0.0, 1.0]]  # orthogonal -- similarity 0.0

    alignments = align_sections(older, newer, older_embeddings, newer_embeddings)

    assert {a.status for a in alignments} == {"removed", "new"}
    removed = next(a for a in alignments if a.status == "removed")
    new = next(a for a in alignments if a.status == "new")
    assert removed.older_section["item_key"] == "1A"
    assert new.newer_section["item_key"] == "3"


def test_both_empty_returns_empty():
    assert align_sections([], [], [], []) == []
