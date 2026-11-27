"""Endpoint policy: which servers the agent may send model prompts to. Enforced in code, before any request.

The model server may be on this machine, or on a network host that is not known yet. Rules:
- Only http and https URLs.
- No user name or password inside the URL.
- Loopback hosts (localhost, 127.x.x.x, ::1) are allowed over http or https.
- Any other host must be on the allowlist. Over https it is allowed.
- Over plain http, an allowlisted host is allowed only when the insecure-http switch is on.
  Prompts carry model metadata, so plain http is an explicit choice, never a default.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from ssas_agent.llm.config import LlmSetting
from ssas_agent.llm.errors import EndpointNotAllowedError


class UrlScheme(StrEnum):
    HTTP = "http"
    HTTPS = "https"


class EndpointKind(StrEnum):
    LOOPBACK = "loopback"
    ALLOWLISTED_HTTPS = "allowlisted_https"
    ALLOWLISTED_HTTP = "allowlisted_http"


@dataclass(frozen=True)
class EndpointDecision:
    host: str
    kind: EndpointKind


def check_endpoint(
    base_url: str,
    allowed_hosts: frozenset[str],
    allow_insecure_http: bool = False,
) -> EndpointDecision:
    """Return the host and kind if the endpoint is allowed. Raise EndpointNotAllowedError otherwise."""
    parts = urlsplit(base_url)
    _require_scheme(parts.scheme)
    if parts.username or parts.password:
        raise EndpointNotAllowedError("credentials inside the endpoint URL are not allowed")
    host = (parts.hostname or "").lower()
    if not host:
        raise EndpointNotAllowedError("endpoint has no host name")
    if _is_loopback(host):
        return EndpointDecision(host, EndpointKind.LOOPBACK)
    if host not in allowed_hosts:
        raise EndpointNotAllowedError(f"host '{host}' is not on the endpoint allowlist")
    if parts.scheme == UrlScheme.HTTPS:
        return EndpointDecision(host, EndpointKind.ALLOWLISTED_HTTPS)
    if allow_insecure_http:
        return EndpointDecision(host, EndpointKind.ALLOWLISTED_HTTP)
    raise EndpointNotAllowedError(
        f"host '{host}' must be reached over https "
        f"(plain http needs {LlmSetting.ALLOW_INSECURE_HTTP}=true)"
    )


def _require_scheme(scheme: str) -> None:
    if scheme not in {member.value for member in UrlScheme}:
        raise EndpointNotAllowedError("only http and https endpoints are allowed")


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
