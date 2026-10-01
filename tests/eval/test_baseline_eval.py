"""Runs the free, no-LLM baselines against the real golden set. Unlike
run_eval() (see test_golden_set_eval.py), this makes zero OpenAI calls, so
it's part of the default `uv run pytest` run on every push -- not gated
behind a marker or a manually-triggered workflow. See
docs/BASELINE_EVAL_SPEC.md.
"""

from src.eval.run_eval import run_baseline_eval


def test_baseline_eval_runs_against_real_golden_set_with_no_api_calls():
    reports = run_baseline_eval()

    assert set(reports.keys()) == {"always_flag", "diff_size"}
    for report in reports.values():
        assert report.precision is not None
        assert report.recall is not None
        assert 0.0 <= report.precision <= 1.0
        assert 0.0 <= report.recall <= 1.0


def test_always_flag_baseline_has_perfect_recall():
    # True by construction, not just on today's golden set: it predicts
    # every evaluable section material, so it can never produce a false
    # negative. A regression here would mean the baseline logic itself
    # broke, not that the golden set changed.
    reports = run_baseline_eval()

    assert reports["always_flag"].recall == 1.0
