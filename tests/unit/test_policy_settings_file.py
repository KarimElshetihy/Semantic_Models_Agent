"""The only root-level file the agent may read is the .env settings file, and it can never be written."""

import pytest

from ssas_agent.policy import READABLE_FILES, Operation, PathPolicy


@pytest.fixture
def policy(tmp_path):
    return PathPolicy(project_root=tmp_path)


def test_env_file_at_project_root_is_readable(policy):
    assert policy.decide(Operation.READ, ".env").allowed


def test_env_file_is_never_writable(policy):
    assert not policy.decide(Operation.WRITE, ".env").allowed


@pytest.mark.parametrize("relative_path", [".env.bak", "config/.env", "env"])
def test_lookalike_env_files_are_not_readable(policy, relative_path):
    assert not policy.decide(Operation.READ, relative_path).allowed


@pytest.mark.parametrize("relative_path", ["README.md", "pyproject.toml", "src/ssas_agent/policy/path_policy.py"])
def test_other_root_files_stay_unreadable(policy, relative_path):
    assert not policy.decide(Operation.READ, relative_path).allowed


def test_readable_file_list_contains_only_the_env_file():
    assert READABLE_FILES == (".env",)
