"""Phase 1 exit gate (step 10): the demonstration runs end to end, refuses what it must, and writes a generated report.

Each test builds its own project root in a temporary folder. The sample spec and the RETA fixture are copied in,
so the policy applies as it does in the real project. The approver is scripted; no terminal is needed.
"""

from pathlib import Path

import pytest

from ssas_agent.audit import InvalidRunIdError
from ssas_agent.bim.document import sha256_hex
from ssas_agent.cli import main
from ssas_agent.demo import DemoRefusedError, run_exit_gate
from ssas_agent.demo.refusals import snapshot_folders
from ssas_agent.demo.report import REPORT_FILE_NAME, report_location
from ssas_agent.policy import PathPolicy

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_SOURCE = REPO_ROOT / "specs" / "SAMPLE_SALES.json"
FIXTURE_SOURCE = REPO_ROOT / "tests" / "fixtures" / "RETA_MODEL" / "Model.bim"
DESTINATION = Path("output") / "Model.bim"
PREFIX = "gate-001"
POWER_QUERY_MARKERS = ("Value.NativeQuery", "SELECT ", "Oracle.Database")


@pytest.fixture
def project(tmp_path):
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "SAMPLE_SALES.json").write_bytes(SPEC_SOURCE.read_bytes())
    fixture_folder = tmp_path / "tests" / "fixtures" / "RETA_MODEL"
    fixture_folder.mkdir(parents=True)
    (fixture_folder / "Model.bim").write_bytes(FIXTURE_SOURCE.read_bytes())
    return PathPolicy(project_root=tmp_path, apply_folder=Path("output"))


def run_demo(policy, answer="approve", prefix=PREFIX):
    printed = []
    result = run_exit_gate(
        policy,
        approver="bob",
        run_prefix=prefix,
        read_line=lambda prompt: answer,
        write_line=printed.append,
    )
    return result, printed


def report_text(policy, prefix=PREFIX):
    return (policy.project_root / report_location(prefix)).read_text(encoding="utf-8")


# ---- Full gate ----------------------------------------------------------------------------------


def test_full_gate_passes_with_the_model_checked_edit_applied_and_refusals_refused(project):
    result, _ = run_demo(project)

    assert result.passed
    assert result.new_model is not None and result.new_model.errors == 0
    assert result.edit is not None and result.edit.verified
    assert all(refusal.refused for refusal in result.refusals)
    assert result.refusals_wrote_nothing


def test_destination_holds_exactly_the_approved_candidate(project):
    result, _ = run_demo(project)

    destination_bytes = (project.project_root / DESTINATION).read_bytes()
    assert sha256_hex(destination_bytes) == result.edit.candidate_sha256


def test_sample_model_stays_in_workspaces_and_is_not_delivered_to_the_destination(project):
    run_demo(project)

    assert (project.project_root / "workspaces" / f"{PREFIX}-model" / "SAMPLE_SALES" / "Model.bim").is_file()
    assert not (project.project_root / "output" / "SAMPLE_SALES").exists()
    assert sorted(path.name for path in (project.project_root / "output").iterdir()) == ["Model.bim"]


def test_report_is_written_from_the_results_and_lists_what_was_not_run(project):
    run_demo(project)

    text = report_text(project)
    assert "Result: **PASSED**" in text
    assert "state: **VERIFIED**" in text
    assert "Visual Studio 2019" in text
    assert "AC-09" in text
    assert "Nothing was written by the refusals" in text
    assert "**yes**" in text


def test_report_holds_no_power_query_or_sql_text(project):
    run_demo(project)

    text = report_text(project)
    for marker in POWER_QUERY_MARKERS:
        assert marker not in text, marker


def test_report_file_name_and_location_follow_the_run_prefix(project):
    run_demo(project)

    assert report_location(PREFIX) == Path("artifacts") / PREFIX / REPORT_FILE_NAME
    assert (project.project_root / report_location(PREFIX)).is_file()


# ---- Stopping -------------------------------------------------------------------------------------


def test_declined_approval_stops_the_edit_and_writes_no_destination(project):
    result, printed = run_demo(project, answer="no")

    assert not result.passed
    assert result.edit is None
    assert "not approved" in result.stopped_reason
    assert not (project.project_root / DESTINATION).exists()
    assert "Not approved. Nothing was changed." in printed


def test_declined_approval_still_writes_the_report_as_not_passed(project):
    run_demo(project, answer="no")

    text = report_text(project)
    assert "Result: **NOT PASSED**" in text
    assert "Stopped early: the edit was not approved" in text
    assert "Not applied (see the stop reason above)." in text


def test_demo_refuses_to_run_when_the_destination_already_holds_a_model(project):
    existing = project.project_root / DESTINATION
    existing.parent.mkdir()
    existing.write_bytes(b"someone else's model")

    with pytest.raises(DemoRefusedError, match="never overwrites"):
        run_demo(project)

    assert existing.read_bytes() == b"someone else's model"
    assert not (project.project_root / "workspaces").exists()


def test_demo_refuses_when_no_destination_folder_is_named(tmp_path):
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "SAMPLE_SALES.json").write_bytes(SPEC_SOURCE.read_bytes())
    policy = PathPolicy(project_root=tmp_path)

    with pytest.raises(DemoRefusedError, match="named destination"):
        run_demo(policy)


def test_invalid_run_prefix_is_refused_before_anything_is_written(project):
    with pytest.raises(InvalidRunIdError):
        run_demo(project, prefix="../escape")

    assert not (project.project_root / "workspaces").exists()


# ---- Refusal snapshot -----------------------------------------------------------------------------


def test_snapshot_sees_an_added_file_and_a_changed_file(project):
    before = snapshot_folders(project.project_root)
    (project.project_root / "output").mkdir()
    (project.project_root / "output" / "extra.txt").write_text("new", encoding="utf-8")

    after_add = snapshot_folders(project.project_root)
    (project.project_root / "output" / "extra.txt").write_text("changed size", encoding="utf-8")
    after_change = snapshot_folders(project.project_root)

    assert before != after_add
    assert after_add != after_change


# ---- Command line ---------------------------------------------------------------------------------


def run_cli(policy, *extra, answer="approve"):
    printed = []
    exit_code = main(
        ["--project-root", str(policy.project_root), "demo", "--actor", "bob", *extra],
        read_line=lambda prompt: answer,
        write_line=printed.append,
    )
    return exit_code, printed


def test_demo_command_exits_zero_and_prints_passed(project):
    exit_code, printed = run_cli(project, "--run-prefix", "cli-001")

    assert exit_code == 0
    assert "Exit gate: PASSED" in printed


def test_demo_command_exits_one_when_approval_is_declined(project):
    exit_code, printed = run_cli(project, "--run-prefix", "cli-002", answer="later")

    assert exit_code == 1
    assert "Exit gate: NOT PASSED" in printed


def test_demo_command_reports_a_refused_start_without_a_traceback(project):
    (project.project_root / DESTINATION).parent.mkdir()
    (project.project_root / DESTINATION).write_bytes(b"existing")

    exit_code, printed = run_cli(project, "--run-prefix", "cli-003")

    assert exit_code == 1
    assert printed[-1].startswith("Refused:") and "never overwrites" in printed[-1]
