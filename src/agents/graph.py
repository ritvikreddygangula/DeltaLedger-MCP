from typing import Callable

from langgraph.graph import END, START, StateGraph

from ..embeddings.openai_client import get_embeddings
from .aligner import DEFAULT_MATCH_THRESHOLD, SectionAlignment, align_sections
from .classifier import Finding, classify_alignment
from .state import PipelineState

EmbedFn = Callable[[list[str]], list[list[float]]]
ClassifyFn = Callable[[SectionAlignment], list[Finding]]


def _make_align_node(embed_fn: EmbedFn, threshold: float):
    def align_node(state: PipelineState) -> dict:
        older_sections = state["older_sections"]
        newer_sections = state["newer_sections"]
        older_embeddings = embed_fn([s["body_text"] for s in older_sections])
        newer_embeddings = embed_fn([s["body_text"] for s in newer_sections])
        alignments = align_sections(
            older_sections,
            newer_sections,
            older_embeddings,
            newer_embeddings,
            threshold=threshold,
        )
        return {"alignments": alignments}

    return align_node


def _make_classify_node(classify_fn: ClassifyFn):
    def classify_node(state: PipelineState) -> dict:
        classifications: list[Finding] = []
        for alignment in state["alignments"]:
            classifications.extend(classify_fn(alignment))
        return {"classifications": classifications}

    return classify_node


def build_graph(
    embed_fn: EmbedFn = get_embeddings,
    classify_fn: ClassifyFn = classify_alignment,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
):
    builder = StateGraph(PipelineState)
    builder.add_node("align", _make_align_node(embed_fn, threshold))
    builder.add_node("classify", _make_classify_node(classify_fn))
    builder.add_edge(START, "align")
    builder.add_edge("align", "classify")
    builder.add_edge("classify", END)
    return builder.compile()
