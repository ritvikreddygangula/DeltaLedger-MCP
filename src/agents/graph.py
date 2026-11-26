import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import psycopg
from langgraph.graph import END, START, StateGraph

from ..embeddings.openai_client import get_embeddings
from ..observability import get_logger, log_event, timed
from ..storage import llm_cache
from . import classifier, verifier
from .aligner import DEFAULT_MATCH_THRESHOLD, SectionAlignment, align_sections
from .classifier import Finding, classify_alignment
from .state import PipelineState
from .verifier import VerifiedFinding, verify_findings_for_alignment

logger = get_logger(__name__)

EmbedFn = Callable[[list[str]], list[list[float]]]
ClassifyFn = Callable[[SectionAlignment], list[Finding]]
VerifyFn = Callable[[list[Finding], SectionAlignment], list[VerifiedFinding]]

# classify_fn/verify_fn calls are independent per item (no shared state, each
# creates its own OpenAI client internally) -- run them concurrently rather
# than waiting for each network round trip before starting the next one.
MAX_WORKERS = 8


def _make_align_node(embed_fn: EmbedFn, threshold: float):
    def align_node(state: PipelineState) -> dict:
        with timed(logger, "align_stage") as extra:
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
            extra["older_section_count"] = len(older_sections)
            extra["newer_section_count"] = len(newer_sections)
            extra["matched"] = sum(1 for a in alignments if a.status == "matched")
            extra["removed"] = sum(1 for a in alignments if a.status == "removed")
            extra["new"] = sum(1 for a in alignments if a.status == "new")
        return {"alignments": alignments}

    return align_node


def _make_classify_node(classify_fn: ClassifyFn):
    def classify_node(state: PipelineState) -> dict:
        alignments = state["alignments"]
        if not alignments:
            log_event(logger, "classify_stage", duration_ms=0.0, alignment_count=0, finding_count=0)
            return {"classifications": [], "classified_pairs": []}

        with timed(logger, "classify_stage", alignment_count=len(alignments)) as extra:
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
            extra["finding_count"] = len(classifications)
        return {"classifications": classifications, "classified_pairs": classified_pairs}

    return classify_node


def _group_by_alignment(
    classified_pairs: list[tuple[SectionAlignment, Finding]],
) -> list[tuple[SectionAlignment, list[Finding]]]:
    """Groups findings by their originating alignment so all of one
    section's findings can be verified in a single batched call. Grouped by
    object identity (id()), not value equality -- SectionAlignment holds
    dicts, which aren't hashable, so it can't be used as a dict key
    directly; identity is safe here because classify_node builds
    classified_pairs by reusing the exact same alignment object for every
    finding it produces.
    """
    groups: dict[int, tuple[SectionAlignment, list[Finding]]] = {}
    order: list[int] = []
    for alignment, finding in classified_pairs:
        key = id(alignment)
        if key not in groups:
            groups[key] = (alignment, [])
            order.append(key)
        groups[key][1].append(finding)
    return [groups[key] for key in order]


def _make_verify_node(verify_fn: VerifyFn):
    def verify_node(state: PipelineState) -> dict:
        groups = _group_by_alignment(state["classified_pairs"])
        if not groups:
            log_event(logger, "verify_stage", duration_ms=0.0, group_count=0, verified_count=0)
            return {"verified_findings": []}

        with timed(logger, "verify_stage", group_count=len(groups)) as extra:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                results = list(
                    executor.map(lambda group: verify_fn(group[1], group[0]), groups)
                )

            verified_findings = [vf for group_results in results for vf in group_results]
            extra["verified_count"] = len(verified_findings)
            extra["credible_count"] = sum(1 for vf in verified_findings if vf.excerpt_verified)
        return {"verified_findings": verified_findings}

    return verify_node


