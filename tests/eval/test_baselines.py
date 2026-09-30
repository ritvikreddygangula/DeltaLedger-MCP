from src.eval.baselines import always_flag, flag_by_diff_size, score_baseline
from src.eval.golden_set import GoldenSetCase
from src.eval.scoring import GroundTruthEntry


def _section(item_key: str, body_text: str) -> dict:
    return {"item_key": item_key, "heading_text": f"Item {item_key}.", "body_text": body_text}


def _case(older_sections: list[dict], newer_sections: list[dict]) -> GoldenSetCase:
    return GoldenSetCase(
        ticker="TEST",
        older_filing={"accession_number": "old", "filing_date": "2024-01-01", "sections": older_sections},
        newer_filing={"accession_number": "new", "filing_date": "2025-01-01", "sections": newer_sections},
        ground_truth=[],
    )


def _ground_truth(item_key: str, expect_finding: bool) -> GroundTruthEntry:
    return GroundTruthEntry(item_key=item_key, expect_finding=expect_finding, category=None, note="")


def test_always_flag_predicts_every_section_in_both_filings():
    case = _case(
        [_section("1A", "x"), _section("3", "y")],
        [_section("1A", "x"), _section("3", "y")],
    )

    assert always_flag(case) == {"1A", "3"}


def test_always_flag_excludes_sections_only_on_one_side():
    case = _case([_section("1A", "x")], [_section("1A", "x"), _section("8", "new section")])

    assert always_flag(case) == {"1A"}


def test_flag_by_diff_size_predicts_substantial_change():
    older = _section("7", "line one\nline two\n" + "old detail " * 50 + "\nline three")
    newer = _section("7", "line one\nline two\n" + "new detail " * 50 + "\nline three")
    case = _case([older], [newer])

    assert flag_by_diff_size(case, threshold=50) == {"7"}


def test_flag_by_diff_size_does_not_predict_identical_sections():
    section = _section("7", "identical text\n" * 10)
    case = _case([section], [section])

    assert flag_by_diff_size(case) == set()


def test_flag_by_diff_size_skips_sections_not_present_on_both_sides():
    # Known limitation, documented in the function's docstring: a
    # wholly-new or wholly-removed section can't be diffed, so this
    # baseline never predicts it material, unlike the real pipeline.
    case = _case([_section("1A", "x")], [_section("1A", "x"), _section("8", "brand new section")])

    assert flag_by_diff_size(case) == set()


def test_score_baseline_tp_when_expected_and_predicted():
    ground_truth = [_ground_truth("1A", expect_finding=True)]

    scores = score_baseline(ground_truth, {"1A"})

    assert len(scores) == 1
    assert scores[0].outcome == "tp"
    assert scores[0].confidence is None


def test_score_baseline_fn_when_expected_but_not_predicted():
    ground_truth = [_ground_truth("1A", expect_finding=True)]

    scores = score_baseline(ground_truth, set())

    assert scores[0].outcome == "fn"


def test_score_baseline_fp_when_predicted_but_not_expected():
    ground_truth = [_ground_truth("7", expect_finding=False)]

    scores = score_baseline(ground_truth, {"7"})

    assert scores[0].outcome == "fp"


def test_score_baseline_tn_when_neither_expected_nor_predicted():
    ground_truth = [_ground_truth("7", expect_finding=False)]

    scores = score_baseline(ground_truth, set())

    assert scores[0].outcome == "tn"


def test_score_baseline_predicted_item_not_in_ground_truth_defaults_to_expect_false():
    scores = score_baseline([], {"8"})

    assert len(scores) == 1
    assert scores[0].item_key == "8"
    assert scores[0].outcome == "fp"
