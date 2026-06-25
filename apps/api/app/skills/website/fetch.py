from dataclasses import dataclass

import httpx

from app.security.safe_http import safe_get

USER_AGENT = "AdVantaAI-WebsiteAgent/0.0.1 (+https://advantaai.com)"
MAX_BYTES = 1_500_000  # 1.5 MB cap on fetched HTML
TIMEOUT_SECONDS = 10.0


@dataclass
class FetchedPage:
    url: str
    final_url: str
    status_code: int
    content_type: str | None
    html: str


class WebsiteFetchError(Exception):
    def __init__(self, message: str, *, url: str):
        super().__init__(message)
        self.url = url


def fetch_html(url: str) -> FetchedPage:
    """Synchronously fetch a page's HTML. Raises WebsiteFetchError on transport
    failure or non-2xx response."""
    try:
        # SSRF-guarded: rejects internal/loopback/link-local/metadata targets
        # and re-validates every redirect hop. A blocked URL surfaces as a
        # normal "could not reach" error so internals aren't disclosed.
        response = safe_get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.9"},
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise WebsiteFetchError(f"Could not reach {url}: {exc.__class__.__name__}", url=url) from exc

    if response.status_code >= 400:
        raise WebsiteFetchError(
            f"{url} returned HTTP {response.status_code}.",
            url=url,
        )

    content = response.content[:MAX_BYTES]
    text = content.decode(response.encoding or "utf-8", errors="replace")

    return FetchedPage(
        url=url,
        final_url=str(response.url),
        status_code=response.status_code,
        content_type=response.headers.get("Content-Type"),
        html=text,
    )
