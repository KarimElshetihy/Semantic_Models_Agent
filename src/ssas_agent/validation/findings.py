"""Result types for static checks, and the rule catalog that gives each finding its severity and fix."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ERROR = "error"
WARNING = "warning"

# rule ID -> (severity, suggested fix). Titles are documented in docs/PHASE1_DESIGN.md.
RULE_CATALOG: dict[str, tuple[str, str]] = {
    "SC-001": (ERROR, "Rename one of the duplicate tables, and update every reference to it."),
    "SC-002": (ERROR, "Rename one of the duplicate columns in this table."),
    "SC-003": (ERROR, "Rename one of the duplicate measures in this table, and update its references."),
    "SC-004": (ERROR, "Give each relationship a unique name."),
    "SC-006": (ERROR, "Give the object a name."),
    "SC-010": (ERROR, "Point the relationship at an existing table and column, or add the missing column."),
    "SC-020": (ERROR, "Correct the reference, or add the missing table, column or measure."),
    "SC-021": (ERROR, "Qualify the reference with its table, or correct the name."),
    "SC-030": (ERROR, "Write the column expression, or remove the calculated column."),
    "SC-040": (WARNING, "Write the measure expression, or remove the measure."),
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    identity: str
    evidence: str
    suggested_fix: str


@dataclass(frozen=True)
class NotChecked:
    """Something the static rules did not examine. It is reported, never silently passed."""

    identity: str
    reason: str


def make_finding(rule_id: str, identity: str, evidence: str) -> Finding:
    severity, suggested_fix = RULE_CATALOG[rule_id]
    return Finding(
        rule_id=rule_id,
        severity=severity,
        identity=identity,
        evidence=evidence,
        suggested_fix=suggested_fix,
    )


@dataclass(frozen=True)
class CheckReport:
    findings: tuple[Finding, ...]
    not_checked: tuple[NotChecked, ...]

    @property
    def has_errors(self) -> bool:
        return any(finding.severity == ERROR for finding in self.findings)

    def count_by_severity(self) -> dict[str, int]:
        return {
            severity: sum(1 for finding in self.findings if finding.severity == severity)
            for severity in (ERROR, WARNING)
        }

    def to_payload(self) -> dict[str, Any]:
        """Plain data for the audit trail: findings and not-checked items, in a stable order."""
        return {
            "counts": self.count_by_severity(),
            "findings": [finding.__dict__ for finding in self.findings],
            "not_checked": [item.__dict__ for item in self.not_checked],
        }
