# Eval Report

Golden set: 6 filing pairs, 24 section-level judgments.

## Scores

- Precision: 69% (11 TP / 16 claimed)
- Recall: 85% (11 TP / 13 expected)
- TP=11  FP=5  FN=2  TN=6

## Confidence calibration

- Avg confidence, true positives: 0.93
- Avg confidence, false positives: 0.92

(True positives should score meaningfully higher than false positives on average -- that's what makes 'confidence' a real signal rather than a number an LLM made up.)

## Per-case results

### AAPL
- Item 8: TP (confidence=0.61)
- Item 3: TP (confidence=0.99)
- Item 1A: FN
- Item 7: TP (confidence=0.97)

### LYV
- Item 8: TP (confidence=0.98)
- Item 3: TN
- Item 1A: TP (confidence=0.98)
- Item 7: TN

### MGM
- Item 8: TP (confidence=0.98)
- Item 3: TN
- Item 1A: TP (confidence=0.96)
- Item 7: TP (confidence=0.93)

### NKE
- Item 8: FP (confidence=0.95)
- Item 3: TN
- Item 1A: FP (confidence=0.97)
- Item 7: TP (confidence=0.96)

### PG
- Item 8: FP (confidence=0.98)
- Item 3: TN
- Item 1A: TP (confidence=0.90)
- Item 7: FN

### SBUX
- Item 8: FP (confidence=0.91)
- Item 3: TN
- Item 1A: FP (confidence=0.78)
- Item 7: TP (confidence=0.92)

## False positives

- **NKE Item 8** (confidence=0.95): ground truth expected no finding -- Restructuring charges continue at similar levels to the prior year (severance mentions decreased); the only new name found (Elliott Hill) is a signature-line certification, not a substantive disclosure.
- **NKE Item 1A** (confidence=0.97): ground truth expected no finding -- Tariff risk factor already present at similar volume in both years (10 mentions each) -- no genuinely new topic found.
- **PG Item 8** (confidence=0.98): ground truth expected no finding -- Only Russia/Ukraine mention is a single passing reference in routine goodwill-impairment estimation language -- boilerplate caveat, not a discrete new disclosure.
- **SBUX Item 8** (confidence=0.91): ground truth expected no finding -- No distinctive new disclosure found in targeted scanning.
- **SBUX Item 1A** (confidence=0.78): ground truth expected no finding -- Only ~2% size growth, no new risk-factor topic found (checked inflation/labor/wage/union -- all absent in both years).

## False negatives

- **AAPL Item 1A**: ground truth expected a finding but the pipeline produced none credible -- New tariff/Section 232 risk language, Google antitrust remedies threatening search-licensing revenue, expanded litigation/regulatory risk disclosures.
- **PG Item 7**: ground truth expected a finding but the pipeline produced none credible -- MD&A jumps from 1 Russia/Ukraine mention to 20 -- genuine discussion of exiting/scaling back Russia operations.

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
