"""Helpers for the two storage forms of expressions in Model.bim: a string, or a list of lines."""

from __future__ import annotations

import re
from typing import Any

NATIVE_QUERY_ONLY_PATTERN = re.compile(
    r'let Source = Value\.NativeQuery\(#"[^"]+", ".*?"(, null, \[[^\]]*\])?\) in Source',
    re.DOTALL,
)
NATIVE_QUERY_TOKEN = "Value.NativeQuery"


def expression_text(expression: Any) -> str:
    """Return the expression as one string. A list of lines is joined with newlines."""
    if expression is None:
        return ""
    if isinstance(expression, list):
        return "\n".join(expression)
    return str(expression)


def expression_form(expression: Any) -> str:
    """Report how the expression is stored: 'none', 'list' or 'string'."""
    if expression is None:
        return "none"
    return "list" if isinstance(expression, list) else "string"


def is_native_query_only(text: str) -> bool:
    """True when the M expression is a single Value.NativeQuery call and nothing else."""
    compact = re.sub(r"\s+", " ", text).strip()
    return NATIVE_QUERY_ONLY_PATTERN.fullmatch(compact) is not None


def m_partition_shape(text: str) -> str:
    """Classify an M partition: 'native_query_only', 'native_query_plus_steps' or 'no_native_query'."""
    if is_native_query_only(text):
        return "native_query_only"
    if NATIVE_QUERY_TOKEN in text:
        return "native_query_plus_steps"
    return "no_native_query"
