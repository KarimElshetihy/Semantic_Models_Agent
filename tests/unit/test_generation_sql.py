"""SQL candidate tests. The model is MOCKED. The checks are text-only: they never connect to a database.

Covers the read-only rules (strings and comments are not code), one statement, balanced parentheses and quotes,
the report that says what was not checked, and that candidates are recorded only in artifacts/."""

import json

import pytest

from ssas_agent.audit import RunRecorder
from ssas_agent.generation import CHECKS_FILE_NAME, SQL_FILE_NAME, check_sql, draft_sql, record_sql_candidate
from ssas_agent.generation.sql_candidate import SqlCandidate
from ssas_agent.generation.sql_checks import SqlRule
from ssas_agent.llm import ScriptedLlmClient
from ssas_agent.policy import PathPolicy


def rules_of(sql: str) -> set[SqlRule]:
    return {finding.rule for finding in check_sql(sql).findings}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT region, SUM(amount) AS total FROM sales GROUP BY region",
        "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent",
        "SELECT a FROM t;",
        "SELECT 'DELETE me' AS note FROM t",
        "SELECT a FROM t -- DROP TABLE t",
        "SELECT a /* DELETE rows */ FROM t",
        "SELECT 'it''s an UPDATE' AS note FROM t",
    ],
)
def test_clean_read_only_statements_have_no_errors(sql):
    report = check_sql(sql)

    assert not report.has_errors
    assert SqlRule.WRITE_KEYWORD not in {finding.rule for finding in report.findings}


@pytest.mark.parametrize("sql, keyword", [
    ("DELETE FROM t", "DELETE"),
    ("SELECT a FROM t; DROP TABLE t", "DROP"),
    ("SELECT a INTO b FROM t; INSERT INTO c VALUES (1)", "INSERT"),
])  # fmt: skip
def test_write_or_ddl_keywords_are_refused(sql, keyword):
    report = check_sql(sql)

    assert report.has_errors
    assert any(keyword in finding.evidence for finding in report.findings if finding.rule is SqlRule.WRITE_KEYWORD)


def test_statement_must_start_with_select_or_with():
    assert SqlRule.NOT_SELECT in rules_of("UPDATE t SET a = 1")


def test_empty_statement_is_refused():
    report = check_sql("   ")

    assert report.has_errors
    assert {finding.rule for finding in report.findings} == {SqlRule.EMPTY}


def test_more_than_one_statement_is_refused():
    assert SqlRule.MULTIPLE_STATEMENTS in rules_of("SELECT a FROM t; SELECT b FROM u")


@pytest.mark.parametrize("sql", ["SELECT (a FROM t", "SELECT a) FROM t"])
def test_unbalanced_parentheses_are_refused(sql):
    assert SqlRule.UNBALANCED_PARENTHESES in rules_of(sql)


@pytest.mark.parametrize("sql", ["SELECT 'abc FROM t", "SELECT a FROM t /* still open"])
def test_unclosed_literal_or_comment_is_refused(sql):
    assert SqlRule.UNCLOSED_LITERAL in rules_of(sql)


def test_select_star_and_missing_from_are_warnings_not_errors():
    report = check_sql("SELECT * FROM t")
    no_from = check_sql("SELECT 1")

    assert {finding.rule for finding in report.findings} == {SqlRule.SELECT_STAR}
    assert not report.has_errors
    assert {finding.rule for finding in no_from.findings} == {SqlRule.NO_FROM}
    assert not no_from.has_errors


def test_report_always_says_what_was_not_checked():
    report = check_sql("SELECT a FROM t")

    assert any("database" in note for note in report.not_checked)
    assert any("meaning" in note for note in report.not_checked)


def test_draft_sql_reads_sql_and_purpose_from_the_reply():
    client = ScriptedLlmClient([json.dumps({"sql": "  SELECT a FROM t  ", "purpose": "list a"})])

    candidate = draft_sql(client, "list column a of t")

    assert candidate == SqlCandidate(sql="SELECT a FROM t", purpose="list a")


def test_candidate_and_report_are_recorded_only_in_artifacts(tmp_path):
    recorder = RunRecorder(PathPolicy(project_root=tmp_path), tmp_path / "artifacts", "run-sql-001")
    candidate = SqlCandidate(sql="DELETE FROM t", purpose="remove rows")

    report = record_sql_candidate(recorder, candidate)

    run_dir = tmp_path / "artifacts" / "run-sql-001"
    assert (run_dir / SQL_FILE_NAME).read_text(encoding="utf-8").startswith("DELETE FROM t")
    payload = json.loads((run_dir / CHECKS_FILE_NAME).read_text(encoding="utf-8"))
    assert report.has_errors
    assert payload["has_errors"] is True
    assert payload["purpose"] == "remove rows"
    assert not (tmp_path / "workspaces").exists()


def test_recorded_event_counts_findings_without_the_statement_text(tmp_path):
    recorder = RunRecorder(PathPolicy(project_root=tmp_path), tmp_path / "artifacts", "run-sql-events")

    record_sql_candidate(recorder, SqlCandidate(sql="SELECT secret_column FROM t", purpose="p"))

    events_text = (recorder.run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert '"event": "sql_candidate_written"' in events_text
    assert "secret_column" not in events_text
