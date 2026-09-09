from typing import NotRequired, TypedDict

from .aligner import SectionAlignment


class PipelineState(TypedDict):
    """Shared state threaded through the whole materiality-engine LangGraph
    pipeline. One flat schema for all Parts (rather than per-Part subclasses)
    since StateGraph takes a single schema type -- each Part adds only the
    fields its own node(s) read/write; earlier Parts' nodes and fields are
    never touched.
    """

    # --- Part 3 (Aligner) ---
    older_sections: list[dict]
    newer_sections: list[dict]
    alignments: list[SectionAlignment]

    # --- Part 4 (Materiality Classifier) -- not yet populated ---
    classifications: NotRequired[list[dict]]

    # --- Part 5 (Verifier) -- not yet populated ---
    verified_findings: NotRequired[list[dict]]
