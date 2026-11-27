"""Lookups over the raw Model.bim dictionary, shared by all static rules.

Object identities use the same scheme as the inventory (`table:T`, `column:T/C`, ...).
Tables that share a name are merged here; the duplicate-name rule reports them separately.
"""

from __future__ import annotations

from typing import Any

CALCULATED_COLUMN_TYPE = "calculated"


def tables_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("model", {}).get("tables", []))


def relationships_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("model", {}).get("relationships", []))


def table_id(table_name: str) -> str:
    return f"table:{table_name}"


def column_id(table_name: str, column_name: str) -> str:
    return f"column:{table_name}/{column_name}"


def measure_id(table_name: str, measure_name: str) -> str:
    return f"measure:{table_name}/{measure_name}"


def relationship_id(relationship_name: str) -> str:
    return f"relationship:{relationship_name}"


class ModelIndex:
    """Lookups are case-insensitive, as they are in DAX and in SSAS object names."""

    def __init__(self, columns_by_table: dict[str, set[str]], measures_by_table: dict[str, set[str]]) -> None:
        self._columns = columns_by_table
        self._measures = measures_by_table

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> ModelIndex:
        columns: dict[str, set[str]] = {}
        measures: dict[str, set[str]] = {}
        for table in tables_of(data):
            key = name_key(table.get("name"))
            if key is None:
                continue
            columns.setdefault(key, set()).update(_keys(table.get("columns", [])))
            measures.setdefault(key, set()).update(_keys(table.get("measures", [])))
        return cls(columns, measures)

    def has_table(self, table_name: str | None) -> bool:
        return name_key(table_name) in self._columns

    def has_column(self, table_name: str | None, column_name: str | None) -> bool:
        return name_key(column_name) in self._columns.get(name_key(table_name), set())

    def has_measure(self, table_name: str | None, measure_name: str | None) -> bool:
        return name_key(measure_name) in self._measures.get(name_key(table_name), set())

    def is_measure_anywhere(self, measure_name: str | None) -> bool:
        key = name_key(measure_name)
        return any(key in names for names in self._measures.values())


def name_key(name: str | None) -> str | None:
    """Comparison key for an object name. None for a missing name."""
    return name.casefold() if name else None


def _keys(objects: list[dict[str, Any]]) -> list[str]:
    return [name_key(item["name"]) for item in objects if item.get("name")]
