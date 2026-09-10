from src.agents.classifier import Finding
from src.agents.verifier import VerifiedFinding
from src.eval.scoring import GroundTruthEntry, aggregate_scores, score_case


def _ground_truth(item_key: str, expect_finding: bool, category: str | None = None) -> GroundTruthEntry:
    return GroundTruthEntry(item_key=item_key, expect_finding=expect_finding, category=category, note="")


def _verified_finding(item_key: str, confidence: float, excerpt_verified: bool = True) -> VerifiedFinding:
    finding = Finding(
        item_key=item_key,
        category="substantive_change",
        tier="medium",
        reasoning="r",
        older_excerpt="old",
        newer_excerpt="new",
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


def test_tp_when_expected_and_credible_finding_exists():
    ground_truth = [_ground_truth("1A", expect_finding=True)]
    findings = [_verified_finding("1A", confidence=0.9)]

    scores = score_case(ground_truth, findings)

    assert len(scores) == 1
    assert scores[0].outcome == "tp"
    assert scores[0].confidence == 0.9


def test_fn_when_expected_but_no_credible_finding():
    ground_truth = [_ground_truth("1A", expect_finding=True)]

    scores = score_case(ground_truth, [])

    assert scores[0].outcome == "fn"
    assert scores[0].confidence is None


def test_fp_when_not_expected_but_credible_finding_exists():
    ground_truth = [_ground_truth("7", expect_finding=False)]
    findings = [_verified_finding("7", confidence=0.6)]

    scores = score_case(ground_truth, findings)

    assert scores[0].outcome == "fp"
    assert scores[0].confidence == 0.6


def test_tn_when_not_expected_and_no_finding():
    ground_truth = [_ground_truth("7", expect_finding=False)]

    scores = score_case(ground_truth, [])

    assert scores[0].outcome == "tn"


def test_hallucination_rejected_finding_does_not_count_as_credible():
    # A finding that failed excerpt verification is the pipeline correctly
    # refusing to claim materiality, not a claim -- should score as FN
    # (expected but nothing credible was produced), not TP.
    ground_truth = [_ground_truth("1A", expect_finding=True)]
    findings = [_verified_finding("1A", confidence=0.0, excerpt_verified=False)]

    scores = score_case(ground_truth, findings)

    assert scores[0].outcome == "fn"


def test_multiple_findings_same_item_key_takes_max_confidence():
    ground_truth = [_ground_truth("1A", expect_finding=True)]
    findings = [
        _verified_finding("1A", confidence=0.3),
        _verified_finding("1A", confidence=0.85),
    ]

    scores = score_case(ground_truth, findings)

    assert scores[0].outcome == "tp"
    assert scores[0].confidence == 0.85


def test_item_key_not_in_ground_truth_defaults_to_expect_false():
    # No ground truth entry at all for "8" -- a credible finding there is
    # over-flagging, scored as FP, not silently ignored.
    findings = [_verified_finding("8", confidence=0.7)]

    scores = score_case([], findings)

    assert len(scores) == 1
    assert scores[0].item_key == "8"
    assert scores[0].outcome == "fp"


def test_aggregate_computes_precision_and_recall():
    from src.eval.scoring import SectionScore

    scores = [
        SectionScore("1A", "tp", 0.9),
        SectionScore("3", "tp", 0.8),
        SectionScore("7", "fp", 0.6),
        SectionScore("8", "fn", None),
    ]

    report = aggregate_scores(scores)

    assert report.tp == 2
    assert report.fp == 1
    assert report.fn == 1
    assert report.tn == 0
    assert report.precision == 2 / 3
    assert report.recall == 2 / 3


def test_aggregate_precision_recall_none_when_undefined():
    from src.eval.scoring import SectionScore

    scores = [SectionScore("1A", "tn", None)]

    report = aggregate_scores(scores)

    assert report.precision is None
    assert report.recall is None


def test_aggregate_confidence_calibration():
    from src.eval.scoring import SectionScore

    scores = [
        SectionScore("1A", "tp", 0.9),
        SectionScore("3", "tp", 0.7),
        SectionScore("7", "fp", 0.2),
    ]

    report = aggregate_scores(scores)

    assert report.avg_confidence_tp == (0.9 + 0.7) / 2
    assert report.avg_confidence_fp == 0.2


def test_aggregate_confidence_none_when_no_such_outcome():
    from src.eval.scoring import SectionScore

    scores = [SectionScore("1A", "tn", None)]

    report = aggregate_scores(scores)

    assert report.avg_confidence_tp is None
    assert report.avg_confidence_fp is None
