"""LLM settings. No model name, endpoint or key is written in code.

Each setting is named by LlmSetting. Sources, highest precedence first:
1. real environment variables,
2. the project's .env file (read through the path policy; see .env.example),
3. built-in defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from ssas_agent.llm.env_file import read_env_file
from ssas_agent.llm.errors import LlmConfigError
from ssas_agent.policy import PathPolicy


class LlmSetting(StrEnum):
    BASE_URL = "SSAS_AGENT_LLM_BASE_URL"
    MODEL = "SSAS_AGENT_LLM_MODEL"
    API_KEY = "SSAS_AGENT_LLM_API_KEY"
    ALLOWED_HOSTS = "SSAS_AGENT_LLM_ALLOWED_HOSTS"
    ALLOW_INSECURE_HTTP = "SSAS_AGENT_LLM_ALLOW_INSECURE_HTTP"
    TIMEOUT_SECONDS = "SSAS_AGENT_LLM_TIMEOUT_SECONDS"
    TEMPERATURE = "SSAS_AGENT_LLM_TEMPERATURE"


class SwitchValue(StrEnum):
    TRUE = "true"
    FALSE = "false"


LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MIN_TIMEOUT_SECONDS = 0.1
MAX_TIMEOUT_SECONDS = 3600.0
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
MAX_RESPONSE_BYTES = 1_000_000


@dataclass(frozen=True)
class LlmSettings:
    base_url: str
    model: str
    allowed_hosts: frozenset[str]
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    temperature: float = DEFAULT_TEMPERATURE
    allow_insecure_http: bool = False
    api_key: str | None = field(default=None, repr=False)


def load_settings(environ: Mapping[str, str]) -> LlmSettings:
    """Build the settings from the given mapping only (no file is read)."""
    return LlmSettings(
        base_url=_required(environ, LlmSetting.BASE_URL),
        model=_required(environ, LlmSetting.MODEL),
        allowed_hosts=_allowed_hosts(environ),
        timeout_seconds=_float_setting(
            environ, LlmSetting.TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS, MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS
        ),
        temperature=_float_setting(environ, LlmSetting.TEMPERATURE, DEFAULT_TEMPERATURE, 0.0, MAX_TEMPERATURE),
        allow_insecure_http=_switch_setting(environ, LlmSetting.ALLOW_INSECURE_HTTP),
        api_key=(environ.get(LlmSetting.API_KEY) or "").strip() or None,
    )


def load_project_settings(policy: PathPolicy, environ: Mapping[str, str]) -> LlmSettings:
    """Build the settings from the project's .env file, with real environment variables taking precedence."""
    file_values = read_env_file(policy)
    return load_settings({**file_values, **environ})


def _required(environ: Mapping[str, str], name: LlmSetting) -> str:
    value = (environ.get(name) or "").strip()
    if not value:
        raise LlmConfigError(f"{name} is not set")
    return value


def _allowed_hosts(environ: Mapping[str, str]) -> frozenset[str]:
    extra = (environ.get(LlmSetting.ALLOWED_HOSTS) or "").split(",")
    return LOOPBACK_HOSTS | frozenset(host.strip().lower() for host in extra if host.strip())


def _switch_setting(environ: Mapping[str, str], name: LlmSetting) -> bool:
    raw = (environ.get(name) or "").strip().lower()
    if not raw:
        return False
    try:
        return SwitchValue(raw) is SwitchValue.TRUE
    except ValueError:
        raise LlmConfigError(f"{name} must be '{SwitchValue.TRUE}' or '{SwitchValue.FALSE}'") from None


def _float_setting(
    environ: Mapping[str, str], name: LlmSetting, default: float, low: float, high: float
) -> float:
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise LlmConfigError(f"{name} must be a number") from None
    if not low <= value <= high:
        raise LlmConfigError(f"{name} must be between {low:g} and {high:g}")
    return value
