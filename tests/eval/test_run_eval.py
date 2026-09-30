import pytest

# format_report()'s type hint pulls in RagasReport, which lives in
# ragas_scoring.py -- the optional "eval" uv dependency group. Same
# importorskip idiom as test_ragas_scoring.py.
pytest.importorskip("ragas")

from src.eval.golden_set import GoldenSetCase
from src.eval.ragas_scoring import RagasReport
from src.eval.run_eval import format_report
from src.eval.scoring import EvalReport, SectionScore


def _report(**overrides) -> EvalReport:
    defaults = {
        "precision": 0.8,
        "recall": 0.75,
        "tp": 3,
        "fp": 1,
        "fn": 1,
        "tn": 2,
        "avg_confidence_tp": 0.7,
        "avg_confidence_fp": 0.4,
    }
    defaults.update(overrides)
    return EvalReport(**defaults)


def _case() -> GoldenSetCase:
    return GoldenSetCase(
        ticker="TEST",
        older_filing={"accession_number": "old", "filing_date": "2024-01-01", "sections": []},
        newer_filing={"accession_number": "new", "filing_date": "2025-01-01", "sections": []},
        ground_truth=[],
    )


def test_report_includes_ragas_scores_section():
    case_scores = [(_case(), [SectionScore("1A", "tp", 0.9)])]
    ragas_report = RagasReport(faithfulness=0.83, answer_correctness=0.61, n_samples=5)

    text = format_report(_report(), case_scores, ragas_report)

    assert "## Ragas scores" in text
    assert "Faithfulness: 83%" in text
    assert "Answer correctness: 61%" in text
    assert "Scored over 5 finding(s)" in text


def test_report_handles_no_ragas_samples():
    # n_samples=0 (e.g. an empty golden set, or nothing scored the TP scope)
    # -- faithfulness/answer_correctness are None, must render as "N/A", not
    # crash trying to format a percentage out of None.
    case_scores = [(_case(), [])]
    ragas_report = RagasReport(faithfulness=None, answer_correctness=None, n_samples=0)

    text = format_report(_report(), case_scores, ragas_report)

    assert "Faithfulness: N/A" in text
    assert "Answer correctness: N/A" in text
    assert "Scored over 0 finding(s)" in text
