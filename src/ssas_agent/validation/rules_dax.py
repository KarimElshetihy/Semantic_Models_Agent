"""Rules about DAX references in measures and calculated columns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ssas_agent.bim.expressions import expression_text
from ssas_agent.validation.dax_scanner import DaxReference, scan_dax
from ssas_agent.validation.findings import Finding, NotChecked, make_finding
from ssas_agent.validation.model_index import CALCULATED_COLUMN_TYPE, ModelIndex, column_id, measure_id, tables_of

CALCULATED_COLUMN_TYPE = "calculated"


@dataclass(frozen=True)
class DaxSource:
    identity: str
    owner_table: str
    expression: str


def dax_findings(data: dict[str, Any], index: ModelIndex) -> tuple[list[Finding], list[NotChecked]]:
    findings: list[Finding] = []
    not_checked: list[NotChecked] = []
    for source in _dax_sources(data):
        scan = scan_dax(source.expression)
        if scan.problem is not None:
            not_checked.append(NotChecked(identity=source.identity, reason=scan.problem))
            continue
        for reference in scan.references:
            finding = _reference_finding(index, source, reference)
            if finding is not None:
                findings.append(finding)
    return findings, not_checked


def _dax_sources(data: dict[str, Any]) -> list[DaxSource]:
    sources = []
    for table in tables_of(data):
        table_name = table.get("name")
        if not table_name:
            continue
        for column in table.get("columns", []):
            if column.get("type") == CALCULATED_COLUMN_TYPE and column.get("name"):
                sources.append(_source(column_id(table_name, column["name"]), table_name, column))
        for measure in table.get("measures", []):
            if measure.get("name"):
                sources.append(_source(measure_id(table_name, measure["name"]), table_name, measure))
    return [source for source in sources if source.expression.strip()]


def _source(identity: str, owner_table: str, member: dict[str, Any]) -> DaxSource:
    return DaxSource(identity=identity, owner_table=owner_table, expression=expression_text(member.get("expression")))


def _reference_finding(index: ModelIndex, source: DaxSource, reference: DaxReference) -> Finding | None:
    if reference.table is not None:
        return _qualified_reference_finding(index, source, reference)
    if index.has_column(source.owner_table, reference.name) or index.is_measure_anywhere(reference.name):
        return None
    evidence = f"{reference.text}: no measure or column named '{reference.name}' in this table or the model"
    return make_finding("SC-021", source.identity, evidence)


def _qualified_reference_finding(index: ModelIndex, source: DaxSource, reference: DaxReference) -> Finding | None:
    table_name, name = reference.table, reference.name
    if not index.has_table(table_name):
        return make_finding("SC-020", source.identity, f"{reference.text}: table '{table_name}' does not exist")
    if index.has_column(table_name, name) or index.has_measure(table_name, name):
        return None
    return make_finding("SC-020", source.identity, f"{reference.text}: '{table_name}' has no column or measure '{name}'")
