"""LLM settings, read from environment variables. No model name, endpoint or key is written in code.

Variables:
    SSAS_AGENT_LLM_BASE_URL          required, e.g. http://localhost:1234/v1
    SSAS_AGENT_LLM_MODEL             required, the model name the server expects
    SSAS_AGENT_LLM_API_KEY           optional, sent as a bearer token
    SSAS_AGENT_LLM_ALLOWED_HOSTS     optional, comma-separated extra hosts (loopback is always allowed)
    SSAS_AGENT_LLM_TIMEOUT_SECONDS   optional, default 60
    SSAS_AGENT_LLM_TEMPERATURE       optional, default 0.0 (0 to 2)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ssas_agent.llm.errors import LlmConfigError

ENV_BASE_URL = "SSAS_AGENT_LLM_BASE_URL"
ENV_MODEL = "SSAS_AGENT_LLM_MODEL"
ENV_API_KEY = "SSAS_AGENT_LLM_API_KEY"
ENV_ALLOWED_HOSTS = "SSAS_AGENT_LLM_ALLOWED_HOSTS"
ENV_TIMEOUT_SECONDS = "SSAS_AGENT_LLM_TIMEOUT_SECONDS"
ENV_TEMPERATURE = "SSAS_AGENT_LLM_TEMPERATURE"

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
    api_key: str | None = field(default=None, repr=False)


def load_settings(environ: Mapping[str, str]) -> LlmSettings:
    return LlmSettings(
        base_url=_required(environ, ENV_BASE_URL),
        model=_required(environ, ENV_MODEL),
        allowed_hosts=_allowed_hosts(environ),
        timeout_seconds=_float_setting(
            environ, ENV_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS, MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS
        ),
        temperature=_float_setting(environ, ENV_TEMPERATURE, DEFAULT_TEMPERATURE, 0.0, MAX_TEMPERATURE),
        api_key=(environ.get(ENV_API_KEY) or "").strip() or None,
    )


def _required(environ: Mapping[str, str], name: str) -> str:
    value = (environ.get(name) or "").strip()
    if not value:
        raise LlmConfigError(f"{name} is not set")
    return value


def _allowed_hosts(environ: Mapping[str, str]) -> frozenset[str]:
    extra = (environ.get(ENV_ALLOWED_HOSTS) or "").split(",")
    return LOOPBACK_HOSTS | frozenset(host.strip().lower() for host in extra if host.strip())


def _float_setting(environ: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise LlmConfigError(f"{name} must be a number") from error
    if not low <= value <= high:
        raise LlmConfigError(f"{name} must be between {low:g} and {high:g}")
    return value
