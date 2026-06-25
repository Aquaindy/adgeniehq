"""SSRF-hardened HTTP GET for fetching customer-supplied URLs.

Any code path that fetches a URL the *customer* controls (the website
crawler, SEO sitemap discovery, landing-page audit) MUST go through
``safe_get`` so the server can never be tricked into reaching internal-only
hosts, loopback, link-local, or the cloud metadata endpoint
(``169.254.169.254`` / ``metadata.google.internal``).

Defenses applied:
  * scheme allow-list (only ``http`` / ``https``);
  * every resolved A/AAAA record is checked — a single private record on an
    otherwise-public hostname is rejected;
  * private / loopback / link-local / reserved / multicast / unspecified IP
    ranges are blocked (covers RFC1918, ``127.0.0.0/8``, ``169.254.0.0/16``,
    IPv6 equivalents, etc.);
  * each redirect hop is re-validated, because an external-looking URL can
    ``30x`` into an internal one (``follow_redirects`` is disabled and
    redirects are followed manually under the same guard).

Residual: a determined attacker controlling authoritative DNS could rebind
between our resolution and httpx's connect (classic TOCTOU). That is a much
narrower window than the direct/redirect vectors this closes and is noted for
a future pinned-resolver hardening pass.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Mapping
from urllib.parse import urljoin, urlparse

import httpx

_ALLOWED_SCHEMES = {"http", "https"}
# Hostnames that must never be reachable regardless of what DNS returns.
_BLOCKED_HOSTNAMES = {"localhost", "metadata", "metadata.google.internal"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_DEFAULT_MAX_REDIRECTS = 5


class BlockedURLError(httpx.HTTPError):
    """A URL was rejected by the SSRF guard.

    Subclasses ``httpx.HTTPError`` so existing callers that already catch
    transport failures treat a blocked URL identically to an unreachable one
    (and therefore never learn that the target was internal)."""


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_url(url: str) -> None:
    """Raise ``BlockedURLError`` if ``url`` is not a safe, public http(s) target."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise BlockedURLError(f"URL scheme '{scheme}' is not allowed.")

    host = parsed.hostname
    if not host:
        raise BlockedURLError("URL has no host.")
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise BlockedURLError("Host is not allowed.")

    # Literal IP in the URL — check it directly without resolving.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _ip_is_blocked(literal):
            raise BlockedURLError("URL points to a non-public address.")
        return

    # Hostname — resolve and reject if ANY record is internal.
    default_port = 443 if scheme == "https" else 80
    try:
        infos = socket.getaddrinfo(
            host, parsed.port or default_port, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as exc:
        raise BlockedURLError(f"Could not resolve host '{host}'.") from exc

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _ip_is_blocked(ip):
            raise BlockedURLError("URL resolves to a non-public address.")


def safe_get(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 10.0,
    max_redirects: int = _DEFAULT_MAX_REDIRECTS,
) -> httpx.Response:
    """SSRF-guarded ``GET``. Validates the target (and every redirect hop)
    before each request. Returns the final ``httpx.Response`` exactly as
    ``httpx.get`` would. Raises ``BlockedURLError`` for a disallowed URL and
    propagates ``httpx`` transport errors otherwise."""
    current = url
    with httpx.Client(follow_redirects=False, timeout=timeout) as client:
        for _ in range(max_redirects + 1):
            _validate_url(current)
            response = client.get(current, headers=dict(headers) if headers else None)
            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("Location")
                if not location:
                    return response
                current = urljoin(str(response.url), location)
                continue
            return response
    raise BlockedURLError("Too many redirects.")
