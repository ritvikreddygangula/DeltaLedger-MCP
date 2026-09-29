"""Finds candidate 10-K pairs for the eval golden set by cross-referencing
SEC 8-K filings with high-signal item codes against a company's 10-K filing
history. See docs/RAGAS_EVAL_SPEC.md for the full rationale.

This is a discovery tool, not an auto-labeler: it surfaces candidates worth
a human reading, it never writes directly into
tests/fixtures/eval_golden_set/. A human still has to confirm the 8-K's
event actually shows up in the "newer" 10-K's text and write the
item_key/category/note by hand before a candidate becomes a real golden-set
case.

Usage: uv run python -m scripts.find_golden_set_candidates AAPL KO MSFT ...
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.connectors.edgar import SUBMISSIONS_URL_TMPL, EDGARConnector

# Chosen because they're rare and essentially never filed for routine
# reasons, unlike 1.01/1.02 (material agreements -- filed constantly) or
# 8.01 (catch-all "other events" -- could be anything). See
# docs/RAGAS_EVAL_SPEC.md for why those three are deliberately excluded
# from this first pass.
TARGET_ITEM_CODES = {"1.03", "4.02", "1.05", "2.06", "3.01"}

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data/golden_set_candidates.json"


def _all_submission_pages(connector: EDGARConnector, cik: int) -> list[dict]:
    """A company's full filing history: the always-present `filings.recent`
    block, plus any paginated `filings.files[]` pages EDGAR splits older
    history into once it gets long. Fetched once per ticker and reused,
    rather than re-fetched per 8-K found, to keep this polite to EDGAR."""
    submissions = connector._get(SUBMISSIONS_URL_TMPL.format(cik=cik)).json()
    pages = [submissions["filings"]["recent"]]
    for page in submissions["filings"].get("files", []):
        page_url = f"https://data.sec.gov/submissions/{page['name']}"
        pages.append(connector._get(page_url).json())
    return pages


def find_candidate_8ks(pages: list[dict], cik: int) -> list[dict]:
    """Every 8-K across `pages` whose item codes intersect
    TARGET_ITEM_CODES."""
    hits = []
    for page in pages:
        forms = page["form"]
        items_col = page.get("items", [""] * len(forms))
        for i in range(len(forms)):
            if forms[i] != "8-K":
                continue
            matched = set(items_col[i].split(",")) & TARGET_ITEM_CODES
            if not matched:
                continue
            accession_no_dashes = page["accessionNumber"][i].replace("-", "")
            hits.append(
                {
                    "filing_date": page["filingDate"][i],
                    "accession_number": page["accessionNumber"][i],
                    "matched_items": sorted(matched),
                    "source_url": (
                        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                        f"{accession_no_dashes}/{page['primaryDocument'][i]}"
                    ),
                }
            )
    return hits


def bracket_10k_pair(pages: list[dict], event_date: str) -> dict | None:
    """The 10-K filed immediately before `event_date` ("older") and the
    first one filed after it ("newer"). None if either side is missing
    (e.g. the event is too recent for a follow-up 10-K to exist yet)."""
    all_10ks = []
    for page in pages:
        forms = page["form"]
        for i in range(len(forms)):
            if forms[i] == "10-K":
                all_10ks.append(
                    {
                        "filing_date": page["filingDate"][i],
                        "accession_number": page["accessionNumber"][i],
                    }
                )
    all_10ks.sort(key=lambda f: f["filing_date"])

    older = None
    newer = None
    for filing in all_10ks:
        if filing["filing_date"] <= event_date:
            older = filing
        elif newer is None:
            newer = filing
            break

    if older is None or newer is None:
        return None
    return {"older_10k": older, "newer_10k": newer}


def find_candidates_for_ticker(connector: EDGARConnector, ticker: str) -> list[dict]:
    cik = connector.resolve_cik(ticker)
    pages = _all_submission_pages(connector, cik)

    candidates = []
    for hit in find_candidate_8ks(pages, cik):
        pair = bracket_10k_pair(pages, hit["filing_date"])
        if pair is None:
            print(
                f"{ticker}: {hit['matched_items']} 8-K on {hit['filing_date']} "
                "has no bracketing 10-K pair yet -- skipped"
            )
            continue
        candidates.append({"ticker": ticker, "triggering_8k": hit, **pair})
        print(f"{ticker}: candidate found -- {hit['matched_items']} on {hit['filing_date']}")
    return candidates


def main() -> None:
    tickers = sys.argv[1:]
    if not tickers:
        print("Usage: uv run python -m scripts.find_golden_set_candidates TICKER [TICKER ...]")
        sys.exit(1)

    load_dotenv()
    connector = EDGARConnector()

    all_candidates = []
    for ticker in tickers:
        ticker = ticker.upper()
        try:
            all_candidates.extend(find_candidates_for_ticker(connector, ticker))
        except Exception as e:
            print(f"{ticker}: failed ({e})")

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(all_candidates, indent=2), encoding="utf-8")
    print(f"\n{len(all_candidates)} candidate(s) written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
