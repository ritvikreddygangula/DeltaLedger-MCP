# Eval Report

Golden set: 6 filing pairs, 24 section-level judgments.

**Last measured:** 2026-09-21, after Part 8's diffing + content-hash cache changes (`src/agents/diffing.py`, `src/agents/graph.py`) -- the classifier and verifier now see only the changed regions of a "matched" section instead of its full body text, so this is a genuinely different (smaller, targeted) prompt shape than the run below, not just normal re-run noise on an unchanged pipeline.

## Scores

- Precision: 94% (17 TP / 18 claimed)
- Recall: 94% (17 TP / 18 expected)
- TP=17  FP=1  FN=1  TN=5

## Confidence calibration

- Avg confidence, true positives: 0.71
- Avg confidence, false positives: 0.91

(True positives should score meaningfully higher than false positives on average -- that's what makes 'confidence' a real signal rather than a number an LLM made up. This run's numbers run the wrong way, but `avg_confidence_fp` here is a single data point -- only one false positive occurred -- so this is far more likely to be small-sample noise than a real calibration regression from the diffing change. Worth re-checking if the golden set ever grows past 6 cases.)

## Per-case results

Not captured for this run -- these numbers came out of the reasoning-effort comparison in Part 8 (see `PROGRESS.md`), which only needed the aggregate precision/recall/confidence figures, not a full per-case breakdown. Re-running `uv run python -m src.eval.run_eval` will regenerate the full per-case/false-positive/false-negative detail (as in every prior version of this report) the next time that's actually needed -- deliberately not spending on a dedicated run purely to backfill formatting, consistent with this project's standing practice of not re-running the paid eval without a real reason (see Part 6's lesson on this in `PROGRESS.md`).

## Known limitations

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
