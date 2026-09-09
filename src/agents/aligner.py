from dataclasses import dataclass
from typing import Literal

from scipy.optimize import linear_sum_assignment

from ..embeddings.similarity import cosine_similarity_matrix

DEFAULT_MATCH_THRESHOLD = 0.75


@dataclass(frozen=True)
class SectionAlignment:
    status: Literal["matched", "removed", "new"]
    older_section: dict | None
    newer_section: dict | None
    similarity: float | None


def align_sections(
    older_sections: list[dict],
    newer_sections: list[dict],
    older_embeddings: list[list[float]],
    newer_embeddings: list[list[float]],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> list[SectionAlignment]:
    """Aligns two filings' sections via optimal one-to-one assignment
    (Hungarian algorithm) rather than independent per-row argmax, which can
    let two older sections both claim the same best-scoring newer section
    while a third newer section goes unmatched despite being a decent fit.

    The Hungarian algorithm is forced to produce a complete matching even
    between genuinely unrelated sections when one is available, so the
    threshold check happens AFTER assignment -- a low-scoring forced pairing
    becomes a separate "removed" + "new" outcome instead of a false "matched".
    """
    if not older_sections and not newer_sections:
        return []
    if not older_sections:
        return [
            SectionAlignment("new", None, section, None) for section in newer_sections
        ]
    if not newer_sections:
        return [
            SectionAlignment("removed", section, None, None)
            for section in older_sections
        ]

    similarity = cosine_similarity_matrix(older_embeddings, newer_embeddings)
    row_ind, col_ind = linear_sum_assignment(1 - similarity)

    matched_older: dict[int, tuple[int, float]] = {}
    matched_newer: set[int] = set()
    for r, c in zip(row_ind, col_ind):
        score = float(similarity[r, c])
        if score >= threshold:
            matched_older[r] = (c, score)
            matched_newer.add(c)

    alignments = [
        SectionAlignment(
            "matched",
            section,
            newer_sections[matched_older[i][0]],
            matched_older[i][1],
        )
        if i in matched_older
        else SectionAlignment("removed", section, None, None)
        for i, section in enumerate(older_sections)
    ]
    alignments += [
        SectionAlignment("new", None, section, None)
        for j, section in enumerate(newer_sections)
        if j not in matched_newer
    ]
    return alignments
