"""Describes the model's tables, columns and measures for the model. The model may use only these names."""

from __future__ import annotations

from typing import Any

from ssas_agent.validation.model_index import tables_of


def model_context(data: dict[str, Any]) -> str:
    lines = [_table_line(table) for table in tables_of(data)]
    return "\n".join(line for line in lines if line)


def _table_line(table: dict[str, Any]) -> str:
    name = table.get("name")
    if not name:
        return ""
    columns = _names(table.get("columns", []))
    measures = _names(table.get("measures", []))
    return f"Table '{name}': columns [{', '.join(columns)}]; measures [{', '.join(measures)}]"


def _names(members: list[dict[str, Any]]) -> list[str]:
    return [member["name"] for member in members if isinstance(member.get("name"), str)]
