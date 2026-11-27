"""Naming rules: objects without a name, and duplicate names within the same scope."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ssas_agent.validation.findings import Finding, make_finding
from ssas_agent.validation.model_index import (
    column_id,
    measure_id,
    name_key,
    relationship_id,
    relationships_of,
    table_id,
    tables_of,
)


def name_findings(data: dict[str, Any]) -> list[Finding]:
    findings = _missing_name_findings(data)
    findings.extend(_duplicate_table_findings(data))
    findings.extend(_duplicate_relationship_findings(data))
    for table in tables_of(data):
        findings.extend(_duplicate_member_findings(table))
    return findings


def _missing_name_findings(data: dict[str, Any]) -> list[Finding]:
    findings = []
    for position, table in enumerate(tables_of(data)):
        if not table.get("name"):
            findings.append(make_finding("SC-006", f"table:(unnamed #{position})", "table has no name"))
    for position, relationship in enumerate(relationships_of(data)):
        if not relationship.get("name"):
            findings.append(make_finding("SC-006", f"relationship:(unnamed #{position})", "relationship has no name"))
    for table in tables_of(data):
        findings.extend(_unnamed_member_findings(table))
    return findings


def _unnamed_member_findings(table: dict[str, Any]) -> list[Finding]:
    table_name = table.get("name")
    if not table_name:
        return []
    findings = []
    for kind, identity_of in (("columns", column_id), ("measures", measure_id)):
        for position, member in enumerate(table.get(kind, [])):
            if not member.get("name"):
                identity = identity_of(table_name, f"(unnamed #{position})")
                findings.append(make_finding("SC-006", identity, f"{kind[:-1]} has no name in '{table_name}'"))
    return findings


def _duplicate_table_findings(data: dict[str, Any]) -> list[Finding]:
    names = [table.get("name") for table in tables_of(data) if table.get("name")]
    return [
        make_finding("SC-001", table_id(name), f"{count} tables named '{name}'")
        for name, count in _duplicates(names)
    ]


def _duplicate_relationship_findings(data: dict[str, Any]) -> list[Finding]:
    names = [relationship.get("name") for relationship in relationships_of(data) if relationship.get("name")]
    return [
        make_finding("SC-004", relationship_id(name), f"{count} relationships named '{name}'")
        for name, count in _duplicates(names)
    ]


def _duplicate_member_findings(table: dict[str, Any]) -> list[Finding]:
    table_name = table.get("name")
    if not table_name:
        return []
    columns = [column.get("name") for column in table.get("columns", []) if column.get("name")]
    measures = [measure.get("name") for measure in table.get("measures", []) if measure.get("name")]
    findings = [
        make_finding("SC-002", column_id(table_name, name), f"{count} columns named '{name}' in '{table_name}'")
        for name, count in _duplicates(columns)
    ]
    findings.extend(
        make_finding("SC-003", measure_id(table_name, name), f"{count} measures named '{name}' in '{table_name}'")
        for name, count in _duplicates(measures)
    )
    return findings


def _duplicates(names: list[str]) -> list[tuple[str, int]]:
    """Names that occur more than once (ignoring case, as SSAS does), with their counts, in name order.
    Each name is reported as first written."""
    first_spelling: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for name in names:
        key = name_key(name)
        first_spelling.setdefault(key, name)
        counts[key] += 1
    return sorted(
        (first_spelling[key], count) for key, count in counts.items() if count > 1
    )
