"""Text diff tests for review artifacts."""

from ssas_agent.diff import unified_text_diff


def test_identical_bytes_produce_empty_text_diff():
    content = b'{\r\n  "a": 1\r\n}'

    assert unified_text_diff(content, content, "Model.bim") == ""


def test_single_line_edit_shows_removed_and_added_line():
    before = b'{\r\n  "a": 1\r\n}'
    after = b'{\r\n  "a": 2\r\n}'

    diff_text = unified_text_diff(before, after, "Model.bim")

    assert "--- Model.bim (before)" in diff_text
    assert "+++ Model.bim (after)" in diff_text
    assert '-  "a": 1' in diff_text
    assert '+  "a": 2' in diff_text
