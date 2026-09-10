import re
from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel, Field

from . import classifier
from .aligner import SectionAlignment
from .classifier import Finding, MaterialityTier

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


class _VerificationSchema(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    final_tier: MaterialityTier
    reasoning: str


SYSTEM_PROMPT = """You are a skeptical, adversarial auditor reviewing a junior \
analyst's claim about a difference between two sequential SEC 10-K filings. \
Your job is to catch overclaiming, not to rubber-stamp it. The cited excerpt(s) \
have ALREADY been confirmed to be exact verbatim quotes from the filing text \
-- do not re-check that they exist. Your only job is whether the quote(s) \
actually SUPPORT the claimed category and materiality tier, given the full \
surrounding section text also provided.

Report:
- confidence: how strongly the evidence supports the ANALYST'S ORIGINAL \
  claimed tier and category, from 0.0 (the original claim is baseless/ \
  unsupported) to 1.0 (the original claim is fully and clearly correct as \
  stated). This is NOT your confidence in your own re-assessment -- if you \
  are downgrading the tier because the original claim was overclaimed, that \
  means the original claim was poorly supported, so confidence should be \
  LOW, even though you are certain about the downgrade itself.
- final_tier: your own independent tier assessment (may match, downgrade, \
  or rarely upgrade the original).
- reasoning: 1-3 sentences, written for a human auditor reading this later."""


def _build_user_prompt(finding: Finding, alignment: SectionAlignment) -> str:
    older = alignment.older_section
    newer = alignment.newer_section
    heading_text = (older or newer)["heading_text"]

    blocks = []
    if older is not None:
        blocks.append(f"=== OLDER FILING TEXT ===\n{older['body_text']}")
    if newer is not None:
        blocks.append(f"=== NEWER FILING TEXT ===\n{newer['body_text']}")

    return (
        f"SECTION: Item {finding.item_key} -- {heading_text}\n\n"
        "An analyst reported this finding:\n"
        f"  category: {finding.category}\n"
        f"  claimed tier: {finding.tier}\n"
        f"  reasoning: {finding.reasoning}\n"
        f"  older_excerpt: {finding.older_excerpt!r}\n"
        f"  newer_excerpt: {finding.newer_excerpt!r}\n\n" + "\n\n".join(blocks)
    )


def verify_finding(
    finding: Finding,
    alignment: SectionAlignment,
    client: OpenAI | None = None,
    model: str = DEFAULT_CHAT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    classifier_model: str = classifier.DEFAULT_CHAT_MODEL,
    classifier_prompt_version: str = classifier.PROMPT_VERSION,
) -> VerifiedFinding:
    if not excerpts_verified(finding, alignment):
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

    client = client or OpenAI()

    try:
        response = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(finding, alignment)},
            ],
            text_format=_VerificationSchema,
            reasoning={"effort": reasoning_effort},
        )
        parsed = response.output_parsed
    except Exception:
        parsed = None

    if parsed is None:
        return VerifiedFinding(
            finding=finding,
            excerpt_verified=True,
            confidence=0.0,
            verifier_reasoning=(
                "Verifier LLM call returned no parsed output (refusal or "
                "parse failure)."
            ),
            final_tier=finding.tier,
            classifier_model=classifier_model,
            classifier_prompt_version=classifier_prompt_version,
            verifier_model=model,
            verifier_prompt_version=PROMPT_VERSION,
        )

    return VerifiedFinding(
        finding=finding,
        excerpt_verified=True,
        confidence=parsed.confidence,
        verifier_reasoning=parsed.reasoning,
        final_tier=parsed.final_tier,
        classifier_model=classifier_model,
        classifier_prompt_version=classifier_prompt_version,
        verifier_model=model,
        verifier_prompt_version=PROMPT_VERSION,
    )
