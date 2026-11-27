"""Endpoint policy: which servers the agent may send model prompts to. Enforced in code, before any request.

Rules:
- Only http and https URLs.
- No user name or password inside the URL.
- Loopback hosts (localhost, 127.x.x.x, ::1) are allowed over http or https.
- Any other host must be on the allowlist and must use https.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from ssas_agent.llm.errors import EndpointNotAllowedError

ALLOWED_SCHEMES = frozenset({"http", "https"})


def check_endpoint(base_url: str, allowed_hosts: frozenset[str]) -> str:
    """Return the lower-case host name if the endpoint is allowed. Raise EndpointNotAllowedError otherwise."""
    parts = urlsplit(base_url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise EndpointNotAllowedError("only http and https endpoints are allowed")
    if parts.username or parts.password:
        raise EndpointNotAllowedError("credentials inside the endpoint URL are not allowed")
    host = (parts.hostname or "").lower()
    if not host:
        raise EndpointNotAllowedError("endpoint has no host name")
    if _is_loopback(host):
        return host
    if host not in allowed_hosts:
        raise EndpointNotAllowedError(f"host '{host}' is not on the endpoint allowlist")
    if parts.scheme != "https":
        raise EndpointNotAllowedError(f"host '{host}' must be reached over https")
    return host


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
