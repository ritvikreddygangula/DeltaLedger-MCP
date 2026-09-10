import json
from dataclasses import dataclass
from pathlib import Path

from .scoring import GroundTruthEntry


@dataclass(frozen=True)
class GoldenSetCase:
    ticker: str
    older_filing: dict
    newer_filing: dict
    ground_truth: list[GroundTruthEntry]


def _load_case(path: Path) -> GoldenSetCase:
    data = json.loads(path.read_text(encoding="utf-8"))
    ground_truth = [
        GroundTruthEntry(
            item_key=g["item_key"],
            expect_finding=g["expect_finding"],
            category=g.get("category"),
            note=g.get("note", ""),
        )
        for g in data["ground_truth"]
    ]
    return GoldenSetCase(
        ticker=data["ticker"],
        older_filing=data["older_filing"],
        newer_filing=data["newer_filing"],
        ground_truth=ground_truth,
    )


def load_golden_set(directory: Path) -> list[GoldenSetCase]:
    return [_load_case(path) for path in sorted(directory.glob("*.json"))]
