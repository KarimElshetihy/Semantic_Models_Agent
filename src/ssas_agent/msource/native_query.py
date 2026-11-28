"""Finds the one Power Query shape the example models use: let Source = Value.NativeQuery(...) in Source.

Anything else returns None, and the caller reports the partition as not understood. Power Query strings
double their quotes (""), so the SQL text and the data source name are unescaped here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NATIVE_QUERY_CALL = "Value.NativeQuery("
NATIVE_QUERY_START = re.compile(r'Value\.NativeQuery\(\s*#"((?:[^"]|"")*)"\s*,\s*"')
LET_BEFORE_SOURCE = re.compile(r"\Alet\s+Source\s*=\s*\Z")
ONLY_SOURCE_AFTER = re.compile(r"\A\s*(?:,[^\n]*)?\)\s*in\s*Source\s*\Z")
LATER_STEPS_NOTE = "later Power Query steps are not read"


@dataclass(frozen=True)
class NativeQuery:
    data_source: str
    sql: str
    sql_start_line: int
    notes: tuple[str, ...]


def find_native_query(m_text: str) -> NativeQuery | None:
    """Return the native query, or None when the text does not have the expected shape."""
    if m_text.count(NATIVE_QUERY_CALL) != 1:
        return None
    start = NATIVE_QUERY_START.search(m_text)
    if start is None or not LET_BEFORE_SOURCE.search(m_text[: start.start()]):
        return None
    literal_start = start.end() - 1
    literal_end = _m_string_end(m_text, literal_start)
    if literal_end is None:
        return None
    return NativeQuery(
        data_source=_unescape(start.group(1)),
        sql=_unescape(m_text[literal_start + 1 : literal_end]),
        sql_start_line=m_text.count("\n", 0, literal_start) + 1,
        notes=_notes_after(m_text[literal_end + 1 :]),
    )


def _m_string_end(text: str, start: int) -> int | None:
    """Index of the closing quote of the Power Query string that opens at `start`, or None if it never closes."""
    position = start + 1
    while position < len(text):
        if text[position] == '"':
            if text.startswith('""', position):
                position += 2
                continue
            return position
        position += 1
    return None


def _notes_after(text_after_literal: str) -> tuple[str, ...]:
    return () if ONLY_SOURCE_AFTER.match(text_after_literal) else (LATER_STEPS_NOTE,)


def _unescape(text: str) -> str:
    return text.replace('""', '"')
