"""Drafts one read-only Oracle SELECT from a request, then records it with its check report.

The statement and report go only into artifacts/{run_id}/. No model or workspace file is changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ssas_agent.audit import RunRecorder
from ssas_agent.generation.sql_checks import SqlReport, check_sql
from ssas_agent.llm import ChatMessage, ChatRole, LlmClient, ask_structured

SQL_FILE_NAME = "candidate.sql"
CHECKS_FILE_NAME = "sql_checks.json"
SQL_INSTRUCTIONS = (
    "You write one read-only Oracle SELECT statement for the request between the REQUEST markers. "
    "Reply with one JSON object only, with exactly these keys: sql, purpose. "
    "Do not write INSERT, UPDATE, DELETE, DDL or more than one statement. "
    "Use only table and column names stated in the request; never invent them."
)
SQL_SCHEMA: dict[str, type] = {"sql": str, "purpose": str}


class SqlEvent(StrEnum):
    CANDIDATE_WRITTEN = "sql_candidate_written"


@dataclass(frozen=True)
class SqlCandidate:
    sql: str
    purpose: str


def draft_sql(client: LlmClient, request_text: str) -> SqlCandidate:
    """Ask the model for one statement. Raises StructuredOutputError or LlmError on a bad reply."""
    messages = [
        ChatMessage(ChatRole.SYSTEM, SQL_INSTRUCTIONS),
        ChatMessage(ChatRole.USER, f"<<<REQUEST\n{request_text}\nREQUEST>>>"),
    ]
    fields = ask_structured(client, messages, SQL_SCHEMA)
    return SqlCandidate(sql=fields["sql"].strip(), purpose=fields["purpose"].strip())


def record_sql_candidate(recorder: RunRecorder, candidate: SqlCandidate) -> SqlReport:
    report = check_sql(candidate.sql)
    recorder.write_text(SQL_FILE_NAME, candidate.sql + "\n")
    recorder.write_json(CHECKS_FILE_NAME, _report_payload(candidate, report))
    recorder.append_event(
        SqlEvent.CANDIDATE_WRITTEN,
        {"has_errors": report.has_errors, "finding_count": len(report.findings)},
    )
    return report


def _report_payload(candidate: SqlCandidate, report: SqlReport) -> dict[str, object]:
    return {
        "purpose": candidate.purpose,
        "has_errors": report.has_errors,
        "findings": [
            {"rule": finding.rule.value, "severity": finding.severity, "evidence": finding.evidence}
            for finding in report.findings
        ],
        "not_checked": list(report.not_checked),
    }
