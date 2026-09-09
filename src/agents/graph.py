from typing import Callable

from langgraph.graph import END, START, StateGraph

from ..embeddings.openai_client import get_embeddings
from .aligner import DEFAULT_MATCH_THRESHOLD, align_sections
from .state import PipelineState

EmbedFn = Callable[[list[str]], list[list[float]]]


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


def build_graph(
    embed_fn: EmbedFn = get_embeddings, threshold: float = DEFAULT_MATCH_THRESHOLD
):
    builder = StateGraph(PipelineState)
    builder.add_node("align", _make_align_node(embed_fn, threshold))
    builder.add_edge(START, "align")
    builder.add_edge("align", END)
    return builder.compile()
