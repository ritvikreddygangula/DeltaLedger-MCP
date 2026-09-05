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


def _select_real_headings(
    candidates: list[_HeadingCandidate], min_gap_chars: int = 400
) -> list[_HeadingCandidate]:
    """Disambiguate real section headings from table-of-contents entries.

    A ToC entry is followed almost immediately (within a few dozen chars) by
    the next ToC entry. A real heading is followed by hundreds/thousands of
    chars of body text before the next heading of ANY item. For each item_key,
    take the last candidate whose gap to the next candidate (any item, in doc
    order) is large, or that is simply the last candidate in the whole
    document. If no candidate for an item_key qualifies, fall back to its
    last occurrence anyway rather than silently dropping the section.
    """
    if not candidates:
        return []

    ordered = sorted(candidates, key=lambda c: c.offset)
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
        chosen = max(qualifying) if qualifying else max(indices)
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
