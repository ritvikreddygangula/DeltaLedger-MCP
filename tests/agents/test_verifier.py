from types import SimpleNamespace

from src.agents.aligner import SectionAlignment
from src.agents.classifier import Finding
from src.agents.verifier import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_REASONING_EFFORT,
    PROMPT_VERSION,
    excerpts_verified,
    verify_findings_for_alignment,
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


def _matched_alignment(older_text="prefix old sentence suffix", newer_text="prefix new sentence suffix"):
    return SectionAlignment(
        status="matched",
        older_section=_section("1A", older_text),
        newer_section=_section("1A", newer_text),
        similarity=0.9,
    )


class _StubResponses:
    def __init__(self, verifications_data):
        self._verifications_data = verifications_data
        self.calls = []

    def parse(self, *, model, input, text_format, reasoning=None):
        self.calls.append({"model": model, "input": input, "reasoning": reasoning})
        return SimpleNamespace(output_parsed=text_format(verifications=self._verifications_data))


class _StubOpenAIClient:
    def __init__(self, verifications_data):
        self.responses = _StubResponses(verifications_data)


class _StubResponsesNoOutput:
    def __init__(self):
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=None)


class _StubOpenAIClientNoOutput:
    def __init__(self):
        self.responses = _StubResponsesNoOutput()


class _StubResponsesRaises:
    def parse(self, **kwargs):
        raise ValueError("Invalid JSON: EOF while parsing a string")


class _StubOpenAIClientRaises:
    def __init__(self):
        self.responses = _StubResponsesRaises()


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
        status="removed", older_section=None, newer_section=None, similarity=None
    )
    assert excerpts_verified(finding, alignment) is False


# --- Batched verification ---


def test_empty_findings_returns_empty_list_no_llm_call():
    client = _StubOpenAIClient([])
    result = verify_findings_for_alignment([], _matched_alignment(), client=client)
    assert result == []
    assert client.responses.calls == []


def test_single_finding_verified_in_one_call():
    finding = _finding()
    client = _StubOpenAIClient(
        [{"confidence": 0.85, "final_tier": "medium", "reasoning": "Reasonably supported."}]
    )

    result = verify_findings_for_alignment([finding], _matched_alignment(), client=client)

    assert len(result) == 1
    assert result[0].excerpt_verified is True
    assert result[0].confidence == 0.85
    assert result[0].final_tier == "medium"
    assert len(client.responses.calls) == 1


def test_multiple_findings_verified_in_a_single_batched_call():
    findings = [
        _finding(category="new_litigation", tier="high"),
        _finding(category="accounting_policy_change", tier="low"),
    ]
    client = _StubOpenAIClient(
        [
            {"confidence": 0.9, "final_tier": "high", "reasoning": "First claim holds up."},
            {"confidence": 0.2, "final_tier": "low", "reasoning": "Second claim is weak."},
        ]
    )

    result = verify_findings_for_alignment(findings, _matched_alignment(), client=client)

    assert len(result) == 2
    assert len(client.responses.calls) == 1  # one call for both, not two
    assert result[0].confidence == 0.9
    assert result[0].final_tier == "high"
    assert result[1].confidence == 0.2
    assert result[1].final_tier == "low"


def test_hallucinated_finding_hard_fails_without_entering_the_batch():
    good_finding = _finding(older_excerpt="old sentence", newer_excerpt="new sentence")
    bad_finding = _finding(older_excerpt="never actually said", newer_excerpt=None)
    alignment = _matched_alignment()
    client = _StubOpenAIClient(
        [{"confidence": 0.9, "final_tier": "high", "reasoning": "Holds up."}]
    )

    result = verify_findings_for_alignment([good_finding, bad_finding], alignment, client=client)

    assert len(result) == 2
    by_excerpt = {r.finding.older_excerpt: r for r in result}
    assert by_excerpt["old sentence"].excerpt_verified is True
    assert by_excerpt["old sentence"].confidence == 0.9
    assert by_excerpt["never actually said"].excerpt_verified is False
    assert by_excerpt["never actually said"].confidence == 0.0
    # Only the surviving finding was sent to the LLM -- one call, one claim.
    assert len(client.responses.calls) == 1


