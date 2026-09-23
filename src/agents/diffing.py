import difflib

# How many unchanged lines of context to keep around each changed region --
# enough for the classifier/verifier to see what a change is embedded in,
# without dragging in the rest of a 40-page section that didn't change.
CONTEXT_LINES = 2

# If diffing doesn't shrink the combined text by at least this fraction,
# the two sides are too different for a line-level diff to be worth it
# (e.g. genuinely unrelated content) -- sending the originals is simpler
# and no more expensive than a degenerate "diff" that kept almost
# everything anyway.
MIN_SAVINGS_RATIO = 0.1


def diff_sections(older_text: str, newer_text: str) -> tuple[str, str]:
    """Returns (older_diff, newer_diff): only the lines that changed between
    the two filings' section text, plus CONTEXT_LINES of surrounding
    unchanged lines, instead of the full section body. Section text is
    already one normalized line per original document line (see
    section_parser._flatten_and_normalize), so line-level diffing lines up
    with real prose units, not arbitrary character offsets.

    This exists because most of a "matched" section's text (e.g. a 40-page
    Risk Factors item) is identical prose repeated year over year -- the
    classifier and verifier only need to see what actually changed, not
    the unchanged 90%, and both currently pay full-section-text token cost
    for every alignment (verify pays it a second time, for the same text).
    """
    older_lines = older_text.split("\n")
    newer_lines = newer_text.split("\n")
    matcher = difflib.SequenceMatcher(None, older_lines, newer_lines, autojunk=False)

    older_keep: set[int] = set()
    newer_keep: set[int] = set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        older_keep.update(range(max(0, i1 - CONTEXT_LINES), min(len(older_lines), i2 + CONTEXT_LINES)))
        newer_keep.update(range(max(0, j1 - CONTEXT_LINES), min(len(newer_lines), j2 + CONTEXT_LINES)))

    older_diff = "\n".join(older_lines[i] for i in sorted(older_keep))
    newer_diff = "\n".join(newer_lines[j] for j in sorted(newer_keep))

    combined_original = len(older_text) + len(newer_text)
    combined_diff = len(older_diff) + len(newer_diff)
    if combined_original == 0 or combined_diff == 0 or combined_diff > combined_original * (1 - MIN_SAVINGS_RATIO):
        return older_text, newer_text
    return older_diff, newer_diff
