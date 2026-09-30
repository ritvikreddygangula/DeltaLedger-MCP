import pytest

# ragas lives in the optional "eval" uv dependency group, not installed by
# default -- skip this whole module cleanly (not a collection error) when
# it's absent, same idiom as any optional-dependency test suite. Run with
# `uv sync --group eval` first to actually exercise these.
pytest.importorskip("ragas")

from src.agents.classifier import Finding
from src.agents.verifier import VerifiedFinding
from src.eval.golden_set import GoldenSetCase
from src.eval.ragas_scoring import build_ragas_samples
from src.eval.scoring import GroundTruthEntry


def _section(item_key: str, body_text: str) -> dict:
    return {"item_key": item_key, "heading_text": f"Item {item_key}.", "body_text": body_text}


def _case(ground_truth: list[GroundTruthEntry], older_sections: list[dict], newer_sections: list[dict]) -> GoldenSetCase:
    return GoldenSetCase(
        ticker="TEST",
        older_filing={"accession_number": "old", "filing_date": "2024-01-01", "sections": older_sections},
        newer_filing={"accession_number": "new", "filing_date": "2025-01-01", "sections": newer_sections},
        ground_truth=ground_truth,
    )


def _ground_truth(item_key: str, expect_finding: bool, note: str = "note") -> GroundTruthEntry:
    return GroundTruthEntry(item_key=item_key, expect_finding=expect_finding, category=None, note=note)


def _verified_finding(item_key: str, confidence: float, reasoning: str = "r", excerpt_verified: bool = True) -> VerifiedFinding:
    finding = Finding(
        item_key=item_key,
        category="substantive_change",
        tier="medium",
        reasoning=reasoning,
        older_excerpt="old excerpt",
        newer_excerpt="new excerpt",
    )
    return VerifiedFinding(
        finding=finding,
        excerpt_verified=excerpt_verified,
        confidence=confidence,
        verifier_reasoning="vr",
        final_tier="medium",
        classifier_model="m",
        classifier_prompt_version="v1",
        verifier_model="m",
        verifier_prompt_version="v1",
    )


def test_builds_a_sample_for_an_expected_and_credible_section():
    older = [_section("1A", "line one\nline two\nold specific detail\nline three")]
    newer = [_section("1A", "line one\nline two\nnew specific detail\nline three")]
    case = _case([_ground_truth("1A", expect_finding=True, note="the real story")], older, newer)
    findings = [_verified_finding("1A", confidence=0.9, reasoning="what changed")]

    samples = build_ragas_samples(case, findings)

    assert len(samples) == 1
    sample = samples[0]
    assert sample.response == "what changed"
    assert sample.reference == "the real story"
    assert "1A" in sample.user_input
    assert len(sample.retrieved_contexts) == 2


def test_context_is_the_diff_not_the_full_body_text():
    # A long shared prefix/suffix should be squeezed out of the diffed
    # context, same as what the classifier itself is actually shown --
    # scoring faithfulness against the full body_text would be a looser,
    # less honest check than what really happened in the pipeline.
    shared = "\n".join(f"unrelated line {i}" for i in range(30))
    older = [_section("7", f"{shared}\nold specific detail\n{shared}")]
    newer = [_section("7", f"{shared}\nnew specific detail\n{shared}")]
    case = _case([_ground_truth("7", expect_finding=True)], older, newer)
    findings = [_verified_finding("7", confidence=0.9)]

    samples = build_ragas_samples(case, findings)

    combined_context = " ".join(samples[0].retrieved_contexts)
    assert "old specific detail" in combined_context
    assert "new specific detail" in combined_context
    assert len(combined_context) < len(older[0]["body_text"]) + len(newer[0]["body_text"])


def test_skips_sections_where_no_finding_is_expected():
    case = _case([_ground_truth("7", expect_finding=False)], [_section("7", "x")], [_section("7", "y")])
    findings = [_verified_finding("7", confidence=0.9)]

    samples = build_ragas_samples(case, findings)

    assert samples == []


def test_skips_expected_sections_with_no_credible_finding():
    case = _case([_ground_truth("1A", expect_finding=True)], [_section("1A", "x")], [_section("1A", "y")])

    samples = build_ragas_samples(case, [])

    assert samples == []


def test_hallucination_rejected_finding_is_not_credible():
    case = _case([_ground_truth("1A", expect_finding=True)], [_section("1A", "x")], [_section("1A", "y")])
    findings = [_verified_finding("1A", confidence=0.0, excerpt_verified=False)]

    samples = build_ragas_samples(case, findings)

    assert samples == []


def test_multiple_findings_same_item_key_uses_max_confidence_one():
    case = _case([_ground_truth("1A", expect_finding=True)], [_section("1A", "x")], [_section("1A", "y")])
    findings = [
        _verified_finding("1A", confidence=0.3, reasoning="weaker claim"),
        _verified_finding("1A", confidence=0.85, reasoning="stronger claim"),
    ]

    samples = build_ragas_samples(case, findings)

    assert len(samples) == 1
    assert samples[0].response == "stronger claim"


def test_missing_section_on_either_side_is_skipped_not_an_error():
    # Ground truth names a section that isn't actually present in one of the
    # two filings -- shouldn't happen in a well-formed golden-set case, but
    # skipping beats crashing the whole eval run over one bad entry.
    case = _case([_ground_truth("9", expect_finding=True)], [_section("1A", "x")], [_section("1A", "y")])
    findings = [_verified_finding("9", confidence=0.9)]

    samples = build_ragas_samples(case, findings)

    assert samples == []
