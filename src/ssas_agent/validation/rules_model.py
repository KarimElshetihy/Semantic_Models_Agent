"""Rules about relationships and about expressions that are present but empty."""

from __future__ import annotations

from typing import Any

from ssas_agent.bim.expressions import expression_text
from ssas_agent.validation.findings import Finding, make_finding
from ssas_agent.validation.model_index import (
    CALCULATED_COLUMN_TYPE,
    ModelIndex,
    column_id,
    measure_id,
    relationship_id,
    relationships_of,
    tables_of,
)

CALCULATED_COLUMN_TYPE = "calculated"


def relationship_findings(data: dict[str, Any], index: ModelIndex) -> list[Finding]:
    findings = []
    for position, relationship in enumerate(relationships_of(data)):
        identity = relationship_id(relationship.get("name") or f"(unnamed #{position})")
        for side in ("from", "to"):
            table_name = relationship.get(f"{side}Table")
            column_name = relationship.get(f"{side}Column")
            if not index.has_column(table_name, column_name):
                evidence = f"{side} side {table_name}[{column_name}] does not exist"
                findings.append(make_finding("SC-010", identity, evidence))
    return findings


def empty_expression_findings(data: dict[str, Any]) -> list[Finding]:
    findings = []
    for table in tables_of(data):
        table_name = table.get("name")
        if not table_name:
            continue
        findings.extend(_empty_calculated_column_findings(table_name, table))
        findings.extend(_blank_measure_findings(table_name, table))
    return findings


def _empty_calculated_column_findings(table_name: str, table: dict[str, Any]) -> list[Finding]:
    return [
        make_finding("SC-030", column_id(table_name, column["name"]), "calculated column has no expression")
        for column in table.get("columns", [])
        if column.get("type") == CALCULATED_COLUMN_TYPE
        and column.get("name")
        and not expression_text(column.get("expression")).strip()
    ]


def _blank_measure_findings(table_name: str, table: dict[str, Any]) -> list[Finding]:
    return [
        make_finding("SC-040", measure_id(table_name, measure["name"]), "measure expression is blank")
        for measure in table.get("measures", [])
        if measure.get("name") and not expression_text(measure.get("expression")).strip()
    ]
