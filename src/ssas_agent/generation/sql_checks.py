"""Text-only checks for a proposed Oracle SQL statement. No SQL parser and no database connection are used.

Checks: one read-only SELECT (or WITH) statement; no write or DDL keyword outside string literals and comments;
balanced parentheses; closed quotes and comments. Table and column names are NOT checked against a database,
and the meaning of the query is NOT checked. Those are reported as not checked, never as passed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ssas_agent.validation.findings import ERROR, WARNING

WRITE_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "GRANT",
    "REVOKE",
    "EXECUTE",
    "EXEC",
    "COMMIT",
    "ROLLBACK",
    "BEGIN",
    "CALL",
)
WRITE_PATTERN = re.compile(r"\b(" + "|".join(WRITE_KEYWORDS) + r")\b", re.IGNORECASE)
SELECT_START = re.compile(r"\s*(SELECT|WITH)\b", re.IGNORECASE)
SELECT_STAR = re.compile(r"\bSELECT\s+(DISTINCT\s+)?\*", re.IGNORECASE)
FROM_CLAUSE = re.compile(r"\bFROM\b", re.IGNORECASE)
NOT_CHECKED_NOTES = (
    "table and column names are not checked against a database",
    "the meaning and performance of the query are not checked",
    "rules are text-only; no SQL parser is used",
)


class SqlRule(StrEnum):
    EMPTY = "SQL-001"
    NOT_SELECT = "SQL-002"
    WRITE_KEYWORD = "SQL-003"
    MULTIPLE_STATEMENTS = "SQL-004"
    UNBALANCED_PARENTHESES = "SQL-005"
    UNCLOSED_LITERAL = "SQL-006"
    SELECT_STAR = "SQL-007"
    NO_FROM = "SQL-008"


SEVERITY: dict[SqlRule, str] = {
    SqlRule.EMPTY: ERROR,
    SqlRule.NOT_SELECT: ERROR,
    SqlRule.WRITE_KEYWORD: ERROR,
    SqlRule.MULTIPLE_STATEMENTS: ERROR,
    SqlRule.UNBALANCED_PARENTHESES: ERROR,
    SqlRule.UNCLOSED_LITERAL: ERROR,
    SqlRule.SELECT_STAR: WARNING,
    SqlRule.NO_FROM: WARNING,
}


@dataclass(frozen=True)
class SqlFinding:
    rule: SqlRule
    severity: str
    evidence: str


@dataclass(frozen=True)
class SqlReport:
    findings: tuple[SqlFinding, ...]
    not_checked: tuple[str, ...]

    @property
    def has_errors(self) -> bool:
        return any(finding.severity == ERROR for finding in self.findings)


def check_sql(sql: str) -> SqlReport:
    text = sql.strip()
    if not text:
        return SqlReport((_finding(SqlRule.EMPTY, "the statement is empty"),), NOT_CHECKED_NOTES)
    code, literal_findings = code_only(text)
    return SqlReport((*literal_findings, *_code_findings(code)), NOT_CHECKED_NOTES)


def code_only(text: str) -> tuple[str, list[SqlFinding]]:
    """Return the text with string literals and comments blanked out, keeping positions, plus any unclosed ones."""
    pieces: list[str] = []
    position = 0
    while position < len(text):
        skip_end, problem = _skippable_end(text, position)
        if skip_end is None:
            pieces.append(text[position])
            position += 1
            continue
        pieces.append(" " * (skip_end - position))
        position = skip_end
        if problem:
            return "".join(pieces) + " " * (len(text) - position), [_finding(SqlRule.UNCLOSED_LITERAL, problem)]
    return "".join(pieces), []


def _skippable_end(text: str, position: int) -> tuple[int | None, str | None]:
    """If a literal or comment starts here, return where it ends (and a problem if it never closes)."""
    if text.startswith("--", position):
        line_end = text.find("\n", position)
        return (len(text) if line_end == -1 else line_end), None
    if text.startswith("/*", position):
        comment_end = text.find("*/", position + 2)
        if comment_end == -1:
            return len(text), "a block comment is not closed"
        return comment_end + 2, None
    if text[position] == "'":
        literal_end = _literal_end(text, position)
        if literal_end is None:
            return len(text), "a string literal is not closed"
        return literal_end, None
    return None, None


def _literal_end(text: str, start: int) -> int | None:
    position = start + 1
    while position < len(text):
        if text[position] == "'":
            if text.startswith("''", position):
                position += 2
                continue
            return position + 1
        position += 1
    return None


def _code_findings(code: str) -> list[SqlFinding]:
    findings: list[SqlFinding] = []
    if not SELECT_START.match(code):
        findings.append(_finding(SqlRule.NOT_SELECT, "the statement must start with SELECT or WITH"))
    for keyword in sorted({match.group(0).upper() for match in WRITE_PATTERN.finditer(code)}):
        findings.append(_finding(SqlRule.WRITE_KEYWORD, f"keyword {keyword} is not allowed (read-only checks)"))
    if _has_more_than_one_statement(code):
        findings.append(_finding(SqlRule.MULTIPLE_STATEMENTS, "more than one statement (semicolon before the end)"))
    if not _parentheses_balanced(code):
        findings.append(_finding(SqlRule.UNBALANCED_PARENTHESES, "parentheses do not balance"))
    if SELECT_STAR.search(code):
        findings.append(_finding(SqlRule.SELECT_STAR, "SELECT * reads every column; name the columns"))
    if not FROM_CLAUSE.search(code):
        findings.append(_finding(SqlRule.NO_FROM, "no FROM clause found"))
    return findings


def _has_more_than_one_statement(code: str) -> bool:
    body = code.rstrip().rstrip(";").rstrip()
    return ";" in body


def _parentheses_balanced(code: str) -> bool:
    depth = 0
    for character in code:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _finding(rule: SqlRule, evidence: str) -> SqlFinding:
    return SqlFinding(rule=rule, severity=SEVERITY[rule], evidence=evidence)
