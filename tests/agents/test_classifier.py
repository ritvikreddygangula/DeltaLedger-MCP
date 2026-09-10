from types import SimpleNamespace

from src.agents.aligner import SectionAlignment
from src.agents.classifier import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_REASONING_EFFORT,
    classify_alignment,
)


def _section(item_key: str, body_text: str = "some section text") -> dict:
    return {"item_key": item_key, "heading_text": f"Item {item_key}.", "body_text": body_text}


def _finding_data(**overrides) -> dict:
    data = {
        "category": "substantive_change",
        "tier": "medium",
        "reasoning": "Something changed.",
        "older_excerpt": "old sentence",
        "newer_excerpt": "new sentence",
    }
    data.update(overrides)
    return data


class _StubResponses:
    def __init__(self, findings_data):
        self._findings_data = findings_data
        self.calls = []

    def parse(self, *, model, input, text_format, reasoning=None):
        self.calls.append({"model": model, "input": input, "reasoning": reasoning})
        return SimpleNamespace(output_parsed=text_format(findings=self._findings_data))


class _StubOpenAIClient:
    def __init__(self, findings_data):
        self.responses = _StubResponses(findings_data)


class _StubResponsesNoOutput:
    def parse(self, **kwargs):
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


def test_matched_alignment_returns_one_finding():
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A", "old risk text"),
        newer_section=_section("1A", "new risk text"),
        similarity=0.9,
    )
    client = _StubOpenAIClient([_finding_data()])

    findings = classify_alignment(alignment, client=client)

    assert len(findings) == 1
    assert findings[0].item_key == "1A"
    assert findings[0].category == "substantive_change"
    assert findings[0].tier == "medium"


def test_matched_alignment_can_return_zero_findings():
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("7"),
        newer_section=_section("7"),
        similarity=0.99,
    )
    client = _StubOpenAIClient([])

    findings = classify_alignment(alignment, client=client)

    assert findings == []


def test_removed_alignment_prompts_with_older_text_only():
    alignment = SectionAlignment(
        status="removed",
        older_section=_section("3", "litigation text"),
        newer_section=None,
        similarity=None,
    )
    client = _StubOpenAIClient([_finding_data(newer_excerpt=None)])

    findings = classify_alignment(alignment, client=client)

    assert findings[0].item_key == "3"
    assert findings[0].newer_excerpt is None
    user_prompt = client.responses.calls[0]["input"][1]["content"]
    assert "litigation text" in user_prompt
    assert "NEWER FILING TEXT" not in user_prompt


def test_new_alignment_prompts_with_newer_text_only():
    alignment = SectionAlignment(
        status="new",
        older_section=None,
        newer_section=_section("8", "financial statements text"),
        similarity=None,
    )
    client = _StubOpenAIClient([_finding_data(older_excerpt=None)])

    findings = classify_alignment(alignment, client=client)

    assert findings[0].item_key == "8"
    assert findings[0].older_excerpt is None
    user_prompt = client.responses.calls[0]["input"][1]["content"]
    assert "financial statements text" in user_prompt
    assert "OLDER FILING TEXT" not in user_prompt


def test_excerpt_round_trips_exactly():
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A"),
        newer_section=_section("1A"),
        similarity=0.9,
    )
    client = _StubOpenAIClient(
        [_finding_data(older_excerpt="exact old quote", newer_excerpt="exact new quote")]
    )

    findings = classify_alignment(alignment, client=client)

    assert findings[0].older_excerpt == "exact old quote"
    assert findings[0].newer_excerpt == "exact new quote"


def test_sends_correct_model_and_reasoning_effort():
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A"),
        newer_section=_section("1A"),
        similarity=0.9,
    )
    client = _StubOpenAIClient([])

    classify_alignment(alignment, client=client)

    call = client.responses.calls[0]
    assert call["model"] == DEFAULT_CHAT_MODEL
    assert call["reasoning"] == {"effort": DEFAULT_REASONING_EFFORT}


def test_none_output_parsed_degrades_to_empty_list():
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A"),
        newer_section=_section("1A"),
        similarity=0.9,
    )
    client = _StubOpenAIClientNoOutput()

    findings = classify_alignment(alignment, client=client)

    assert findings == []


def test_parse_exception_degrades_to_empty_list_instead_of_crashing():
    # Live-discovered bug (Part 6 eval run against LYV): the SDK can raise a
    # validation error, not just return output_parsed=None, when the model's
    # JSON output is truncated mid-string. Must degrade gracefully like the
    # None case, not propagate and crash the whole pipeline run.
    alignment = SectionAlignment(
        status="matched",
        older_section=_section("1A"),
        newer_section=_section("1A"),
        similarity=0.9,
    )
    client = _StubOpenAIClientRaises()

    findings = classify_alignment(alignment, client=client)

    assert findings == []
