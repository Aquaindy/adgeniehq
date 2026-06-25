"""SSRF guard tests for app.security.safe_http.

These verify the URL validator that protects the website/SEO fetchers from
being pointed at internal hosts, loopback, link-local, or the cloud metadata
endpoint. We test the validator directly (no network) plus the redirect
re-validation via a mocked transport.
"""

import httpx
import pytest

from app.security import safe_http
from app.security.safe_http import BlockedURLError, _validate_url, safe_get


# --- scheme + literal-IP / hostname blocking -------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # AWS metadata
        "http://[fd00::1]/",  # IPv6 ULA (private)
        "http://127.0.0.1:8000/",  # loopback
        "http://localhost/admin",  # loopback hostname
        "http://10.0.0.5/",  # RFC1918
        "http://192.168.1.1/",  # RFC1918
        "http://172.16.0.1/",  # RFC1918
        "http://0.0.0.0/",  # unspecified
        "http://metadata.google.internal/computeMetadata/v1/",  # GCP metadata host
        "file:///etc/passwd",  # disallowed scheme
        "gopher://127.0.0.1/",  # disallowed scheme
        "ftp://example.com/",  # disallowed scheme
        "http:///nohost",  # no host
    ],
)
def test_validate_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(BlockedURLError):
        _validate_url(url)


def test_validate_rejects_hostname_resolving_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    # A public-looking hostname whose DNS returns a private address must be blocked.
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(2, 1, 6, "", ("10.1.2.3", port))]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(BlockedURLError):
        _validate_url("http://evil.example.com/")


def test_validate_rejects_when_any_record_is_private(monkeypatch: pytest.MonkeyPatch) -> None:
    # Public + private record mix (DNS rebinding style) — reject on the private one.
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (2, 1, 6, "", ("93.184.216.34", port)),  # public
            (2, 1, 6, "", ("127.0.0.1", port)),  # loopback
        ]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(BlockedURLError):
        _validate_url("http://mixed.example.com/")


def test_validate_allows_public_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)
    _validate_url("https://example.com/page")  # does not raise


# --- redirect re-validation ------------------------------------------------

def test_safe_get_blocks_redirect_to_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    """An external-looking URL that 302s to the metadata endpoint must be
    blocked at the redirect hop, not followed."""
    # Treat all hostnames as public so the *only* thing that can block is the
    # literal metadata IP in the redirect Location.
    monkeypatch.setattr(
        safe_http.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("93.184.216.34", port))],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "good.example.com":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/"})
        return httpx.Response(200, text="should-not-reach")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(safe_http.httpx, "Client", client_factory)

    with pytest.raises(BlockedURLError):
        safe_get("http://good.example.com/start")


def test_safe_get_returns_response_for_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        safe_http.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("93.184.216.34", port))],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>ok</html>")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(safe_http.httpx, "Client", client_factory)

    resp = safe_get("https://example.com/")
    assert resp.status_code == 200
    assert "ok" in resp.text
