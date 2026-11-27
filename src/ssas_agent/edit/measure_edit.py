"""Typed edits to measures in a Model.bim document.

Each function returns a new BimDocument and never changes its input.
Only the targeted measure changes. Its other properties and the storage form
of its expression (string or list of lines) are kept.
"""

from __future__ import annotations

import copy
from typing import Any

from ssas_agent.bim.document import BimDocument
from ssas_agent.bim.expressions import expression_text

LINE_SEPARATOR = "\n"


class MeasureEditError(ValueError):
    """Raised when an edit cannot be applied: unknown table or measure, duplicate name, blank or unchanged expression."""


def replace_measure_expression(
    document: BimDocument,
    table_name: str,
    measure_name: str,
    new_expression: str,
) -> BimDocument:
    """Replace the DAX expression of one existing measure."""
    document.ensure_editable()
    normalized = _normalize_expression(new_expression)
    edited = copy.deepcopy(document.data)
    measure = _find_measure(edited, table_name, measure_name)
    if expression_text(measure.get("expression")) == normalized:
        raise MeasureEditError(f"expression of {table_name}/{measure_name} is unchanged")
    measure["expression"] = _in_form_of(measure.get("expression"), normalized)
    return _with_data(document, edited)


def add_measure(
    document: BimDocument,
    table_name: str,
    measure_name: str,
    new_expression: str,
) -> BimDocument:
    """Append a new measure to an existing table."""
    document.ensure_editable()
    normalized = _normalize_expression(new_expression)
    edited = copy.deepcopy(document.data)
    table = _find_table(edited, table_name)
    if any(existing.get("name") == measure_name for existing in table.get("measures", [])):
        raise MeasureEditError(f"measure already exists: {table_name}/{measure_name}")
    table.setdefault("measures", []).append({"name": measure_name, "expression": _new_storage_form(normalized)})
    return _with_data(document, edited)


def _normalize_expression(expression: str) -> str:
    if not expression.strip():
        raise MeasureEditError("expression must not be blank")
    return expression.replace("\r\n", LINE_SEPARATOR)


def _in_form_of(original: Any, normalized: str) -> str | list[str]:
    """Keep the list form when the original was a list of lines; otherwise store one string."""
    if isinstance(original, list):
        return normalized.split(LINE_SEPARATOR)
    return normalized


def _new_storage_form(normalized: str) -> str | list[str]:
    """Visual Studio stores multi-line expressions as a list of lines; single lines as a string."""
    if LINE_SEPARATOR in normalized:
        return normalized.split(LINE_SEPARATOR)
    return normalized


def _find_table(data: dict[str, Any], table_name: str) -> dict[str, Any]:
    matches = [table for table in data["model"].get("tables", []) if table.get("name") == table_name]
    if len(matches) != 1:
        raise MeasureEditError(f"table must exist exactly once: {table_name} (found {len(matches)})")
    return matches[0]


def _find_measure(data: dict[str, Any], table_name: str, measure_name: str) -> dict[str, Any]:
    table = _find_table(data, table_name)
    matches = [measure for measure in table.get("measures", []) if measure.get("name") == measure_name]
    if len(matches) != 1:
        raise MeasureEditError(f"measure must exist exactly once: {table_name}/{measure_name} (found {len(matches)})")
    return matches[0]


def _with_data(document: BimDocument, edited_data: dict[str, Any]) -> BimDocument:
    return BimDocument(
        source_bytes=document.source_bytes,
        data=edited_data,
        reproducible_on_load=document.reproducible_on_load,
    )
