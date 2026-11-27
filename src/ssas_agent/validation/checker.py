"""Runs every static rule on a Model.bim dictionary and returns one sorted report.

A clean report means only that these rules found nothing. It does not mean the
model compiles or processes (spec section 4.1).
"""

from __future__ import annotations

from typing import Any

from ssas_agent.validation.findings import CheckReport, Finding, NotChecked
from ssas_agent.validation.model_index import ModelIndex, tables_of
from ssas_agent.validation.rules_dax import dax_findings
from ssas_agent.validation.rules_model import empty_expression_findings, relationship_findings
from ssas_agent.validation.rules_structure import name_findings


def run_static_checks(data: dict[str, Any]) -> CheckReport:
    index = ModelIndex.from_data(data)
    findings = name_findings(data) + relationship_findings(data, index) + empty_expression_findings(data)
    dax_found, dax_skipped = dax_findings(data, index)
    findings.extend(dax_found)
    not_checked = dax_skipped + _scope_notes(data)
    return CheckReport(
        findings=tuple(sorted(findings, key=_finding_order)),
        not_checked=tuple(sorted(not_checked, key=_not_checked_order)),
    )


def _scope_notes(data: dict[str, Any]) -> list[NotChecked]:
    notes = []
    if any(table.get("partitions") for table in tables_of(data)):
        notes.append(NotChecked(identity="partitions", reason="Power Query (M) partitions are not checked in Phase 1"))
    if data.get("model", {}).get("roles"):
        notes.append(NotChecked(identity="roles", reason="row-level security filter expressions are not checked in Phase 1"))
    return notes


def _finding_order(finding: Finding) -> tuple[str, str, str]:
    return (finding.rule_id, finding.identity, finding.evidence)


def _not_checked_order(item: NotChecked) -> tuple[str, str]:
    return (item.identity, item.reason)
