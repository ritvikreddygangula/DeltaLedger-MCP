import re
from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel, Field

from ..observability import get_logger, log_event
from . import classifier
from ._llm_utils import call_responses_parse, log_usage
from .aligner import SectionAlignment
from .diffing import diff_sections
from .classifier import Finding, MaterialityTier

logger = get_logger(__name__)

DEFAULT_CHAT_MODEL = "gpt-5.4-mini"
DEFAULT_REASONING_EFFORT = "medium"
PROMPT_VERSION = "v1"


@dataclass(frozen=True)
class VerifiedFinding:
    finding: Finding
    excerpt_verified: bool
    confidence: float
    verifier_reasoning: str
    final_tier: MaterialityTier
    classifier_model: str
    classifier_prompt_version: str
    verifier_model: str
    verifier_prompt_version: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def excerpts_verified(finding: Finding, alignment: SectionAlignment) -> bool:
    """Layer 1: deterministic, no LLM call. A None excerpt (the classifier
    nulls out the side that has no counterpart for removed/new alignments)
    trivially passes -- there's nothing to hallucinate. Anything else must
    be a verbatim (whitespace-normalized) substring of that side's body_text.
    """

    def _side_ok(excerpt: str | None, body_text: str | None) -> bool:
        if excerpt is None:
            return True
        if body_text is None:
            return False
        return _normalize(excerpt) in _normalize(body_text)

    older_body = alignment.older_section["body_text"] if alignment.older_section else None
    newer_body = alignment.newer_section["body_text"] if alignment.newer_section else None
    return _side_ok(finding.older_excerpt, older_body) and _side_ok(
        finding.newer_excerpt, newer_body
    )


