from typing import NotRequired, TypedDict

from .aligner import SectionAlignment
from .classifier import Finding
from .verifier import VerifiedFinding


class PipelineState(TypedDict):
    """Shared state threaded through the align -> classify -> verify
    LangGraph pipeline. One flat schema (rather than a subclass per stage)
    since StateGraph takes a single schema type -- each stage reads/writes
    only its own fields.
    """

    # --- Aligner ---
    older_sections: list[dict]
    newer_sections: list[dict]
    alignments: list[SectionAlignment]

    # --- Classifier ---
    classifications: NotRequired[list[Finding]]
    # Each finding paired with the alignment it came from -- Finding.item_key
    # alone isn't a reliable re-matching key: a "removed" and a "new"
    # alignment from the same run can share the same item_key.
    classified_pairs: NotRequired[list[tuple[SectionAlignment, Finding]]]

    # --- Verifier ---
    verified_findings: NotRequired[list[VerifiedFinding]]
