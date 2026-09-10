from types import SimpleNamespace

from src.agents.aligner import SectionAlignment
from src.agents.classifier import Finding
from src.agents.verifier import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_REASONING_EFFORT,
    PROMPT_VERSION,
    excerpts_verified,
    verify_finding,
)


def _section(item_key: str, body_text: str = "some section text") -> dict:
    return {"item_key": item_key, "heading_text": f"Item {item_key}.", "body_text": body_text}


def _finding(**overrides) -> Finding:
    data = {
        "item_key": "1A",
        "category": "substantive_change",
        "tier": "high",
        "reasoning": "Something changed.",
        "older_excerpt": "old sentence",
        "newer_excerpt": "new sentence",
    }
    data.update(overrides)
    return Finding(**data)


class _StubResponses:
    def __init__(self, verification_data):
        self._verification_data = verification_data
        self.calls = []

    def parse(self, *, model, input, text_format, reasoning=None):
        self.calls.append({"model": model, "input": input, "reasoning": reasoning})
        return SimpleNamespace(output_parsed=text_format(**self._verification_data))


class _StubOpenAIClient:
    def __init__(self, verification_data):
        self.responses = _StubResponses(verification_data)


class _StubResponsesNoOutput:
    def __init__(self):
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=None)


class _StubOpenAIClientNoOutput:
    def __init__(self):
        self.responses = _StubResponsesNoOutput()


# --- Layer 1: excerpts_verified (no LLM involved) ---


def test_verbatim_excerpt_passes():
    finding = _finding(older_excerpt="exact quote", newer_excerpt=None)
    alignment = SectionAlignment(
        status="removed",
        older_section=_section("1A", "prefix exact quote suffix"),
        newer_section=None,
        similarity=None,
    )
    assert excerpts_verified(finding, alignment) is True


def test_whitespace_varied_excerpt_passes():
    finding = _finding(older_excerpt="exact   quote\nhere", newer_excerpt=None)
    alignment = SectionAlignment(
        status="removed",
        older_section=_section("1A", "prefix exact quote here suffix"),
        newer_section=None,
        similarity=None,
    )
    assert excerpts_verified(finding, alignment) is True


def test_hallucinated_excerpt_fails():
    finding = _finding(older_excerpt="this was never said", newer_excerpt=None)
    alignment = SectionAlignment(
        status="removed",
        older_section=_section("1A", "completely different content"),
        newer_section=None,
        similarity=None,
    )
    assert excerpts_verified(finding, alignment) is False


def test_none_excerpt_trivially_passes():
    finding = _finding(older_excerpt=None, newer_excerpt="new quote")
    alignment = SectionAlignment(
        status="new",
        older_section=None,
        newer_section=_section("1A", "new quote here"),
        similarity=None,
    )
    assert excerpts_verified(finding, alignment) is True


def test_excerpt_present_but_body_text_missing_fails():
    finding = _finding(older_excerpt="some quote", newer_excerpt=None)
    alignment = SectionAlignment(
        status="removed",
        older_section=None,  # no section at all, but finding still cites older_excerpt
        newer_section=None,
        similarity=None,
    )
    assert excerpts_verified(finding, alignment) is False


# --- Hard-fail path: short-circuits before any LLM call ---


def test_hard_fail_short_circuits_without_llm_call():
    finding = _finding(older_excerpt="never said this", tier="high")
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A", "totally unrelated text"),
        newer_section=_section("1A", "new sentence here"),
        similarity=0.9,
    )
    client = _StubOpenAIClient({"confidence": 0.9, "final_tier": "high", "reasoning": "n/a"})

    result = verify_finding(finding, alignment, client=client)

    assert result.excerpt_verified is False
    assert result.confidence == 0.0
    assert result.final_tier == "low"
    assert client.responses.calls == []


# --- Layer 2: LLM-based judgment ---


def test_verified_finding_parses_llm_output():
    finding = _finding(older_excerpt="old sentence", newer_excerpt="new sentence")
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A", "prefix old sentence suffix"),
        newer_section=_section("1A", "prefix new sentence suffix"),
        similarity=0.9,
    )
    client = _StubOpenAIClient(
        {"confidence": 0.85, "final_tier": "medium", "reasoning": "Reasonably supported."}
    )

    result = verify_finding(finding, alignment, client=client)

    assert result.excerpt_verified is True
    assert result.confidence == 0.85
    assert result.final_tier == "medium"
    assert result.verifier_reasoning == "Reasonably supported."


def test_none_output_parsed_degrades_and_keeps_original_tier():
    finding = _finding(older_excerpt="old sentence", newer_excerpt="new sentence", tier="high")
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A", "prefix old sentence suffix"),
        newer_section=_section("1A", "prefix new sentence suffix"),
        similarity=0.9,
    )
    client = _StubOpenAIClientNoOutput()

    result = verify_finding(finding, alignment, client=client)

    assert result.excerpt_verified is True
    assert result.confidence == 0.0
    assert result.final_tier == "high"  # infra failure keeps original, doesn't force "low"


def test_sends_correct_model_reasoning_and_prompt_version():
    finding = _finding(older_excerpt="old sentence", newer_excerpt="new sentence")
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A", "prefix old sentence suffix"),
        newer_section=_section("1A", "prefix new sentence suffix"),
        similarity=0.9,
    )
    client = _StubOpenAIClient({"confidence": 0.5, "final_tier": "low", "reasoning": "r"})

    result = verify_finding(finding, alignment, client=client)

    call = client.responses.calls[0]
    assert call["model"] == DEFAULT_CHAT_MODEL
    assert call["reasoning"] == {"effort": DEFAULT_REASONING_EFFORT}
    assert result.verifier_model == DEFAULT_CHAT_MODEL
    assert result.verifier_prompt_version == PROMPT_VERSION


def test_tier_downgrade_flows_through():
    finding = _finding(tier="high", older_excerpt="old sentence", newer_excerpt="new sentence")
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A", "prefix old sentence suffix"),
        newer_section=_section("1A", "prefix new sentence suffix"),
        similarity=0.9,
    )
    client = _StubOpenAIClient(
        {"confidence": 0.15, "final_tier": "low", "reasoning": "Overclaimed."}
    )

    result = verify_finding(finding, alignment, client=client)

    assert result.finding.tier == "high"  # original preserved for audit trail
    assert result.final_tier == "low"  # verifier's independent assessment
