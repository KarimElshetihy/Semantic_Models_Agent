"""LLM settings from a mapping: required and optional values, defaults, blank values, number and switch ranges."""

import pytest

from ssas_agent.llm import LlmConfigError, LlmSetting, load_settings
from ssas_agent.llm.config import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    LOOPBACK_HOSTS,
)

BASE_ENVIRONMENT = {
    LlmSetting.BASE_URL: "http://localhost:1234/v1",
    LlmSetting.MODEL: "some-local-model",
}


def test_minimal_environment_gives_safe_defaults():
    settings = load_settings(BASE_ENVIRONMENT)

    assert settings.base_url == "http://localhost:1234/v1"
    assert settings.model == "some-local-model"
    assert settings.allowed_hosts == LOOPBACK_HOSTS
    assert settings.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert settings.temperature == DEFAULT_TEMPERATURE
    assert settings.allow_insecure_http is False
    assert settings.api_key is None


@pytest.mark.parametrize("missing", [LlmSetting.BASE_URL, LlmSetting.MODEL])
def test_missing_required_setting_is_named_in_the_error(missing):
    environment = {name: value for name, value in BASE_ENVIRONMENT.items() if name != missing}

    with pytest.raises(LlmConfigError, match=missing.value):
        load_settings(environment)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_required_setting_counts_as_missing(blank):
    with pytest.raises(LlmConfigError, match=LlmSetting.MODEL.value):
        load_settings({**BASE_ENVIRONMENT, LlmSetting.MODEL: blank})


def test_no_model_name_is_built_in():
    with pytest.raises(LlmConfigError):
        load_settings({LlmSetting.BASE_URL: "http://localhost:1234/v1"})


def test_api_key_is_read_and_stripped():
    settings = load_settings({**BASE_ENVIRONMENT, LlmSetting.API_KEY: "  secret-token  "})

    assert settings.api_key == "secret-token"


def test_blank_api_key_means_no_key():
    assert load_settings({**BASE_ENVIRONMENT, LlmSetting.API_KEY: "   "}).api_key is None


def test_api_key_is_hidden_from_the_printed_settings():
    settings = load_settings({**BASE_ENVIRONMENT, LlmSetting.API_KEY: "secret-token"})

    assert "secret-token" not in repr(settings)


def test_extra_allowed_hosts_are_added_in_lower_case_to_loopback():
    settings = load_settings(
        {**BASE_ENVIRONMENT, LlmSetting.ALLOWED_HOSTS: " LLM.Corp.Local , other.host,, "}
    )

    assert settings.allowed_hosts == LOOPBACK_HOSTS | {"llm.corp.local", "other.host"}


def test_timeout_and_temperature_are_read_as_numbers():
    settings = load_settings(
        {**BASE_ENVIRONMENT, LlmSetting.TIMEOUT_SECONDS: "12.5", LlmSetting.TEMPERATURE: "0.7"}
    )

    assert settings.timeout_seconds == 12.5
    assert settings.temperature == 0.7


@pytest.mark.parametrize("value", ["true", "TRUE", " true "])
def test_insecure_http_switch_on(value):
    settings = load_settings({**BASE_ENVIRONMENT, LlmSetting.ALLOW_INSECURE_HTTP: value})

    assert settings.allow_insecure_http is True


def test_insecure_http_switch_off():
    settings = load_settings({**BASE_ENVIRONMENT, LlmSetting.ALLOW_INSECURE_HTTP: "false"})

    assert settings.allow_insecure_http is False


@pytest.mark.parametrize(
    "name, value",
    [
        (LlmSetting.TIMEOUT_SECONDS, "soon"),
        (LlmSetting.TIMEOUT_SECONDS, "0"),
        (LlmSetting.TIMEOUT_SECONDS, "99999"),
        (LlmSetting.TEMPERATURE, "-0.1"),
        (LlmSetting.TEMPERATURE, "2.5"),
        (LlmSetting.ALLOW_INSECURE_HTTP, "yes"),
        (LlmSetting.ALLOW_INSECURE_HTTP, "1"),
    ],
)
def test_invalid_setting_values_are_refused(name, value):
    with pytest.raises(LlmConfigError, match=name.value):
        load_settings({**BASE_ENVIRONMENT, name: value})
