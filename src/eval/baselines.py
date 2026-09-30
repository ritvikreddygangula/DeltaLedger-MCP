"""Mechanical, no-LLM baselines scored against the same golden set as the
real pipeline -- see docs/BASELINE_EVAL_SPEC.md. Exists to prove the
classifier is earning its cost against something dumb and free, not just to
report the pipeline's own precision/recall in isolation.

Reuses SectionScore/aggregate_scores from scoring.py unchanged; a baseline
prediction has no model confidence, so SectionScore.confidence is always
None for these.
"""

from ..agents.diffing import diff_sections
from .golden_set import GoldenSetCase
from .scoring import GroundTruthEntry, SectionScore

DIFF_SIZE_THRESHOLD = 200  # changed characters (combined both sides)


def always_flag(case: GoldenSetCase) -> set[str]:
    """The floor baseline: predicts every section present in both filings is
    material. Precision here is just this golden set's actual base rate of
    material sections; recall is always 100%.

    Only counts sections present in *both* filings -- same limitation as
    flag_by_diff_size below, see its docstring.
    """
    older_keys = {s["item_key"] for s in case.older_filing["sections"]}
    newer_keys = {s["item_key"] for s in case.newer_filing["sections"]}
    return older_keys & newer_keys


def flag_by_diff_size(case: GoldenSetCase, threshold: int = DIFF_SIZE_THRESHOLD) -> set[str]:
    """Predicts a section is material if diff_sections() -- the same
    function the real classifier's input is built from -- finds more than
    `threshold` characters of actual change. Free, mechanical, no model
    call; distinguishes a substantial rewrite from trivial rewording and
    nothing more.

    Only considers sections present in both filings, since diffing needs
    both sides -- a section that's wholly new or wholly removed (no
    counterpart to diff against) is never predicted material by this
    baseline, unlike the real pipeline's classifier, which handles
    new/removed sections separately from matched ones.
    """
    older_sections = {s["item_key"]: s for s in case.older_filing["sections"]}
    newer_sections = {s["item_key"]: s for s in case.newer_filing["sections"]}

    predicted = set()
    for item_key in older_sections.keys() & newer_sections.keys():
        older_text = older_sections[item_key]["body_text"]
        newer_text = newer_sections[item_key]["body_text"]
        if older_text == newer_text:
            # diff_sections() falls back to returning the full original text
            # when its computed diff is empty (a reasonable choice for the
            # classifier, which needs *something* to look at) -- which would
            # otherwise make "nothing changed" look like "changed a lot" to
            # a length-based predictor. Short-circuit before that fallback.
            continue
        older_diff, newer_diff = diff_sections(older_text, newer_text)
        if len(older_diff) + len(newer_diff) > threshold:
            predicted.add(item_key)
    return predicted


def score_baseline(
    ground_truth: list[GroundTruthEntry], predicted_item_keys: set[str]
) -> list[SectionScore]:
    """Same TP/FP/FN/TN logic as scoring.py's score_case, but scored against
    a plain set of predicted item_keys instead of confidence-scored credible
    findings -- a baseline has no confidence to report.
    """
    ground_truth_by_key = {g.item_key: g for g in ground_truth}
    item_keys = set(ground_truth_by_key) | predicted_item_keys

    scores = []
    for item_key in item_keys:
        entry = ground_truth_by_key.get(item_key)
        expect_finding = entry.expect_finding if entry is not None else False
        predicted = item_key in predicted_item_keys

        if expect_finding and predicted:
            outcome = "tp"
        elif expect_finding and not predicted:
            outcome = "fn"
        elif not expect_finding and predicted:
            outcome = "fp"
        else:
            outcome = "tn"

        scores.append(SectionScore(item_key=item_key, outcome=outcome, confidence=None))
    return scores
