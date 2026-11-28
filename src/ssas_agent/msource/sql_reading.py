"""Reads one SQL statement: the tables named after FROM and JOIN, and the columns of the top-level SELECT.

Only what the text shows is reported. A select list with expressions, a comma-joined FROM list, or a
UNION is reported as a note, and the columns are not guessed. String literals and comments are blanked
first (code_only from the SQL checks), so words inside them are never read as tables or columns.
"""

from __future__ import annotations

import re

from ssas_agent.generation.sql_checks import code_only
from ssas_agent.msource.records import SourceColumn, SourceReference, SqlReading

FROM_OR_JOIN = re.compile(r'\b(?:FROM|JOIN)\s+("?[A-Za-z_][\w$#]*"?(?:\s*\.\s*"?[A-Za-z_][\w$#]*"?)?)', re.IGNORECASE)
CTE_NAME = re.compile(r'(?:\bWITH|,)\s*("?[A-Za-z_][\w$#]*"?)\s+AS\s*\(', re.IGNORECASE)
SELECT_KEYWORD = re.compile(r"\bSELECT\b", re.IGNORECASE)
FROM_KEYWORD = re.compile(r"\bFROM\b", re.IGNORECASE)
DISTINCT_PREFIX = re.compile(r"\A\s*DISTINCT\b", re.IGNORECASE)
FROM_CLAUSE_END = re.compile(r"\b(?:WHERE|GROUP|HAVING|ORDER|UNION|LIMIT|FETCH|QUALIFY)\b", re.IGNORECASE)
PLAIN_COLUMN = re.compile(
    r'\s*(?:"?[A-Za-z_]\w*"?\s*\.\s*)?("?[A-Za-z_]\w*"?)'
    r'(?:\s+(?:AS\s+)?("?[A-Za-z_]\w*"?))?\s*\Z',
    re.IGNORECASE,
)
ALL_COLUMNS = re.compile(r"(?:[A-Za-z_]\w*\s*\.\s*)?\*")
NOT_A_COLUMN_WORDS = frozenset({"NULL", "TRUE", "FALSE", "CASE", "CAST", "DISTINCT", "ALL"})

EXPRESSION_NOTE = "select list has expressions; those columns are not listed"
COMMA_JOIN_NOTE = "comma-joined tables after FROM are not listed"
MULTIPLE_SELECT_NOTE = "more than one top-level SELECT (UNION?); only the first select's columns are listed"


def read_sql(sql: str, first_line: int = 1) -> SqlReading:
    """Read one statement. `first_line` is the M line where the SQL text starts, so references get M line numbers."""
    code, literal_findings = code_only(sql)
    problems = [finding.evidence for finding in literal_findings]
    depths = _depths(code)
    selects = _top_level_matches(SELECT_KEYWORD, code, depths)
    main_from = _first_top_level(FROM_KEYWORD, code, depths, after=selects[0].end()) if selects else None
    if not selects or main_from is None:
        problems.append("no top-level SELECT ... FROM found")
    if problems:
        return SqlReading(references=(), select_all=False, columns=(), problems=tuple(problems), notes=())
    notes = _statement_notes(code, depths, selects, main_from)
    references = _references(sql, code, first_line)
    select_all, columns, column_notes = _select_list(sql, code, selects[0], main_from, first_line)
    return SqlReading(
        references=references,
        select_all=select_all,
        columns=columns,
        problems=(),
        notes=tuple(notes + column_notes),
    )


def _statement_notes(
    code: str,
    depths: list[int],
    selects: list[re.Match[str]],
    main_from: re.Match[str],
) -> list[str]:
    notes = [COMMA_JOIN_NOTE] if _from_list_has_comma(code, depths, main_from) else []
    if len(selects) > 1:
        notes.append(MULTIPLE_SELECT_NOTE)
    return notes


