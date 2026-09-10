from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from langgraph.graph import END, START, StateGraph

from ..embeddings.openai_client import get_embeddings
from .aligner import DEFAULT_MATCH_THRESHOLD, SectionAlignment, align_sections
from .classifier import Finding, classify_alignment
from .state import PipelineState
from .verifier import VerifiedFinding, verify_finding

EmbedFn = Callable[[list[str]], list[list[float]]]
ClassifyFn = Callable[[SectionAlignment], list[Finding]]
VerifyFn = Callable[[Finding, SectionAlignment], VerifiedFinding]

# classify_fn/verify_fn calls are independent per item (no shared state, each
# creates its own OpenAI client internally) -- run them concurrently rather
# than waiting for each network round trip before starting the next one.
MAX_WORKERS = 8


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
        alignments = state["alignments"]
        if not alignments:
            return {"classifications": [], "classified_pairs": []}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # executor.map preserves input order in its output, regardless
            # of which call finishes first -- results[i] always corresponds
            # to alignments[i].
            results = list(executor.map(classify_fn, alignments))

        classifications: list[Finding] = []
        classified_pairs: list[tuple[SectionAlignment, Finding]] = []
        for alignment, findings in zip(alignments, results):
            classifications.extend(findings)
            classified_pairs.extend((alignment, finding) for finding in findings)
        return {"classifications": classifications, "classified_pairs": classified_pairs}

    return classify_node


def _make_verify_node(verify_fn: VerifyFn):
    def verify_node(state: PipelineState) -> dict:
        classified_pairs = state["classified_pairs"]
        if not classified_pairs:
            return {"verified_findings": []}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            verified_findings = list(
                executor.map(
                    lambda pair: verify_fn(pair[1], pair[0]), classified_pairs
                )
            )
        return {"verified_findings": verified_findings}

    return verify_node


def build_graph(
    embed_fn: EmbedFn = get_embeddings,
    classify_fn: ClassifyFn = classify_alignment,
    verify_fn: VerifyFn = verify_finding,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
):
    builder = StateGraph(PipelineState)
    builder.add_node("align", _make_align_node(embed_fn, threshold))
    builder.add_node("classify", _make_classify_node(classify_fn))
    builder.add_node("verify", _make_verify_node(verify_fn))
    builder.add_edge(START, "align")
    builder.add_edge("align", "classify")
    builder.add_edge("classify", "verify")
    builder.add_edge("verify", END)
    return builder.compile()
