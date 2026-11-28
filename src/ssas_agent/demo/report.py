"""The exit-gate report, written by code from the recorded results. No one types the outcomes by hand.

The report holds paths, hashes, counts, check results and notes. It never holds Power Query or SQL text.
"""

from __future__ import annotations

from pathlib import Path

from ssas_agent.audit.recorder import RunRecorder
from ssas_agent.demo.records import EditOutcome, ExitGateResult, NewModelOutcome, RefusalRecord
from ssas_agent.policy import PathPolicy

ARTIFACTS_ROOT = Path("artifacts")
REPORT_FILE_NAME = "exit_gate_report.md"
GATE_TEXT = "Demonstrate a new sample model and a safe edit to an existing model (requirements section 12)."
NOT_RUN_ITEMS = (
    "Visual Studio 2019 has not opened the generated files. This check is yours.",
    "No Oracle connection was made, so no SQL or DAX results were compared (Phase 2, AC-04).",
    "No SSAS instance was used. Nothing was processed or deployed (AC-09).",
    "The live LLM test was not run. The demonstration makes no LLM call.",
    "Dependency and impact analysis was not run; the proposal says so (decision 3).",
    "The new sample model stays in workspaces/ and was not delivered to the destination.",
)
KNOWN_LIMITATIONS = (
    "The destination must not already hold a model; the demo refuses rather than overwrite.",
    "The edit is staged from a read-only fixture model, so it creates a new destination file.",
    "Staging is done by code. Only the approval and apply steps are terminal commands.",
    "The approver's name is typed, not verified. The staging actor is a fixed name.",
    "The static checks do not read Power Query text; it is copied as written.",
)


def report_location(run_prefix: str) -> Path:
    """Where the report of a run is written, relative to the project root."""
    return ARTIFACTS_ROOT / run_prefix / REPORT_FILE_NAME


def write_exit_gate_report(policy: PathPolicy, result: ExitGateResult) -> Path:
    recorder = RunRecorder(policy, ARTIFACTS_ROOT, result.run_prefix)
    return recorder.write_text(REPORT_FILE_NAME, render_report(result))


def render_report(result: ExitGateResult) -> str:
    sections = [
        _header(result),
        _new_model_section(result.new_model),
        _edit_section(result.edit),
        _refusal_section(result.refusals, result.refusals_wrote_nothing),
        _list_section("Not checked and not run", NOT_RUN_ITEMS + _not_checked_items(result.new_model)),
        _list_section("Known limitations", KNOWN_LIMITATIONS),
    ]
    return "\n\n".join(sections) + "\n"


def _header(result: ExitGateResult) -> str:
    status = "PASSED" if result.passed else "NOT PASSED"
    stopped = result.stopped_reason or "no"
    return "\n".join(
        [
            "# Phase 1 exit gate demonstration",
            "",
            f"- Run prefix: `{result.run_prefix}`",
            f"- Result: **{status}**",
            f"- Stopped early: {stopped}",
            f"- Gate: {GATE_TEXT}",
        ]
    )


def _new_model_section(outcome: NewModelOutcome | None) -> str:
    if outcome is None:
        return "## 1. New sample model\n\nNot built (see the stop reason above)."
    return "\n".join(
        [
            "## 1. New sample model",
            "",
            f"- Spec: `specs/SAMPLE_SALES.json`, project `{outcome.project_name}`",
            f"- Run: `{outcome.run_id}`",
            f"- Model: `{outcome.model_path}` (SHA-256 `{outcome.model_sha256}`)",
            f"- Project file: `{outcome.project_path}`",
            f"- Source mapping: `{outcome.mapping_path}`",
            f"- Static checks: {outcome.errors} errors, {outcome.warnings} warnings",
            "- The model was checked in workspaces/ only. It was not delivered to the destination.",
        ]
    )


def _edit_section(outcome: EditOutcome | None) -> str:
    if outcome is None:
        return "## 2. Safe edit to an existing model\n\nNot applied (see the stop reason above)."
    return "\n".join(
        [
            "## 2. Safe edit to an existing model",
            "",
            f"- Source (read only): `{outcome.source_path}`",
            f"- Destination: `{outcome.target_path}`",
            f"- Run: `{outcome.run_id}`",
            f"- Staged by: `{outcome.staged_by}`; approved by: `{outcome.approved_by}` (typed approval)",
            f"- Candidate SHA-256: `{outcome.candidate_sha256}`",
            f"- Change: {_counts_text(outcome.change_summary)}",
            f"- Categories: {_counts_text(outcome.category_summary)}",
            f"- Apply outcome: {outcome.outcome}; state: **{outcome.state}**",
            f"- Verified on disk: hash match {outcome.verification['hash_matches']}, "
            f"reads back identically {outcome.verification['reads_back_identically']}",
        ]
    )


def _refusal_section(refusals: tuple[RefusalRecord, ...], wrote_nothing: bool) -> str:
    rows = ["| Case | Refused | Reason |", "|---|---|---|"]
    rows += [f"| {_cell(record.case)} | {'yes' if record.refused else 'NO'} | {_cell(record.reason)} |" for record in refusals]
    closing = (
        "Nothing was written by the refusals (checked by path, size and modification time "
        f"in the protected and destination folders): **{'yes' if wrote_nothing else 'NO'}**."
    )
    return "\n".join(["## 3. Refusals", "", *rows, "", closing])


def _not_checked_items(outcome: NewModelOutcome | None) -> tuple[str, ...]:
    return tuple(outcome.not_checked) if outcome is not None else ()


def _list_section(title: str, items: tuple[str, ...]) -> str:
    return "\n".join([f"## {title}", "", *[f"- {item}" for item in items]])


def _counts_text(counts: dict) -> str:
    return ", ".join(f"{name} {value}" for name, value in counts.items()) or "none"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
