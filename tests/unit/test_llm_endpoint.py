"""Endpoint policy tests: loopback is allowed; network hosts need the allowlist; plain http needs the switch."""

import pytest

from ssas_agent.llm import EndpointKind, EndpointNotAllowedError, check_endpoint
from ssas_agent.llm.config import LOOPBACK_HOSTS

NETWORK_HOST = "llm.corp.local"
ALLOWLIST = LOOPBACK_HOSTS | {NETWORK_HOST}


@pytest.mark.parametrize(
    "base_url, expected_host",
    [
        ("http://localhost:1234/v1", "localhost"),
        ("HTTP://LOCALHOST:1234/v1", "localhost"),
        ("http://127.0.0.1:1234/v1", "127.0.0.1"),
        ("http://127.0.0.2/v1", "127.0.0.2"),
        ("http://[::1]:1234/v1", "::1"),
        ("https://localhost/v1", "localhost"),
    ],
)
def test_loopback_endpoints_are_allowed_without_configuration(base_url, expected_host):
    decision = check_endpoint(base_url, LOOPBACK_HOSTS)

    assert decision.host == expected_host
    assert decision.kind is EndpointKind.LOOPBACK


def test_network_host_is_refused_when_not_on_the_allowlist():
    with pytest.raises(EndpointNotAllowedError, match="not on the endpoint allowlist"):
        check_endpoint("https://api.example.com/v1", LOOPBACK_HOSTS)


def test_private_network_address_is_refused_when_not_on_the_allowlist():
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint("http://10.0.0.5:1234/v1", LOOPBACK_HOSTS, allow_insecure_http=True)


def test_allowlisted_host_is_accepted_over_https():
    decision = check_endpoint(f"https://{NETWORK_HOST}/v1", ALLOWLIST)

    assert decision.host == NETWORK_HOST
    assert decision.kind is EndpointKind.ALLOWLISTED_HTTPS


def test_allowlisted_host_over_plain_http_is_refused_by_default():
    with pytest.raises(EndpointNotAllowedError, match="must be reached over https"):
        check_endpoint(f"http://{NETWORK_HOST}/v1", ALLOWLIST)


def test_allowlisted_host_over_plain_http_is_accepted_when_the_switch_is_on():
    decision = check_endpoint(f"http://{NETWORK_HOST}:8080/v1", ALLOWLIST, allow_insecure_http=True)

    assert decision.host == NETWORK_HOST
    assert decision.kind is EndpointKind.ALLOWLISTED_HTTP


def test_insecure_switch_does_not_open_hosts_that_are_not_allowlisted():
    with pytest.raises(EndpointNotAllowedError, match="not on the endpoint allowlist"):
        check_endpoint("http://other.example.com/v1", ALLOWLIST, allow_insecure_http=True)


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
