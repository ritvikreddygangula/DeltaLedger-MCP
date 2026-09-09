from dataclasses import dataclass
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from .aligner import SectionAlignment

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
        return (
            f"SECTION: Item {item_key} -- {heading_text}\n"
            f"ALIGNMENT: matched between an older and newer filing "
            f"(embedding similarity {alignment.similarity:.4f}).\n"
            "Compare the two versions below; report only substantive differences.\n\n"
            "=== OLDER FILING TEXT ===\n"
            f"{older['body_text']}\n\n"
            "=== NEWER FILING TEXT ===\n"
            f"{newer['body_text']}"
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

    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(alignment)},
        ],
        text_format=_ClassificationSchema,
        reasoning={"effort": reasoning_effort},
    )

    parsed = response.output_parsed
    if parsed is None:
        return []
    return [
        Finding(item_key=item_key, **finding.model_dump())
        for finding in parsed.findings
    ]
