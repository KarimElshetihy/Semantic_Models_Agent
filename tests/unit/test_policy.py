"""Path policy tests: deny by default, protected folders, traversal and lookalike folder names."""

import os

import pytest

from ssas_agent.policy import Operation, PathPolicy, PolicyDeniedError


@pytest.fixture
def policy(tmp_path):
    return PathPolicy(project_root=tmp_path)


@pytest.mark.parametrize(
    "relative_path",
    ["example_models/EOPM_MODEL/Model.bim", "tests/fixtures/MOF_MODEL/Model.bim", "workspaces/run1/Model.bim"],
)
def test_read_is_allowed_in_examples_fixtures_and_workspaces(policy, relative_path):
    assert policy.decide(Operation.READ, relative_path).allowed


@pytest.mark.parametrize("relative_path", ["workspaces/run1/Model.bim", "artifacts/run1/diff.txt"])
def test_write_is_allowed_in_workspaces_and_artifacts(policy, relative_path):
    assert policy.decide(Operation.WRITE, relative_path).allowed


@pytest.mark.parametrize(
    "relative_path",
    ["example_models/EOPM_MODEL/EOPM_MODEL/Model.bim", "tests/fixtures/MOF_MODEL/Model.bim"],
)
def test_write_to_protected_folders_is_denied_with_reason(policy, relative_path):
    decision = policy.decide(Operation.WRITE, relative_path)

    assert not decision.allowed
    assert "protected" in decision.reason


@pytest.mark.parametrize("relative_path", ["src/ssas_agent/bim/document.py", "README.md", "pyproject.toml"])
def test_write_outside_allowed_folders_is_denied_by_default(policy, relative_path):
    assert not policy.decide(Operation.WRITE, relative_path).allowed


def test_read_outside_allowed_folders_is_denied_by_default(policy):
    assert not policy.decide(Operation.READ, "src/ssas_agent/bim/document.py").allowed


def test_parent_folder_traversal_into_protected_area_is_denied(policy):
    decision = policy.decide(Operation.WRITE, "workspaces/../example_models/EOPM_MODEL/Model.bim")

    assert not decision.allowed
    assert "protected" in decision.reason


def test_traversal_out_of_project_is_denied(policy, tmp_path):
    outside = tmp_path.parent / "outside.bim"

    assert not policy.decide(Operation.WRITE, outside).allowed


def test_absolute_path_inside_workspaces_is_allowed(policy, tmp_path):
    target = tmp_path / "workspaces" / "run1" / "Model.bim"

    assert policy.decide(Operation.WRITE, target).allowed


def test_lookalike_folder_name_is_not_a_match(policy):
    assert not policy.decide(Operation.WRITE, "workspaces_evil/Model.bim").allowed


def test_relative_paths_are_resolved_against_project_root_not_current_directory(policy, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path.parent)

    assert policy.decide(Operation.WRITE, "workspaces/run1/Model.bim").allowed


def test_unknown_operation_is_denied(policy):
    decision = policy.decide("delete", "workspaces/run1/Model.bim")

    assert not decision.allowed
    assert "unknown operation" in decision.reason


def test_enforce_returns_resolved_path_when_allowed(policy, tmp_path):
    resolved = policy.enforce(Operation.WRITE, "workspaces/run1/Model.bim")

    assert resolved == (tmp_path / "workspaces" / "run1" / "Model.bim").resolve()


def test_enforce_raises_when_denied(policy):
    with pytest.raises(PolicyDeniedError, match="protected"):
        policy.enforce(Operation.WRITE, "example_models/EOPM_MODEL/Model.bim")


def test_symlink_inside_workspaces_pointing_to_protected_folder_is_denied(policy, tmp_path):
    (tmp_path / "workspaces").mkdir()
    (tmp_path / "example_models").mkdir()
    link = tmp_path / "workspaces" / "link"
    try:
        os.symlink(tmp_path / "example_models", link, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation needs extra privileges on this system")

    assert not policy.decide(Operation.WRITE, "workspaces/link/Model.bim").allowed
