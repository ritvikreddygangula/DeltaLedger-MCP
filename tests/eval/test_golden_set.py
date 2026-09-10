import json

from src.eval.golden_set import load_golden_set


def _sample_case_json(ticker: str) -> dict:
    return {
        "ticker": ticker,
        "older_filing": {
            "accession_number": "0000000000-00-000001",
            "filing_date": "2024-01-01",
            "sections": [{"item_key": "1A", "heading_text": "Item 1A.", "body_text": "old text"}],
        },
        "newer_filing": {
            "accession_number": "0000000000-00-000002",
            "filing_date": "2025-01-01",
            "sections": [{"item_key": "1A", "heading_text": "Item 1A.", "body_text": "new text"}],
        },
        "ground_truth": [
            {"item_key": "1A", "expect_finding": True, "category": "new_risk_factor", "note": "why"},
            {"item_key": "3", "expect_finding": False, "category": None, "note": "no change"},
        ],
    }


def test_load_golden_set_parses_all_json_files(tmp_path):
    (tmp_path / "aaa.json").write_text(json.dumps(_sample_case_json("AAA")), encoding="utf-8")
    (tmp_path / "bbb.json").write_text(json.dumps(_sample_case_json("BBB")), encoding="utf-8")

    cases = load_golden_set(tmp_path)

    assert len(cases) == 2
    assert {c.ticker for c in cases} == {"AAA", "BBB"}


def test_load_golden_set_parses_filings_and_ground_truth(tmp_path):
    (tmp_path / "xyz.json").write_text(json.dumps(_sample_case_json("XYZ")), encoding="utf-8")

    (case,) = load_golden_set(tmp_path)

    assert case.older_filing["sections"][0]["body_text"] == "old text"
    assert case.newer_filing["sections"][0]["body_text"] == "new text"
    assert len(case.ground_truth) == 2
    assert case.ground_truth[0].item_key == "1A"
    assert case.ground_truth[0].expect_finding is True
    assert case.ground_truth[0].category == "new_risk_factor"
    assert case.ground_truth[1].expect_finding is False
    assert case.ground_truth[1].category is None


def test_load_golden_set_empty_directory_returns_empty_list(tmp_path):
    assert load_golden_set(tmp_path) == []