class _SingleVerificationSchema(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    final_tier: MaterialityTier
    reasoning: str


class _BatchVerificationSchema(BaseModel):
    verifications: list[_SingleVerificationSchema]


SYSTEM_PROMPT = """You are a skeptical, adversarial auditor reviewing a junior \
analyst's claims about differences between two sequential SEC 10-K filings, \
all within the same section. Your job is to catch overclaiming, not to \
rubber-stamp it. The cited excerpt(s) for each claim have ALREADY been \
confirmed to be exact verbatim quotes from the filing text -- do not re-check \
that they exist. Your only job is whether each quote actually SUPPORTS its \
claimed category and materiality tier, given the full surrounding section \
text also provided.

You will be given a numbered list of claims. Return exactly one verification \
per claim, in the same order, as a list.

For each claim, report:
- confidence: how strongly the evidence supports the ANALYST'S ORIGINAL \
  claimed tier and category for that claim, from 0.0 (the original claim is \
  baseless/unsupported) to 1.0 (the original claim is fully and clearly \
  correct as stated). This is NOT your confidence in your own re-assessment \
  -- if you are downgrading a tier because the original claim was \
  overclaimed, that means the original claim was poorly supported, so \
  confidence should be LOW, even though you are certain about the downgrade \
  itself.
- final_tier: your own independent tier assessment for that claim (may \
  match, downgrade, or rarely upgrade the original).
- reasoning: 1-3 sentences per claim, written for a human auditor reading \
  this later."""


def _build_batch_user_prompt(findings: list[Finding], alignment: SectionAlignment) -> str:
    older = alignment.older_section
    newer = alignment.newer_section
    item_key = findings[0].item_key
    heading_text = (older or newer)["heading_text"]

    claims = "\n\n".join(
        f"CLAIM {i + 1}:\n"
        f"  category: {f.category}\n"
        f"  claimed tier: {f.tier}\n"
        f"  reasoning: {f.reasoning}\n"
        f"  older_excerpt: {f.older_excerpt!r}\n"
        f"  newer_excerpt: {f.newer_excerpt!r}"
        for i, f in enumerate(findings)
    )

    blocks = []
    if older is not None and newer is not None:
        # Same diff the classifier saw, recomputed fresh (diff_sections is
        # pure, so this always agrees with it) -- verify no longer pays
        # full-section-text cost a second time for text classify already
        # sent.
        older_text, newer_text = diff_sections(older["body_text"], newer["body_text"])
        blocks.append(f"=== OLDER FILING TEXT (changed regions only) ===\n{older_text}")
        blocks.append(f"=== NEWER FILING TEXT (changed regions only) ===\n{newer_text}")
    elif older is not None:
        blocks.append(f"=== OLDER FILING TEXT ===\n{older['body_text']}")
    elif newer is not None:
        blocks.append(f"=== NEWER FILING TEXT ===\n{newer['body_text']}")

    return (
        f"SECTION: Item {item_key} -- {heading_text}\n\n"
        f"An analyst reported {len(findings)} finding(s) for this section:\n\n"
        f"{claims}\n\n" + "\n\n".join(blocks)
    )


def _hard_fail(
    finding: Finding, model: str, classifier_model: str, classifier_prompt_version: str
) -> VerifiedFinding:
    return VerifiedFinding(
        finding=finding,
        excerpt_verified=False,
        confidence=0.0,
        verifier_reasoning=(
            "One or more cited excerpts could not be found verbatim in "
            "the source section text -- treating as an unsupported/"
            "hallucinated claim."
        ),
        final_tier="low",
        classifier_model=classifier_model,
        classifier_prompt_version=classifier_prompt_version,
        verifier_model=model,
        verifier_prompt_version=PROMPT_VERSION,
    )


def _no_output_fallback(
    finding: Finding, model: str, classifier_model: str, classifier_prompt_version: str
) -> VerifiedFinding:
    return VerifiedFinding(
        finding=finding,
        excerpt_verified=True,
        confidence=0.0,
        verifier_reasoning=(
            "Verifier LLM call returned no usable output (refusal, parse "
            "failure, or a mismatched number of verifications)."
        ),
        final_tier=finding.tier,
        classifier_model=classifier_model,
        classifier_prompt_version=classifier_prompt_version,
        verifier_model=model,
        verifier_prompt_version=PROMPT_VERSION,
    )


def verify_findings_for_alignment(
    findings: list[Finding],
    alignment: SectionAlignment,
    client: OpenAI | None = None,
    model: str = DEFAULT_CHAT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    classifier_model: str = classifier.DEFAULT_CHAT_MODEL,
    classifier_prompt_version: str = classifier.PROMPT_VERSION,
) -> list[VerifiedFinding]:
    """Verifies every finding for one alignment in a single LLM call, rather
    than one call per finding. A section's full text can run tens of
    thousands of tokens; resending it once per finding (the original Part 5
    design) multiplies that cost by however many findings the section has.
    Findings that fail the Layer-1 hallucination check are hard-failed
    without ever entering the batch -- they still cost zero LLM calls.
    """
    if not findings:
        return []

    results: list[VerifiedFinding] = []
    needs_llm: list[Finding] = []
    for finding in findings:
        if excerpts_verified(finding, alignment):
            needs_llm.append(finding)
        else:
            results.append(_hard_fail(finding, model, classifier_model, classifier_prompt_version))

    if not needs_llm:
        return results

    client = client or OpenAI()
    item_key = needs_llm[0].item_key
    try:
        response = call_responses_parse(
            client,
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_batch_user_prompt(needs_llm, alignment)},
            ],
            text_format=_BatchVerificationSchema,
            reasoning={"effort": reasoning_effort},
        )
        parsed = response.output_parsed
        log_usage(
            logger, "openai_call", response,
            stage="verify", model=model, item_key=item_key, claim_count=len(needs_llm),
        )
    except Exception:
        parsed = None
        log_event(logger, "openai_call_failed", stage="verify", model=model, item_key=item_key)

    if parsed is None or len(parsed.verifications) != len(needs_llm):
        results.extend(
            _no_output_fallback(f, model, classifier_model, classifier_prompt_version)
            for f in needs_llm
        )
        return results

    for finding, verification in zip(needs_llm, parsed.verifications):
        results.append(
            VerifiedFinding(
                finding=finding,
                excerpt_verified=True,
                confidence=verification.confidence,
                verifier_reasoning=verification.reasoning,
                final_tier=verification.final_tier,
                classifier_model=classifier_model,
                classifier_prompt_version=classifier_prompt_version,
                verifier_model=model,
                verifier_prompt_version=PROMPT_VERSION,
            )
        )
    return results
