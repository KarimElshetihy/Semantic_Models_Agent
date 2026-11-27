"""LLM settings come from the environment only, with clear errors and no secret in the printed form."""

import pytest

from ssas_agent.llm import LlmConfigError, load_settings
from ssas_agent.llm.config import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    ENV_API_KEY,
    ENV_ALLOWED_HOSTS,
    ENV_BASE_URL,
    ENV_MODEL,
    ENV_TEMPERATURE,
    ENV_TIMEOUT_SECONDS,
    LOOPBACK_HOSTS,
)

BASE_ENV = {ENV_BASE_URL: "http://localhost:1234/v1", ENV_MODEL: "some-local-model"}


def test_minimal_environment_gives_safe_defaults():
    settings = load_settings(BASE_ENV)

    assert settings.base_url == "http://localhost:1234/v1"
    assert settings.model == "some-local-model"
    assert settings.allowed_hosts == LOOPBACK_HOSTS
    assert settings.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert settings.temperature == DEFAULT_TEMPERATURE
    assert settings.api_key is None


@pytest.mark.parametrize("missing", [ENV_BASE_URL, ENV_MODEL])
def test_missing_required_setting_is_named_in_the_error(missing):
    environ = {key: value for key, value in BASE_ENV.items() if key != missing}

    with pytest.raises(LlmConfigError, match=missing):
        load_settings(environ)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_required_setting_counts_as_missing(blank):
    with pytest.raises(LlmConfigError, match=ENV_MODEL):
        load_settings({**BASE_ENV, ENV_MODEL: blank})


def test_no_model_name_is_built_in():
    with pytest.raises(LlmConfigError):
        load_settings({ENV_BASE_URL: "http://localhost:1234/v1"})


def test_api_key_is_read_and_stripped():
    settings = load_settings({**BASE_ENV, ENV_API_KEY: "  secret-token  "})

    assert settings.api_key == "secret-token"


def test_blank_api_key_means_no_key():
    assert load_settings({**BASE_ENV, ENV_API_KEY: "   "}).api_key is None


def test_api_key_is_hidden_from_the_printed_settings():
    settings = load_settings({**BASE_ENV, ENV_API_KEY: "secret-token"})

    assert "secret-token" not in repr(settings)


def test_extra_allowed_hosts_are_added_in_lower_case_to_loopback():
    settings = load_settings({**BASE_ENV, ENV_ALLOWED_HOSTS: " LLM.Corp.Local , other.host,, "})

    assert settings.allowed_hosts == LOOPBACK_HOSTS | {"llm.corp.local", "other.host"}


def test_timeout_and_temperature_are_read_as_numbers():
    settings = load_settings({**BASE_ENV, ENV_TIMEOUT_SECONDS: "12.5", ENV_TEMPERATURE: "0.7"})

    assert settings.timeout_seconds == 12.5
    assert settings.temperature == 0.7


@pytest.mark.parametrize(
    "name, value",
    [
        (ENV_TIMEOUT_SECONDS, "soon"),
        (ENV_TIMEOUT_SECONDS, "0"),
        (ENV_TIMEOUT_SECONDS, "99999"),
        (ENV_TEMPERATURE, "-0.1"),
        (ENV_TEMPERATURE, "2.5"),
    ],
)
def test_invalid_number_settings_are_refused(name, value):
    with pytest.raises(LlmConfigError, match=name):
        load_settings({**BASE_ENV, name: value})
