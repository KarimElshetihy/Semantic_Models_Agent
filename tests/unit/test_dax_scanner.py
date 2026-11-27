"""DAX scanner tests: which references are found, and which text is refused rather than guessed."""

import pytest

from ssas_agent.validation import scan_dax


def reference_pairs(expression):
    scan = scan_dax(expression)
    assert scan.problem is None, scan.problem
    return [(reference.table, reference.name) for reference in scan.references]


def test_quoted_table_reference_is_found():
    assert reference_pairs("SUM('Sales Data'[Amount])") == [("Sales Data", "Amount")]


def test_plain_table_reference_is_found():
    assert reference_pairs("SUM(Sales[Amount])") == [("Sales", "Amount")]


def test_space_between_table_and_bracket_is_allowed():
    assert reference_pairs("SUM(Sales [Amount])") == [("Sales", "Amount")]


def test_unqualified_reference_is_found():
    assert reference_pairs("[Total] * 2") == [(None, "Total")]


def test_several_references_in_one_expression_are_all_found():
    expression = "DIVIDE([Sales], [Target], 0) + SUM('Dim Date'[Year])"

    found = reference_pairs(expression)

    assert sorted(found, key=str) == sorted([(None, "Sales"), (None, "Target"), ("Dim Date", "Year")], key=str)


def test_doubled_quote_inside_quoted_table_name_is_unescaped():
    assert reference_pairs("SUM('O''Brien'[Amount])") == [("O'Brien", "Amount")]


def test_text_inside_string_literal_is_ignored():
    assert reference_pairs('IF(Status = "Sales[Amount] and [Ghost]", 1, 0)') == []


def test_doubled_quote_inside_string_literal_is_ignored():
    assert reference_pairs('"say ""[Ghost]"" now" & [Real]') == [(None, "Real")]


def test_line_comments_are_ignored():
    assert reference_pairs("// [Ghost]\n[Real]") == [(None, "Real")]
    assert reference_pairs("-- [Ghost]\n[Real]") == [(None, "Real")]


def test_block_comment_is_ignored():
    assert reference_pairs("/* [Ghost] */ [Real]") == [(None, "Real")]


def test_comment_markers_inside_quoted_table_name_are_not_comments():
    assert reference_pairs("SUM('A//B--C'[Amount])") == [("A//B--C", "Amount")]


@pytest.mark.parametrize(
    "expression, problem_fragment",
    [
        ('IF(x = "unterminated, 1, 0)', "unterminated string literal"),
        ("/* never closed [Real]", "unterminated block comment"),
        ("SUM('Sales[Amount])", "unterminated quoted table or column name"),
        ("[Total", "unbalanced brackets"),
        ("Total]", "closing bracket without an opening bracket"),
        ("[A]]", "escaped ']' inside a name is not supported"),
    ],
)
def test_text_the_scanner_cannot_read_is_reported_not_guessed(expression, problem_fragment):
    scan = scan_dax(expression)

    assert scan.problem is not None
    assert problem_fragment in scan.problem
    assert scan.references == ()


def test_references_are_kept_as_written_for_evidence():
    scan = scan_dax("SUM('Sales Data'[Amount])")

    assert scan.references[0].text == "'Sales Data'[Amount]"


def test_empty_expression_has_no_references_and_no_problem():
    scan = scan_dax("")

    assert scan.problem is None
    assert scan.references == ()
