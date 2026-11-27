"""The .env reader: format rules, error messages that hide values, reads only through the path policy,
and the precedence of real environment variables over the file."""

import pytest

from ssas_agent.llm import (
    ENV_FILE_NAME,
    EnvFileError,
    LlmConfigError,
    LlmSetting,
    load_project_settings,
    parse_env_text,
    read_env_file,
)
from ssas_agent.policy import PathPolicy

FILE_BASE_URL = "http://localhost:1234/v1"
FILE_MODEL = "file-model"


@pytest.fixture
def policy(tmp_path):
    return PathPolicy(project_root=tmp_path)


def write_env_file(project_root, text):
    (project_root / ENV_FILE_NAME).write_bytes(text.encode("utf-8"))


def test_simple_pairs_are_parsed():
    assert parse_env_text("A=1\nB=two") == {"A": "1", "B": "two"}


def test_blank_lines_and_comment_lines_are_ignored():
    assert parse_env_text("# note\n\n   \nA=1\n  # another note\n") == {"A": "1"}


def test_export_prefix_and_spaces_around_the_key_are_allowed():
    assert parse_env_text("export  A = 1 ") == {"A": "1"}


def test_quoted_values_keep_hash_and_equals_signs():
    text = "A=\"x # y = z\"\nB='p#q'"

    assert parse_env_text(text) == {"A": "x # y = z", "B": "p#q"}


def test_unquoted_value_may_end_with_a_comment():
    assert parse_env_text("A=value   # the note") == {"A": "value"}


def test_hash_without_a_space_before_it_stays_in_an_unquoted_value():
    assert parse_env_text("A=abc#def") == {"A": "abc#def"}


def test_empty_value_is_allowed():
    assert parse_env_text("A=") == {"A": ""}


def test_windows_line_endings_are_accepted():
    assert parse_env_text("A=1\r\nB=2\r\n") == {"A": "1", "B": "2"}


@pytest.mark.parametrize(
    "text, reason",
    [
        ("GOOD=1\nnot an assignment", "line 2: expected KEY=VALUE"),
        ("1BAD=x", "line 1: expected KEY=VALUE"),
        ("A=\"unclosed", "line 1: the quoted value of 'A' is not closed"),
        ("A=\"ok\" trailing", "line 1: unexpected text after the quoted value of 'A'"),
    ],
)
def test_malformed_lines_are_refused_with_a_line_number(text, reason):
    with pytest.raises(EnvFileError, match=reason):
        parse_env_text(text)


def test_error_message_never_shows_the_value():
    with pytest.raises(EnvFileError) as error:
        parse_env_text("GOOD=1\nnot-an-assignment-SECRET-VALUE")

    assert "SECRET-VALUE" not in str(error.value)


def test_duplicate_key_is_refused_and_the_error_names_only_the_key():
    with pytest.raises(EnvFileError, match="'A' is set more than once") as error:
        parse_env_text("A=first-SECRET\nA=second-SECRET")

    assert "SECRET" not in str(error.value)


def test_missing_env_file_gives_no_values(policy):
    assert read_env_file(policy) == {}


def test_env_file_is_read_through_the_policy(policy):
    write_env_file(policy.project_root, f"{LlmSetting.MODEL}={FILE_MODEL}\n")

    assert read_env_file(policy) == {LlmSetting.MODEL.value: FILE_MODEL}


def test_byte_order_mark_is_ignored(policy):
    (policy.project_root / ENV_FILE_NAME).write_bytes(b"\xef\xbb\xbfA=1\n")

    assert read_env_file(policy) == {"A": "1"}


def test_file_that_is_not_utf8_is_refused(policy):
    (policy.project_root / ENV_FILE_NAME).write_bytes(b"A=\xff\xfe\n")

    with pytest.raises(EnvFileError, match="could not be read as UTF-8"):
        read_env_file(policy)


def test_project_settings_come_from_the_env_file(policy):
    write_env_file(policy.project_root, f"{LlmSetting.BASE_URL}={FILE_BASE_URL}\n{LlmSetting.MODEL}={FILE_MODEL}\n")

    settings = load_project_settings(policy, {})

    assert settings.base_url == FILE_BASE_URL
    assert settings.model == FILE_MODEL


def test_real_environment_variables_override_the_env_file(policy):
    write_env_file(policy.project_root, f"{LlmSetting.BASE_URL}={FILE_BASE_URL}\n{LlmSetting.MODEL}={FILE_MODEL}\n")

    settings = load_project_settings(policy, {LlmSetting.BASE_URL: "http://127.0.0.1:9999/v1"})

    assert settings.base_url == "http://127.0.0.1:9999/v1"
    assert settings.model == FILE_MODEL


def test_settings_can_come_from_the_environment_alone(policy):
    settings = load_project_settings(
        policy, {LlmSetting.BASE_URL: FILE_BASE_URL, LlmSetting.MODEL: FILE_MODEL}
    )

    assert settings.model == FILE_MODEL


def test_missing_settings_everywhere_are_reported(policy):
    with pytest.raises(LlmConfigError, match=LlmSetting.BASE_URL.value):
        load_project_settings(policy, {})


def test_api_key_from_the_file_stays_hidden(policy):
    write_env_file(
        policy.project_root,
        f"{LlmSetting.BASE_URL}={FILE_BASE_URL}\n{LlmSetting.MODEL}={FILE_MODEL}\n{LlmSetting.API_KEY}=file-secret\n",
    )

    settings = load_project_settings(policy, {})

    assert settings.api_key == "file-secret"
    assert "file-secret" not in repr(settings)
