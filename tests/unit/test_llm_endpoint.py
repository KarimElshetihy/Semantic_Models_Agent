"""Endpoint policy tests: loopback is allowed; anything else needs the allowlist and https."""

import pytest

from ssas_agent.llm import EndpointNotAllowedError, check_endpoint
from ssas_agent.llm.config import LOOPBACK_HOSTS


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:1234/v1",
        "HTTP://LOCALHOST:1234/v1",
        "http://127.0.0.1:1234/v1",
        "http://127.0.0.2/v1",
        "http://[::1]:1234/v1",
        "https://localhost/v1",
    ],
)
def test_loopback_endpoints_are_allowed_without_configuration(base_url):
    assert check_endpoint(base_url, LOOPBACK_HOSTS) in {"localhost", "127.0.0.1", "127.0.0.2", "::1"}


def test_remote_host_is_refused_when_not_on_the_allowlist():
    with pytest.raises(EndpointNotAllowedError, match="not on the endpoint allowlist"):
        check_endpoint("https://api.example.com/v1", LOOPBACK_HOSTS)


def test_private_network_address_is_refused_when_not_on_the_allowlist():
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint("http://10.0.0.5:1234/v1", LOOPBACK_HOSTS)


def test_allowlisted_host_is_accepted_over_https():
    host = check_endpoint("https://llm.corp.local/v1", LOOPBACK_HOSTS | {"llm.corp.local"})

    assert host == "llm.corp.local"


def test_allowlisted_host_over_plain_http_is_refused():
    with pytest.raises(EndpointNotAllowedError, match="must be reached over https"):
        check_endpoint("http://llm.corp.local/v1", LOOPBACK_HOSTS | {"llm.corp.local"})


@pytest.mark.parametrize(
    "base_url, reason",
    [
        ("ftp://localhost/v1", "only http and https"),
        ("file:///etc/passwd", "only http and https"),
        ("http://user:pass@localhost:1234/v1", "credentials"),
        ("http:///v1", "no host name"),
    ],
)
def test_unsafe_url_forms_are_refused(base_url, reason):
    with pytest.raises(EndpointNotAllowedError, match=reason):
        check_endpoint(base_url, LOOPBACK_HOSTS)
