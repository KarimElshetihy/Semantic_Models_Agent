"""Audit tests: run IDs, redaction, artifact writes, event log and policy integration."""

import json
from datetime import datetime, timezone

import pytest

from ssas_agent.audit import (
    REDACTED,
    InvalidRunIdError,
    RunRecorder,
    new_run_id,
    redact_text,
    validate_run_id,
)
from ssas_agent.policy import PathPolicy, PolicyDeniedError


@pytest.fixture
def policy(tmp_path):
    return PathPolicy(project_root=tmp_path)


@pytest.fixture
def artifacts_root(tmp_path):
    return tmp_path / "artifacts"


def make_recorder(policy, artifacts_root, run_id="run-test-001"):
    return RunRecorder(policy=policy, artifacts_root=artifacts_root, run_id=run_id)


def test_new_run_ids_are_valid_and_unique():
    run_ids = {new_run_id() for _ in range(50)}

    assert len(run_ids) == 50
    assert all(validate_run_id(run_id) for run_id in run_ids)


def test_run_id_embeds_the_given_timestamp():
    moment = datetime(2026, 11, 26, 10, 55, 0, tzinfo=timezone.utc)

    assert new_run_id(moment).startswith("20261126T105500Z-")


@pytest.mark.parametrize(
    "bad_run_id",
    ["", "../escape", "a/b", "a\\b", ".hidden", "x" * 65, "run 1", None, 42],
)
def test_unsafe_run_ids_are_rejected(bad_run_id):
    with pytest.raises(InvalidRunIdError):
        validate_run_id(bad_run_id)


def test_recorder_rejects_unsafe_run_id_before_creating_anything(policy, artifacts_root, tmp_path):
    with pytest.raises(InvalidRunIdError):
        make_recorder(policy, artifacts_root, run_id="../escape")

    assert not any(tmp_path.iterdir())


def test_recorder_refuses_artifacts_root_inside_protected_folder(policy, tmp_path):
    protected_root = tmp_path / "example_models" / "artifacts"

    with pytest.raises(PolicyDeniedError, match="protected"):
        make_recorder(policy, protected_root)


def test_recorder_writes_json_text_and_events(policy, artifacts_root):
    recorder = make_recorder(policy, artifacts_root)

    recorder.write_json("run.json", {"run_id": "run-test-001", "input_sha256": "abc"})
    recorder.write_text("diff.txt", "--- before\n+++ after\n")
    recorder.append_event("policy_decision", {"operation": "write", "allowed": True})
    recorder.append_event("run_started", {"step": 1})

    assert json.loads((recorder.run_dir / "run.json").read_text(encoding="utf-8"))["input_sha256"] == "abc"
    assert (recorder.run_dir / "diff.txt").read_text(encoding="utf-8") == "--- before\n+++ after\n"
    events = (recorder.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event"] for line in events] == ["policy_decision", "run_started"]
    assert all("timestamp" in json.loads(line) for line in events)


def test_credentials_are_redacted_in_text_artifacts(policy, artifacts_root):
    recorder = make_recorder(policy, artifacts_root)

    path = recorder.write_text("diff.txt", '"Username": "epaysetts"\n"Password": "hunter2"\n')

    content = path.read_text(encoding="utf-8")
    assert "epaysetts" not in content
    assert "hunter2" not in content
    assert content.count(REDACTED) == 2


def test_credentials_are_redacted_in_events(policy, artifacts_root):
    recorder = make_recorder(policy, artifacts_root)

    recorder.append_event("connection", {"detail": "Password=hunter2;User ID=svc_user"})

    events = (recorder.run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "hunter2" not in events
    assert "svc_user" not in events


@pytest.mark.parametrize("bad_name", ["../escape.txt", "sub/file.txt", "", ".", ".."])
def test_artifact_names_must_be_plain_file_names(policy, artifacts_root, bad_name):
    recorder = make_recorder(policy, artifacts_root)

    with pytest.raises(ValueError, match="plain file name"):
        recorder.write_text(bad_name, "x")


def test_write_leaves_no_temporary_files(policy, artifacts_root):
    recorder = make_recorder(policy, artifacts_root)

    recorder.write_json("run.json", {"ok": True})

    assert sorted(path.name for path in recorder.run_dir.iterdir()) == ["run.json"]


@pytest.mark.parametrize(
    ("text", "expected_secret_absent"),
    [
        ('"Username": "epaysetts"', "epaysetts"),
        ('"Password": "p@ss"', "p@ss"),
        ("Password=hunter2;", "hunter2"),
        ("Pwd = s3cret;", "s3cret"),
    ],
)
def test_redaction_patterns(text, expected_secret_absent):
    redacted = redact_text(text)

    assert expected_secret_absent not in redacted
    assert REDACTED in redacted


def test_redaction_leaves_ordinary_values_untouched():
    text = '"Name": "Sales", "dataType": "string"'

    assert redact_text(text) == text
