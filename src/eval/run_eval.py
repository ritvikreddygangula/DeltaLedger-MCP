"""Runs the full align+classify+verify pipeline against the golden set and
produces EVAL_REPORT.md. Makes real OpenAI calls (classify + verify for
every alignment in every case) -- not free, not part of the default test
suite. tests/eval/test_golden_set_eval.py wraps this same logic as a
CI-marked test with a threshold-based pass/fail.

Usage: uv run python -m src.eval.run_eval
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

from ..agents.graph import build_graph
from .golden_set import GoldenSetCase, load_golden_set
from .scoring import EvalReport, SectionScore, aggregate_scores, score_case

GOLDEN_SET_DIR = Path(__file__).resolve().parent.parent.parent / "tests/fixtures/eval_golden_set"
REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "EVAL_REPORT.md"

# Each case already runs its own alignments/findings concurrently (up to
# graph.MAX_WORKERS each). Running a few cases concurrently too -- rather
# than one full company at a time -- is what actually cuts wall-clock time
# for the whole golden set, not just within one company. Kept modest (not
# one worker per case) since each case can itself burst up to 8 requests;
# retry logic in _llm_utils.py absorbs the added rate-limit risk.
CASE_MAX_WORKERS = 3

KNOWN_LIMITATIONS = """## Known limitations

- **Golden set size**: 6 filing pairs (24 section-level judgments), smaller than the
  spec's suggested 15-25. Building and verifying each pair well (reading the real
  diff, confirming a genuine event, drafting ground truth) is real labor; a smaller
  honestly-labeled set was chosen over a larger rushed one. Precision/recall/
  calibration numbers here should be read as directional, not statistically
  rigorous, until the set is expanded.
- **Category matching is out of scope for v1**: scoring is binary at the section
  level ("was a material change correctly flagged for this section, yes or no"),
  not an exact match on the classifier's category label (e.g. `new_litigation` vs
  `substantive_change`). Reasonable category disagreements between the ground
  truth and the classifier are not counted as errors.
- **LLM output is not fully deterministic**: re-running this eval will produce
  slightly different findings, tiers, and confidence scores each time, even
  against identical input text. Scores here are a single run's snapshot, not a
  fixed constant.
- **Two candidate filing pairs were dropped during curation, not silently
  avoided, because they exposed real pipeline limitations**:
  - Wells Fargo (WFC): all four target sections incorporate their actual content
    by reference to a separate "Annual Report to Shareholders" exhibit that the
    EDGAR connector does not fetch. The pipeline currently cannot evaluate filers
    that structure their 10-K this way.
  - Costco (COST): the section parser selected the wrong "Item 8" boundary for
    this filing's structure, capturing the Exhibits list instead of the real
    financial statements. A parsing edge case, not a materiality-judgment issue.
"""


def run_case(case: GoldenSetCase) -> list[SectionScore]:
    graph = build_graph()
    result = graph.invoke(
        {
            "older_sections": case.older_filing["sections"],
            "newer_sections": case.newer_filing["sections"],
        }
    )
    return score_case(case.ground_truth, result["verified_findings"])


def run_eval(
    golden_set_dir: Path = GOLDEN_SET_DIR,
) -> tuple[EvalReport, list[tuple[GoldenSetCase, list[SectionScore]]]]:
    load_dotenv()  # pytest doesn't load .env automatically the way our scripts do
    cases = load_golden_set(golden_set_dir)
    with ThreadPoolExecutor(max_workers=CASE_MAX_WORKERS) as executor:
        # executor.map preserves input order in its output regardless of
        # which case finishes first, so zip(cases, ...) still pairs each
        # case with its own scores correctly.
        score_lists = list(executor.map(run_case, cases))
    case_scores = list(zip(cases, score_lists))
    all_scores = [score for _, scores in case_scores for score in scores]
    report = aggregate_scores(all_scores)
    return report, case_scores


def _pct(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "N/A"


def _confidence(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "N/A"


def _note_for(case: GoldenSetCase, item_key: str) -> str:
    entry = next((g for g in case.ground_truth if g.item_key == item_key), None)
    return entry.note if entry else ""


def format_report(
    report: EvalReport, case_scores: list[tuple[GoldenSetCase, list[SectionScore]]]
) -> str:
    total = report.tp + report.fp + report.fn + report.tn
    lines = [
        "# Eval Report",
        "",
        f"Golden set: {len(case_scores)} filing pairs, {total} section-level judgments.",
        "",
        "## Scores",
        "",
        f"- Precision: {_pct(report.precision)} ({report.tp} TP / {report.tp + report.fp} claimed)",
        f"- Recall: {_pct(report.recall)} ({report.tp} TP / {report.tp + report.fn} expected)",
        f"- TP={report.tp}  FP={report.fp}  FN={report.fn}  TN={report.tn}",
        "",
        "## Confidence calibration",
        "",
        f"- Avg confidence, true positives: {_confidence(report.avg_confidence_tp)}",
        f"- Avg confidence, false positives: {_confidence(report.avg_confidence_fp)}",
        "",
        "(True positives should score meaningfully higher than false positives on"
        " average -- that's what makes 'confidence' a real signal rather than a"
        " number an LLM made up.)",
        "",
        "## Per-case results",
        "",
    ]
    for case, scores in case_scores:
        lines.append(f"### {case.ticker}")
        for s in scores:
            conf = f" (confidence={s.confidence:.2f})" if s.confidence is not None else ""
            lines.append(f"- Item {s.item_key}: {s.outcome.upper()}{conf}")
        lines.append("")

    lines.append("## False positives")
    lines.append("")
    false_positives = [(case, s) for case, scores in case_scores for s in scores if s.outcome == "fp"]
    if not false_positives:
        lines.append("None.")
    for case, s in false_positives:
        lines.append(
            f"- **{case.ticker} Item {s.item_key}** (confidence={s.confidence:.2f}): "
            f"ground truth expected no finding -- {_note_for(case, s.item_key)}"
        )
    lines.append("")

    lines.append("## False negatives")
    lines.append("")
    false_negatives = [(case, s) for case, scores in case_scores for s in scores if s.outcome == "fn"]
    if not false_negatives:
        lines.append("None.")
    for case, s in false_negatives:
        lines.append(
            f"- **{case.ticker} Item {s.item_key}**: ground truth expected a finding "
            f"but the pipeline produced none credible -- {_note_for(case, s.item_key)}"
        )
    lines.append("")

    lines.append(KNOWN_LIMITATIONS)
    return "\n".join(lines)


def main() -> None:
    report, case_scores = run_eval()
    REPORT_PATH.write_text(format_report(report, case_scores), encoding="utf-8")
    print(f"Precision: {_pct(report.precision)}  Recall: {_pct(report.recall)}")
    print(f"TP={report.tp} FP={report.fp} FN={report.fn} TN={report.tn}")
    print(f"Avg confidence TP={_confidence(report.avg_confidence_tp)} FP={_confidence(report.avg_confidence_fp)}")
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
