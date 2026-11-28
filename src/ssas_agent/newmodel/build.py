"""Turns a ModelSpec into a Model.bim (TMSL) dictionary shaped like Visual Studio 2019 output.

The data source has no credential. Each relationship gets a name derived from its endpoints, so the
same spec always produces the same file. Multi-line Power Query text and expressions are stored as a
list of lines, as Visual Studio stores them.
"""

from __future__ import annotations

import uuid
from typing import Any

from ssas_agent.newmodel.spec import (
    ColumnSpec,
    DataSourceSpec,
    MeasureSpec,
    ModelSpec,
    RelationshipSpec,
    TableSpec,
)
from ssas_agent.validation.model_index import name_key

MODEL_NAME = "SemanticModel"
CLIENT_COMPATIBILITY_ANNOTATION = {"name": "ClientCompatibilityLevel", "value": "600"}
LINE_BREAK = "\n"
RELATIONSHIP_NAME_PREFIX = "ssas-agent"


def build_model_document(spec: ModelSpec) -> dict[str, Any]:
    return {
        "name": MODEL_NAME,
        "compatibilityLevel": spec.compatibility_level,
        "model": {
            "culture": spec.culture,
            "dataSources": [_data_source_payload(spec.data_source)],
            "tables": [_table_payload(table, _measures_of(table, spec)) for table in spec.tables],
            "relationships": [_relationship_payload(relationship) for relationship in spec.relationships],
            "annotations": [dict(CLIENT_COMPATIBILITY_ANNOTATION)],
        },
        "id": MODEL_NAME,
    }


def relationship_name(relationship: RelationshipSpec) -> str:
    """A stable GUID-shaped name, so rebuilding the same spec gives the same file."""
    endpoints = (
        f"{relationship.from_table}[{relationship.from_column}]->"
        f"{relationship.to_table}[{relationship.to_column}]"
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{RELATIONSHIP_NAME_PREFIX}:{endpoints}"))


def storage_form(text: str) -> str | list[str]:
    """One line is stored as a string; several lines as a list of lines (Visual Studio style)."""
    lines = text.split(LINE_BREAK)
    return lines if len(lines) > 1 else text


def _measures_of(table: TableSpec, spec: ModelSpec) -> list[MeasureSpec]:
    return [measure for measure in spec.measures if name_key(measure.table) == name_key(table.name)]


def _data_source_payload(source: DataSourceSpec) -> dict[str, Any]:
    return {
        "type": "structured",
        "name": source.name,
        "connectionDetails": {
            "protocol": "oracle",
            "address": {"server": source.server},
            "authentication": None,
            "query": None,
        },
        "options": {"hierarchicalNavigation": True},
    }


def _table_payload(table: TableSpec, measures: list[MeasureSpec]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": table.name,
        "columns": [_column_payload(column) for column in table.columns],
    }
    if table.power_query is not None:
        payload["partitions"] = [_partition_payload(table)]
    if measures:
        payload["measures"] = [_measure_payload(measure) for measure in measures]
    return payload


def _column_payload(column: ColumnSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": column.name,
        "dataType": column.data_type.value,
        "sourceColumn": column.source_column,
    }
    if column.is_key:
        payload["isKey"] = True
    return payload


def _partition_payload(table: TableSpec) -> dict[str, Any]:
    return {
        "name": table.name,
        "source": {"type": "m", "expression": storage_form(table.power_query or "")},
    }


def _measure_payload(measure: MeasureSpec) -> dict[str, Any]:
    return {"name": measure.name, "expression": storage_form(measure.expression)}


def _relationship_payload(relationship: RelationshipSpec) -> dict[str, Any]:
    return {
        "name": relationship_name(relationship),
        "fromTable": relationship.from_table,
        "fromColumn": relationship.from_column,
        "toTable": relationship.to_table,
        "toColumn": relationship.to_column,
    }
