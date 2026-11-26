"""Rules that flag suspicious model objects. Phase 0 reports findings and never fixes them."""

from __future__ import annotations

from typing import Any

from ssas_agent.bim.expressions import expression_text

LOCAL_NOW_TOKEN = "DateTime.LocalNow"

CALCULATED_COLUMN_TYPE = "calculated"
M_SOURCE_TYPE = "m"
CALCULATED_COLUMN_WITHOUT_EXPRESSION = "calculated column has no expression"
M_PARTITION_USES_LOCAL_NOW = "M partition uses DateTime.LocalNow, so its output changes over time"


def column_findings(column: dict[str, Any]) -> list[str]:
    findings = []
    if column.get("type") == CALCULATED_COLUMN_TYPE and not column.get("expression"):
        findings.append(CALCULATED_COLUMN_WITHOUT_EXPRESSION)
    return findings


def partition_findings(partition: dict[str, Any]) -> list[str]:
    source = partition.get("source", {})
    findings = []
    if source.get("type") == M_SOURCE_TYPE and LOCAL_NOW_TOKEN in expression_text(source.get("expression")):
        findings.append(M_PARTITION_USES_LOCAL_NOW)
    return findings
