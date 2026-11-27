"""Find table and column references in DAX text.

This is a pattern scanner, not a DAX parser. It first blanks out string literals
and comments, so text inside them is never read as a reference. Text it cannot
read reliably is reported as a problem, and no references are returned for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

QUOTED_TABLE_QUALIFIED = re.compile(r"'((?:[^']|'')+)'\s*\[([^\]]+)\]")
PLAIN_TABLE_QUALIFIED = re.compile(r"(?<![\w'\]])([A-Za-z_]\w*)\s*\[([^\]]+)\]")
UNQUALIFIED = re.compile(r"\[([^\]]+)\]")
QUOTED_NAME = re.compile(r"'(?:[^']|'')*'")
LINE_COMMENT_STARTS = ("//", "--")
BLOCK_COMMENT_START = "/*"
BLOCK_COMMENT_END = "*/"


@dataclass(frozen=True)
class DaxReference:
    table: str | None
    name: str
    text: str


@dataclass(frozen=True)
class DaxScan:
    references: tuple[DaxReference, ...]
    problem: str | None


def scan_dax(expression: str) -> DaxScan:
    code, problem = _blank_strings_and_comments(expression)
    if problem is None:
        problem = _bracket_problem(code)
    if problem is not None:
        return DaxScan(references=(), problem=problem)
    return DaxScan(references=tuple(_extract_references(code)), problem=None)


def _blank_strings_and_comments(expression: str) -> tuple[str, str | None]:
    """Replace string literals and comments with spaces. Quoted names are kept, because they are references."""
    chars = list(expression)
    position = 0
    while position < len(expression):
        character = expression[position]
        if character == "'":
            end = _matching_quote(expression, position, "'")
            if end is None:
                return expression, "unterminated quoted table or column name"
            position = end
            continue
        end, problem = _end_of_literal_or_comment(expression, position)
        if problem is not None:
            return expression, problem
        if end is None:
            position += 1
            continue
        _blank(chars, position, end)
        position = end
    return "".join(chars), None


def _end_of_literal_or_comment(expression: str, position: int) -> tuple[int | None, str | None]:
    if expression[position] == '"':
        end = _matching_quote(expression, position, '"')
        return (end, None) if end is not None else (None, "unterminated string literal")
    if expression.startswith(LINE_COMMENT_STARTS, position):
        line_end = expression.find("\n", position)
        return (len(expression) if line_end == -1 else line_end), None
    if expression.startswith(BLOCK_COMMENT_START, position):
        block_end = expression.find(BLOCK_COMMENT_END, position + len(BLOCK_COMMENT_START))
        if block_end == -1:
            return None, "unterminated block comment"
        return block_end + len(BLOCK_COMMENT_END), None
    return None, None


def _matching_quote(expression: str, start: int, quote: str) -> int | None:
    """Return the index just after the closing quote. A doubled quote inside is an escaped quote."""
    position = start + 1
    while position < len(expression):
        if expression[position] == quote:
            if expression.startswith(quote, position + 1):
                position += 2
                continue
            return position + 1
        position += 1
    return None


def _blank(chars: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        chars[index] = " "


def _bracket_problem(code: str) -> str | None:
    without_names = QUOTED_NAME.sub(" ", code)
    if "]]" in without_names:
        return "escaped ']' inside a name is not supported"
    depth = 0
    for character in without_names:
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth < 0:
                return "closing bracket without an opening bracket"
    return "unbalanced brackets" if depth != 0 else None


def _extract_references(code: str) -> list[DaxReference]:
    references: list[DaxReference] = []
    working = code
    for match in QUOTED_TABLE_QUALIFIED.finditer(working):
        table = match.group(1).replace("''", "'")
        references.append(DaxReference(table=table, name=match.group(2), text=match.group(0)))
    working = QUOTED_TABLE_QUALIFIED.sub(_spaces_for_match, working)
    for match in PLAIN_TABLE_QUALIFIED.finditer(working):
        references.append(DaxReference(table=match.group(1), name=match.group(2), text=match.group(0)))
    working = PLAIN_TABLE_QUALIFIED.sub(_spaces_for_match, working)
    for match in UNQUALIFIED.finditer(working):
        references.append(DaxReference(table=None, name=match.group(1), text=match.group(0)))
    return references


def _spaces_for_match(match: re.Match[str]) -> str:
    return " " * len(match.group(0))
