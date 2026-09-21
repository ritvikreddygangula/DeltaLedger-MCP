from src.agents.diffing import diff_sections


def test_returns_full_text_when_nothing_in_common():
    older, newer = diff_sections("completely different content here", "totally unrelated other content")
    assert older == "completely different content here"
    assert newer == "totally unrelated other content"


def test_keeps_only_changed_lines_plus_context():
    shared_prefix = "\n".join(f"unchanged line {i}" for i in range(20))
    shared_suffix = "\n".join(f"unchanged line {i}" for i in range(20, 40))
    older_text = f"{shared_prefix}\nold specific line\n{shared_suffix}"
    newer_text = f"{shared_prefix}\nnew specific line\n{shared_suffix}"

    older_diff, newer_diff = diff_sections(older_text, newer_text)

    assert "old specific line" in older_diff
    assert "new specific line" in newer_diff
    assert len(older_diff) < len(older_text)
    assert len(newer_diff) < len(newer_text)
    assert "unchanged line 19" in older_diff  # context immediately before the change
    assert "unchanged line 0" not in older_diff  # far from any change, dropped


def test_identical_text_falls_back_to_full_text():
    text = "same content\non every line"
    older, newer = diff_sections(text, text)
    assert older == text
    assert newer == text


def test_diffed_excerpt_is_always_a_verbatim_substring():
    # Critical invariant: the verifier's Layer-1 hallucination check
    # substring-matches a cited excerpt against the FULL original body_text
    # (see verifier.excerpts_verified), never against whatever diffed text
    # was shown to the LLM -- so the diff must only omit whole unchanged
    # lines, never alter or reorder the lines it keeps.
    shared = "\n".join(f"line {i}" for i in range(10))
    older_text = f"{shared}\nold change\n{shared}"
    newer_text = f"{shared}\nnew change\n{shared}"

    older_diff, newer_diff = diff_sections(older_text, newer_text)

    for line in older_diff.split("\n"):
        assert line in older_text.split("\n")
    for line in newer_diff.split("\n"):
        assert line in newer_text.split("\n")
