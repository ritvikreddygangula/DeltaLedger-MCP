import re
import warnings
from dataclasses import dataclass

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# Real EDGAR 10-Ks are iXBRL: standard HTML with XML namespace tags mixed in.
# bs4 flags that combination as "looks like XML" even though parsing it as
# HTML (what we want) is correct and is exactly what browsers do.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

TARGET_ITEMS = ["1A", "3", "7", "8"]

# Matches a line that STARTS with "Item N[letter]" and has a short remainder
# (<=120 chars) on the same line. The short-remainder constraint is what lets
# this match both real headings and table-of-contents entries alike (both are
# short) while excluding inline prose references like "as discussed in Item 7
# above, the Company..." which don't start a line.
ITEM_LINE_RE = re.compile(
    r"^item\s+(\d{1,2})([a-c])?\.?\s*(.{0,120})$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class TaggedSection:
    item_key: str  # "1A" | "3" | "7" | "8"
    heading_text: str
    body_text: str


@dataclass(frozen=True)
class _HeadingCandidate:
    item_key: str
    offset: int  # char offset of match start in the flattened full text
    line_end: int  # char offset where the heading's line ends (body starts here)
    raw_text: str


def parse_10k_sections(html: str) -> list[TaggedSection]:
    """Parse raw 10-K HTML and extract Item 1A/3/7/8.

    Returns 0-4 TaggedSection entries -- a missing section is simply omitted,
    not an error: some filers' Item 3 body is legitimately a one-line "None."
    which is still valid content, while a section absent from a malformed or
    unusual document should degrade gracefully rather than raise.
    """
    full_text = _flatten_and_normalize(html)
    candidates = _find_heading_candidates(full_text)
    selected = _select_real_headings(candidates)
    return _build_sections(full_text, selected)


def _flatten_and_normalize(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    raw_text = soup.get_text(separator="\n")
    raw_text = raw_text.replace("\xa0", " ")
    lines = []
    for line in raw_text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _find_heading_candidates(full_text: str) -> list[_HeadingCandidate]:
    candidates = []
    for match in ITEM_LINE_RE.finditer(full_text):
        digits, letter, _remainder = match.groups()
        item_key = digits + (letter.upper() if letter else "")
        candidates.append(
            _HeadingCandidate(
                item_key=item_key,
                offset=match.start(),
                line_end=match.end(),
                raw_text=match.group(0).strip(),
            )
        )
    return candidates


def _exclude_table_of_contents(
    ordered: list[_HeadingCandidate], toc_max_gap: int, min_toc_items: int = 5
) -> list[_HeadingCandidate]:
    """Identifies and drops the leading table-of-contents block as a whole,
    rather than judging each candidate's own gap in isolation.

    A real ToC lists every item exactly once, in order, each entry
    separated from the next by a small gap -- so it shows up as a
    contiguous run of DISTINCT item_keys near the start of the document.
    Real body content, by contrast, either has just one occurrence of an
    item_key, or -- when a filer prints "Item 7" as a running page header
    on every page of a long section -- REPEATS the same item_key many
    times over. The block ends at the first repeat (real content started)
    or the first large gap (we've moved past the ToC into real body text).

    Judging ToC membership this way, rather than by each candidate's own
    gap to its neighbor, matters because a single ToC entry can have an
    anomalously large gap purely from a filer's own formatting quirks --
    a per-candidate threshold check can end up selecting that ToC line
    itself as if it were the real section.

    `min_toc_items` guards the other direction: a real ToC lists on the
    order of 15+ items (1 through 9C, in a modern 10-K), so a run shorter
    than this is more likely two genuinely short, distinct real sections
    sitting close together than an actual ToC -- e.g. one short real
    section immediately followed by an unrelated later item, which would
    otherwise be misclassified as a ToC and dropped entirely.
    """
    if len(ordered) < 2:
        return ordered

    # A candidate only belongs to the block once CONFIRMED by a close,
    # distinct successor -- so the very first candidate isn't assumed to
    # be in the block until candidate 1 validates it. Each successful step
    # extends the block to include the candidate just examined.
    seen: set[str] = {ordered[0].item_key}
    toc_block_end = -1
    for i in range(1, len(ordered)):
        prev, candidate = ordered[i - 1], ordered[i]
        if candidate.item_key in seen or (candidate.offset - prev.line_end) > toc_max_gap:
            break
        seen.add(candidate.item_key)
        toc_block_end = i

    if toc_block_end + 1 < min_toc_items:
        return ordered
    return ordered[toc_block_end + 1 :]


def _select_real_headings(
    candidates: list[_HeadingCandidate], min_gap_chars: int = 400, toc_max_gap: int = 2000
) -> list[_HeadingCandidate]:
    """Disambiguate real section headings from table-of-contents entries --
    AND from repeated running page-headers some filers print on every page
    of a long section.

    Step 1: drop the entire leading ToC block at once (_exclude_table_of_contents).

    Step 2: among what's left, for each item_key take the FIRST candidate
    (in document order) whose gap to the next candidate is large -- not the
    last. This must be "first", not "last": when a filer repeats "Item 7"
    or "Item 8" as a running page header throughout a long section, every
    repeat also has a large gap to whatever comes next (a full page of real
    content each time), so "last occurrence with a large gap" would pick
    the LAST repeat -- deep inside the section, often in the trailing
    audit-report boilerplate -- instead of the true start.

    Gap-to-NEXT is used here deliberately, not gap-to-previous: SEC filings
    since 2021 almost universally show "Item 6. [Reserved]" (the Selected
    Financial Data requirement was eliminated that year) with essentially
    no content, so the real Item 7 heading immediately follows it with a
    near-zero gap from the previous candidate. Gap-to-next doesn't have
    this problem: a real heading is reliably followed by substantial body
    text regardless of how little preceded it.

    If NO candidate for an item_key clears the threshold at all -- e.g. a
    filer whose real Item 3 is legitimately a one-line "None." with under
    400 chars before Item 4 starts -- fall back to the LAST occurrence
    overall rather than the first, since within the post-ToC candidates
    the real heading is always the (possibly only) occurrence, and
    defaulting to the last one is the safer bet if none of them clear the
    threshold at all.
    """
    if not candidates:
        return []

    ordered = _exclude_table_of_contents(sorted(candidates, key=lambda c: c.offset), toc_max_gap)
    gaps: list[int | None] = []
    for i, candidate in enumerate(ordered):
        if i + 1 < len(ordered):
            gaps.append(ordered[i + 1].offset - candidate.line_end)
        else:
            gaps.append(None)  # last candidate in the document

    indices_by_item: dict[str, list[int]] = {}
    for i, candidate in enumerate(ordered):
        indices_by_item.setdefault(candidate.item_key, []).append(i)

    selected = []
    for item_key, indices in indices_by_item.items():
        qualifying = [i for i in indices if gaps[i] is None or gaps[i] >= min_gap_chars]
        chosen = min(qualifying) if qualifying else max(indices)
        selected.append(ordered[chosen])

    return sorted(selected, key=lambda c: c.offset)


def _build_sections(
    full_text: str, selected: list[_HeadingCandidate]
) -> list[TaggedSection]:
    sections = []
    for i, candidate in enumerate(selected):
        if candidate.item_key not in TARGET_ITEMS:
            continue
        end = selected[i + 1].offset if i + 1 < len(selected) else len(full_text)
        body_text = full_text[candidate.line_end : end].strip()
        sections.append(
            TaggedSection(
                item_key=candidate.item_key,
                heading_text=candidate.raw_text,
                body_text=body_text,
            )
        )
    return sections
