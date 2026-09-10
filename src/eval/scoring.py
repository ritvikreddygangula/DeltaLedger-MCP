from dataclasses import dataclass
from typing import Literal

from ..agents.verifier import VerifiedFinding

Outcome = Literal["tp", "fp", "fn", "tn"]


@dataclass(frozen=True)
class GroundTruthEntry:
    item_key: str
    expect_finding: bool
    category: str | None
    note: str


@dataclass(frozen=True)
class SectionScore:
    item_key: str
    outcome: Outcome
    confidence: float | None


@dataclass(frozen=True)
class EvalReport:
    precision: float | None
    recall: float | None
    tp: int
    fp: int
    fn: int
    tn: int
    avg_confidence_tp: float | None
    avg_confidence_fp: float | None


def _credible_confidence_by_item_key(
    verified_findings: list[VerifiedFinding],
) -> dict[str, float]:
    """Maps item_key -> the strongest (max) confidence among its credible
    findings. A hallucination-rejected finding (excerpt_verified=False)
    isn't a credible claim of materiality -- it's the pipeline correctly
    refusing to make one -- so it's excluded here entirely.
    """
    best: dict[str, float] = {}
    for vf in verified_findings:
        if not vf.excerpt_verified:
            continue
        item_key = vf.finding.item_key
        if item_key not in best or vf.confidence > best[item_key]:
            best[item_key] = vf.confidence
    return best


def score_case(
    ground_truth: list[GroundTruthEntry], verified_findings: list[VerifiedFinding]
) -> list[SectionScore]:
    """Section-level (item_key) precision/recall scoring. An item_key with a
    credible finding but no ground-truth entry is treated as expect_finding
    = False (the golden set is assumed to enumerate every section that
    matters; anything else the pipeline flags on its own is over-flagging).
    """
    credible = _credible_confidence_by_item_key(verified_findings)
    ground_truth_by_key = {g.item_key: g for g in ground_truth}

    item_keys = set(ground_truth_by_key) | set(credible)
    scores = []
    for item_key in item_keys:
        entry = ground_truth_by_key.get(item_key)
        expect_finding = entry.expect_finding if entry is not None else False
        has_credible = item_key in credible
        confidence = credible.get(item_key)

        if expect_finding and has_credible:
            outcome: Outcome = "tp"
        elif expect_finding and not has_credible:
            outcome = "fn"
        elif not expect_finding and has_credible:
            outcome = "fp"
        else:
            outcome = "tn"

        scores.append(SectionScore(item_key=item_key, outcome=outcome, confidence=confidence))
    return scores


def aggregate_scores(all_scores: list[SectionScore]) -> EvalReport:
    tp = sum(1 for s in all_scores if s.outcome == "tp")
    fp = sum(1 for s in all_scores if s.outcome == "fp")
    fn = sum(1 for s in all_scores if s.outcome == "fn")
    tn = sum(1 for s in all_scores if s.outcome == "tn")

    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None

    tp_confidences = [
        s.confidence for s in all_scores if s.outcome == "tp" and s.confidence is not None
    ]
    fp_confidences = [
        s.confidence for s in all_scores if s.outcome == "fp" and s.confidence is not None
    ]
    avg_confidence_tp = sum(tp_confidences) / len(tp_confidences) if tp_confidences else None
    avg_confidence_fp = sum(fp_confidences) / len(fp_confidences) if fp_confidences else None

    return EvalReport(
        precision=precision,
        recall=recall,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        avg_confidence_tp=avg_confidence_tp,
        avg_confidence_fp=avg_confidence_fp,
    )