def test_all_hallucinated_findings_make_zero_llm_calls():
    findings = [
        _finding(older_excerpt="never said this", newer_excerpt=None),
        _finding(older_excerpt="nor this", newer_excerpt=None),
    ]
    alignment = SectionAlignment(
        status="removed",
        older_section=_section("1A", "completely unrelated content"),
        newer_section=None,
        similarity=None,
    )
    client = _StubOpenAIClient([{"confidence": 0.9, "final_tier": "high", "reasoning": "n/a"}])

    result = verify_findings_for_alignment(findings, alignment, client=client)

    assert all(r.excerpt_verified is False for r in result)
    assert all(r.confidence == 0.0 for r in result)
    assert client.responses.calls == []


def test_count_mismatch_degrades_all_needing_llm_to_fallback():
    findings = [_finding(tier="high"), _finding(tier="medium")]
    # Only one verification returned for two findings -- a malformed/
    # mismatched response, not a valid one to trust.
    client = _StubOpenAIClient(
        [{"confidence": 0.9, "final_tier": "high", "reasoning": "only one"}]
    )

    result = verify_findings_for_alignment(findings, _matched_alignment(), client=client)

    assert len(result) == 2
    assert all(r.confidence == 0.0 for r in result)
    assert {r.final_tier for r in result} == {"high", "medium"}  # each keeps its own original tier


def test_none_output_parsed_degrades_and_keeps_each_original_tier():
    findings = [_finding(tier="high"), _finding(tier="low")]
    client = _StubOpenAIClientNoOutput()

    result = verify_findings_for_alignment(findings, _matched_alignment(), client=client)

    assert len(result) == 2
    assert all(r.excerpt_verified is True for r in result)
    assert all(r.confidence == 0.0 for r in result)
    assert {r.final_tier for r in result} == {"high", "low"}


def test_parse_exception_degrades_instead_of_crashing():
    finding = _finding(tier="high")
    client = _StubOpenAIClientRaises()

    result = verify_findings_for_alignment([finding], _matched_alignment(), client=client)

    assert len(result) == 1
    assert result[0].confidence == 0.0
    assert result[0].final_tier == "high"


def test_sends_correct_model_and_reasoning_effort():
    client = _StubOpenAIClient(
        [{"confidence": 0.5, "final_tier": "low", "reasoning": "r"}]
    )

    verify_findings_for_alignment([_finding()], _matched_alignment(), client=client)

    call = client.responses.calls[0]
    assert call["model"] == DEFAULT_CHAT_MODEL
    assert call["reasoning"] == {"effort": DEFAULT_REASONING_EFFORT}


def test_batch_prompt_includes_every_claim():
    findings = [
        _finding(category="new_litigation", older_excerpt="old sentence"),
        _finding(category="accounting_policy_change", older_excerpt="another old sentence"),
    ]
    alignment = _matched_alignment(older_text="old sentence and another old sentence appear here")
    client = _StubOpenAIClient(
        [
            {"confidence": 0.5, "final_tier": "low", "reasoning": "r1"},
            {"confidence": 0.5, "final_tier": "low", "reasoning": "r2"},
        ]
    )

    verify_findings_for_alignment(findings, alignment, client=client)

    user_prompt = client.responses.calls[0]["input"][1]["content"]
    assert "CLAIM 1" in user_prompt
    assert "CLAIM 2" in user_prompt
    assert "new_litigation" in user_prompt
    assert "accounting_policy_change" in user_prompt


def test_prompt_version_recorded_on_result():
    client = _StubOpenAIClient(
        [{"confidence": 0.5, "final_tier": "low", "reasoning": "r"}]
    )

    (result,) = verify_findings_for_alignment([_finding()], _matched_alignment(), client=client)

    assert result.verifier_prompt_version == PROMPT_VERSION
