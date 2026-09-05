from pathlib import Path

from src.connectors.section_parser import parse_10k_sections

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_10k_trimmed.html"


def _load_fixture_sections():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    return parse_10k_sections(html)


def test_tags_exactly_the_four_target_items():
    sections = _load_fixture_sections()

    assert {s.item_key for s in sections} == {"1A", "3", "7", "8"}


def test_bodies_have_substantial_content():
    sections = {s.item_key: s for s in _load_fixture_sections()}

    for item_key in ("1A", "3", "7"):
        assert len(sections[item_key].body_text) > 100


def test_item_1a_body_does_not_bleed_into_item_1b():
    sections = {s.item_key: s for s in _load_fixture_sections()}

    assert "Item 1B" not in sections["1A"].body_text
    assert "Unresolved Staff Comments" not in sections["1A"].body_text


def test_item_3_body_does_not_bleed_into_item_4():
    sections = {s.item_key: s for s in _load_fixture_sections()}

    assert "Item 4" not in sections["3"].body_text
    assert "Mine Safety" not in sections["3"].body_text


def test_item_7_body_does_not_bleed_into_item_7a():
    sections = {s.item_key: s for s in _load_fixture_sections()}

    assert "7A" not in sections["7"].body_text
    assert "Market Risk" not in sections["7"].body_text


def test_item_8_body_does_not_bleed_into_item_9():
    sections = {s.item_key: s for s in _load_fixture_sections()}

    assert "Item 9" not in sections["8"].body_text
    assert "Disagreements with Accountants" not in sections["8"].body_text


def test_selects_real_heading_over_table_of_contents_entry():
    sections = {s.item_key: s for s in _load_fixture_sections()}

    # The ToC entry for Item 3 is immediately followed by the Item 4 ToC
    # entry -- if the parser had picked the ToC occurrence instead of the
    # real heading, this body would be a few characters long, not a full
    # paragraph.
    assert "ordinary course of business" in sections["3"].body_text


def test_handles_nbsp_between_item_and_number():
    sections = {s.item_key: s for s in _load_fixture_sections()}

    assert "1A" in sections
    assert "risks" in sections["1A"].body_text.lower()


def test_missing_section_is_omitted_not_an_error():
    html = """
    <html><body>
    <div>Item 1A. Risk Factors</div>
    <p>Some risk factor content that is long enough to look like a real section
    body rather than a table of contents entry, spanning well past four
    hundred characters so the gap-based heuristic treats it as genuine. Padding
    padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding.</p>
    <div>Item 9. Changes in and Disagreements with Accountants</div>
    <p>None.</p>
    </body></html>
    """

    sections = parse_10k_sections(html)

    assert {s.item_key for s in sections} == {"1A"}
