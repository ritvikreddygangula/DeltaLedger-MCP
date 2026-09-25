from dataclasses import dataclass
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from ..observability import get_logger, log_event
from ._llm_utils import call_responses_parse, log_usage
from .aligner import SectionAlignment
from .diffing import diff_sections

logger = get_logger(__name__)

FindingCategory = Literal[
    "new_risk_factor",
    "removed_risk_factor",
    "substantive_change",
    "new_litigation",
    "removed_litigation",
    "accounting_policy_change",
    "other",
]
MaterialityTier = Literal["high", "medium", "low"]

DEFAULT_CHAT_MODEL = "gpt-5.4-mini"
DEFAULT_REASONING_EFFORT = "low"
PROMPT_VERSION = "v1"


@dataclass(frozen=True)
class Finding:
    item_key: str
    category: FindingCategory
    tier: MaterialityTier
    reasoning: str
    older_excerpt: str | None
    newer_excerpt: str | None


class _FindingSchema(BaseModel):
    category: FindingCategory
    tier: MaterialityTier
    reasoning: str
    older_excerpt: str | None
    newer_excerpt: str | None


class _ClassificationSchema(BaseModel):
    findings: list[_FindingSchema]


SYSTEM_PROMPT = """You are a financial analyst reviewing changes between two \
sequential SEC 10-K filings from the same company, one section at a time. \
Identify and classify only MATERIAL changes -- ones a reasonable investor \
would want to know about. Do NOT flag purely cosmetic rewording, reordering, \
or formatting differences that don't change substantive meaning.

For each material change, report:
- category: the type of change
- tier: "high" (investor would want to know immediately -- new litigation, a \
  significant new risk, a material accounting policy change), "medium" \
  (worth noting, not urgent), or "low" (minor but still substantive)
- reasoning: 1-3 sentences on why it matters and how you arrived at the tier
- older_excerpt / newer_excerpt: the EXACT verbatim sentence(s) you are \
  citing, copied character-for-character from the text given -- do not \
  paraphrase the excerpt itself

If nothing changed in a way that matters to an investor, return an empty \
findings list. Do not invent a finding just to have something to report."""


def _build_user_prompt(alignment: SectionAlignment) -> str:
    older = alignment.older_section
    newer = alignment.newer_section
    item_key = (older or newer)["item_key"]
    heading_text = (older or newer)["heading_text"]

    if alignment.status == "matched":
        older_text, newer_text = diff_sections(older["body_text"], newer["body_text"])
        return (
            f"SECTION: Item {item_key} -- {heading_text}\n"
            f"ALIGNMENT: matched between an older and newer filing "
            f"(embedding similarity {alignment.similarity:.4f}).\n"
            "Compare the two versions below; report only substantive differences. "
            "Unchanged surrounding text has been omitted for length -- a gap "
            "does not itself indicate a change, only the lines shown do.\n\n"
            "=== OLDER FILING TEXT (changed regions only) ===\n"
            f"{older_text}\n\n"
            "=== NEWER FILING TEXT (changed regions only) ===\n"
            f"{newer_text}"
        )
    if alignment.status == "removed":
        return (
            f"SECTION: Item {item_key} -- {heading_text}\n"
            "ALIGNMENT: this section appeared only in the OLDER filing "
            "(removed in the newer one).\n"
            "newer_excerpt must be null for every finding, since there is no newer text.\n\n"
            "=== OLDER FILING TEXT (no newer counterpart) ===\n"
            f"{older['body_text']}"
        )
    return (
        f"SECTION: Item {item_key} -- {heading_text}\n"
        "ALIGNMENT: this section appeared only in the NEWER filing "
        "(new in this filing, absent from the older one).\n"
        "older_excerpt must be null for every finding, since there is no older text.\n\n"
        "=== NEWER FILING TEXT (no older counterpart) ===\n"
        f"{newer['body_text']}"
    )


def classify_alignment(
    alignment: SectionAlignment,
    client: OpenAI | None = None,
    model: str = DEFAULT_CHAT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> list[Finding]:
    client = client or OpenAI()
    item_key = (alignment.older_section or alignment.newer_section)["item_key"]

    try:
        response = call_responses_parse(
            client,
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(alignment)},
            ],
            text_format=_ClassificationSchema,
            reasoning={"effort": reasoning_effort},
        )
        parsed = response.output_parsed
        log_usage(logger, "openai_call", response, stage="classify", model=model, item_key=item_key)
    except Exception:
        # The SDK can raise a validation error (not just return output_parsed
        # = None) when the model's output is truncated mid-JSON -- a real,
        # if infrequent, LLM API characteristic no prompt fully prevents.
        # Degrade to zero findings for this alignment rather than crashing
        # the whole pipeline run.
        parsed = None
        log_event(logger, "openai_call_failed", stage="classify", model=model, item_key=item_key)

    if parsed is None:
        return []
    return [
        Finding(item_key=item_key, **finding.model_dump())
        for finding in parsed.findings
    ]