def _from_list_has_comma(code: str, depths: list[int], main_from: re.Match[str]) -> bool:
    """True when the top-level FROM clause lists more than one table with commas."""
    clause_end = _first_top_level(FROM_CLAUSE_END, code, depths, after=main_from.end())
    end = clause_end.start() if clause_end else len(code)
    return any(code[index] == "," and depths[index] == 0 for index in range(main_from.end(), end))


def _references(sql: str, code: str, first_line: int) -> tuple[SourceReference, ...]:
    common_table_expressions = _cte_names(code)
    references = []
    for match in FROM_OR_JOIN.finditer(code):
        reference_text = sql[match.start(1) : match.end(1)]
        schema, name = _split_reference(reference_text)
        if schema is None and name.casefold() in common_table_expressions:
            continue
        references.append(
            SourceReference(
                reference=reference_text,
                schema=schema,
                name=name,
                line=_line_of(sql, match.start(1), first_line),
            )
        )
    return tuple(references)


def _cte_names(code: str) -> set[str]:
    return {_plain(match.group(1)).casefold() for match in CTE_NAME.finditer(code)}


def _select_list(
    sql: str,
    code: str,
    select: re.Match[str],
    main_from: re.Match[str],
    first_line: int,
) -> tuple[bool, tuple[SourceColumn, ...], list[str]]:
    region_start = select.end()
    region = code[region_start : main_from.start()]
    distinct = DISTINCT_PREFIX.match(region)
    if distinct:
        region_start += distinct.end()
        region = region[distinct.end() :]
    select_all = False
    columns: list[SourceColumn] = []
    notes: list[str] = []
    for offset, item in _split_top_level(region):
        item_selects_all, column, note = _select_item(sql, item, region_start + offset, first_line)
        select_all = select_all or item_selects_all
        if column is not None:
            columns.append(column)
        if note is not None and EXPRESSION_NOTE not in notes:
            notes.append(note)
    return select_all, tuple(columns), notes


def _select_item(
    sql: str,
    item: str,
    item_start: int,
    first_line: int,
) -> tuple[bool, SourceColumn | None, str | None]:
    """Classify one select-list item: all columns, one plain column, or an expression."""
    stripped = item.strip()
    if ALL_COLUMNS.fullmatch(stripped):
        return True, None, None
    plain = PLAIN_COLUMN.match(item)
    if plain is None or _plain(plain.group(1)).upper() in NOT_A_COLUMN_WORDS:
        return False, None, EXPRESSION_NOTE
    leading = len(item) - len(item.lstrip())
    column_start = item_start + leading
    alias = plain.group(2)
    column = SourceColumn(
        name=_plain(plain.group(1)),
        line=_line_of(sql, column_start, first_line),
        alias=_plain(alias) if alias else None,
    )
    return False, column, None


def _split_top_level(text: str) -> list[tuple[int, str]]:
    """Split on commas that are not inside parentheses. Returns (offset, item) pairs."""
    items: list[tuple[int, str]] = []
    depth = 0
    start = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            items.append((start, text[start:index]))
            start = index + 1
    items.append((start, text[start:]))
    return items


def _depths(code: str) -> list[int]:
    """Parenthesis depth in front of each character."""
    depths: list[int] = []
    depth = 0
    for character in code:
        depths.append(depth)
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
    return depths


def _top_level_matches(pattern: re.Pattern[str], code: str, depths: list[int]) -> list[re.Match[str]]:
    return [match for match in pattern.finditer(code) if depths[match.start()] == 0]


def _first_top_level(pattern: re.Pattern[str], code: str, depths: list[int], after: int) -> re.Match[str] | None:
    for match in pattern.finditer(code, after):
        if depths[match.start()] == 0:
            return match
    return None


def _split_reference(text: str) -> tuple[str | None, str]:
    parts = [_plain(part) for part in re.split(r"\s*\.\s*", text.strip())]
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, parts[0]


def _plain(text: str) -> str:
    return text.strip().strip('"')


def _line_of(sql: str, position: int, first_line: int) -> int:
    return first_line + sql.count("\n", 0, position)