def _classify_cache_key(alignment: SectionAlignment) -> str:
    older = alignment.older_section
    newer = alignment.newer_section
    return llm_cache.compute_cache_key(
        kind="classify",
        status=alignment.status,
        older_text=older["body_text"] if older else None,
        newer_text=newer["body_text"] if newer else None,
        model=classifier.DEFAULT_CHAT_MODEL,
        prompt_version=classifier.PROMPT_VERSION,
        reasoning_effort=classifier.DEFAULT_REASONING_EFFORT,
    )


def _cached_classify(classify_fn: ClassifyFn, conn: psycopg.Connection) -> ClassifyFn:
    def wrapped(alignment: SectionAlignment) -> list[Finding]:
        item_key = (alignment.older_section or alignment.newer_section)["item_key"]
        key = _classify_cache_key(alignment)
        cached = llm_cache.get_cached(conn, key)
        if cached is not None:
            log_event(logger, "llm_cache_hit", kind="classify", item_key=item_key)
            return [Finding(**d) for d in json.loads(cached)]
        log_event(logger, "llm_cache_miss", kind="classify", item_key=item_key)
        findings = classify_fn(alignment)
        llm_cache.set_cached(
            conn, key, "classify",
            json.dumps([dataclasses.asdict(f) for f in findings]),
            classifier.DEFAULT_CHAT_MODEL, classifier.PROMPT_VERSION,
        )
        return findings

    return wrapped


def _verify_cache_key(findings: list[Finding], alignment: SectionAlignment) -> str:
    older = alignment.older_section
    newer = alignment.newer_section
    return llm_cache.compute_cache_key(
        kind="verify",
        status=alignment.status,
        older_text=older["body_text"] if older else None,
        newer_text=newer["body_text"] if newer else None,
        claims=[dataclasses.asdict(f) for f in findings],
        model=verifier.DEFAULT_CHAT_MODEL,
        prompt_version=verifier.PROMPT_VERSION,
        reasoning_effort=verifier.DEFAULT_REASONING_EFFORT,
    )


def _verified_finding_from_dict(d: dict) -> VerifiedFinding:
    return VerifiedFinding(**{**d, "finding": Finding(**d["finding"])})


def _cached_verify(verify_fn: VerifyFn, conn: psycopg.Connection) -> VerifyFn:
    def wrapped(findings: list[Finding], alignment: SectionAlignment) -> list[VerifiedFinding]:
        item_key = (alignment.older_section or alignment.newer_section)["item_key"]
        key = _verify_cache_key(findings, alignment)
        cached = llm_cache.get_cached(conn, key)
        if cached is not None:
            log_event(logger, "llm_cache_hit", kind="verify", item_key=item_key)
            return [_verified_finding_from_dict(d) for d in json.loads(cached)]
        log_event(logger, "llm_cache_miss", kind="verify", item_key=item_key)
        verified = verify_fn(findings, alignment)
        llm_cache.set_cached(
            conn, key, "verify",
            json.dumps([dataclasses.asdict(vf) for vf in verified]),
            verifier.DEFAULT_CHAT_MODEL, verifier.PROMPT_VERSION,
        )
        return verified

    return wrapped


def build_graph(
    embed_fn: EmbedFn = get_embeddings,
    classify_fn: ClassifyFn = classify_alignment,
    verify_fn: VerifyFn = verify_findings_for_alignment,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
    cache_conn: psycopg.Connection | None = None,
):
    if cache_conn is not None:
        classify_fn = _cached_classify(classify_fn, cache_conn)
        verify_fn = _cached_verify(verify_fn, cache_conn)
    builder = StateGraph(PipelineState)
    builder.add_node("align", _make_align_node(embed_fn, threshold))
    builder.add_node("classify", _make_classify_node(classify_fn))
    builder.add_node("verify", _make_verify_node(verify_fn))
    builder.add_edge(START, "align")
    builder.add_edge("align", "classify")
    builder.add_edge("classify", "verify")
    builder.add_edge("verify", END)
    return builder.compile()
