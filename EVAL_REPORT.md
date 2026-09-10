# Eval Report

Golden set: 6 filing pairs, 24 section-level judgments.

## Scores

- Precision: 89% (17 TP / 19 claimed)
- Recall: 100% (17 TP / 17 expected)
- TP=17  FP=2  FN=0  TN=5

## Confidence calibration

- Avg confidence, true positives: 0.95
- Avg confidence, false positives: 0.94

(True positives should score meaningfully higher than false positives on average -- that's what makes 'confidence' a real signal rather than a number an LLM made up.)

## Per-case results

### AAPL
- Item 7: TP (confidence=0.97)
- Item 1A: TP (confidence=0.87)
- Item 8: TP (confidence=0.90)
- Item 3: TP (confidence=0.99)

### LYV
- Item 1A: TP (confidence=0.99)
- Item 8: TP (confidence=0.96)
- Item 3: TN
- Item 7: FP (confidence=0.98)

### MGM
- Item 1A: TP (confidence=0.96)
- Item 8: TP (confidence=0.97)
- Item 3: TN
- Item 7: TP (confidence=0.96)

### NKE
- Item 1A: TP (confidence=0.95)
- Item 8: TP (confidence=0.96)
- Item 3: TN
- Item 7: TP (confidence=0.98)

### PG
- Item 1A: TP (confidence=0.98)
- Item 8: FP (confidence=0.89)
- Item 3: TN
- Item 7: TP (confidence=0.95)

### SBUX
- Item 1A: TP (confidence=0.94)
- Item 8: TP (confidence=0.95)
- Item 3: TN
- Item 7: TP (confidence=0.90)

## False positives

- **LYV Item 7** (confidence=0.98): ground truth expected no finding -- No mention of the litigation or any accounting-standard changes in MD&A in either year -- routine business discussion only.
- **PG Item 8** (confidence=0.89): ground truth expected no finding -- Only Russia/Ukraine mention is a single passing reference in routine goodwill-impairment estimation language -- boilerplate caveat, not a discrete new disclosure.

## False negatives

None.

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
