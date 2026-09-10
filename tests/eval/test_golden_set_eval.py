"""Runs the real pipeline against the golden set -- makes real, billed OpenAI
calls. Excluded from the default `uv run pytest` via the `eval` marker (see
pyproject.toml); run explicitly with `uv run pytest -m eval`.

Thresholds are deliberately lenient: the golden set is small (6 pairs, 24
section-level judgments per PROGRESS.md/EVAL_REPORT.md), and LLM output has
some run-to-run variance, so this should only fail on a real regression, not
ordinary fluctuation.
"""

import pytest

from src.eval.run_eval import run_eval

PRECISION_FLOOR = 0.4
RECALL_FLOOR = 0.4


@pytest.mark.eval
def test_golden_set_eval_meets_threshold():
    report, _case_scores = run_eval()

    print(
        f"\nPrecision: {report.precision:.0%}  Recall: {report.recall:.0%}  "
        f"TP={report.tp} FP={report.fp} FN={report.fn} TN={report.tn}"
    )

    assert report.precision is not None, "No credible findings at all -- can't compute precision"
    assert report.recall is not None, "No expected findings in the golden set -- can't compute recall"
    assert report.precision >= PRECISION_FLOOR, (
        f"Precision {report.precision:.0%} fell below the {PRECISION_FLOOR:.0%} floor -- "
        "likely a real regression, not normal LLM variance"
    )
    assert report.recall >= RECALL_FLOOR, (
        f"Recall {report.recall:.0%} fell below the {RECALL_FLOOR:.0%} floor -- "
        "likely a real regression, not normal LLM variance"
    )
