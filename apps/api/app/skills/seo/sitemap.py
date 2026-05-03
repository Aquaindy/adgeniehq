from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx

USER_AGENT = "AdVantaAI-SEOAgent/0.0.1 (+https://advantaai.com)"
TIMEOUT = 10.0


@dataclass
class SitemapResult:
    """Outcome of sitemap discovery for a site."""

    base_url: str
    sitemap_urls_tried: list[str] = field(default_factory=list)
    sitemap_url_found: str | None = None
    discovered_via_robots: bool = False
    page_urls: list[str] = field(default_factory=list)
    error: str | None = None


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}"


def _try_fetch(url: str) -> httpx.Response | None:
    try:
        return httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/xml,application/xml,*/*;q=0.9"},
            timeout=TIMEOUT,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        return None


def _parse_robots_for_sitemap(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        if line.lower().startswith("sitemap:"):
            value = line.split(":", 1)[1].strip()
            if value:
                out.append(value)
    return out


def _parse_sitemap_xml(content: bytes) -> tuple[list[str], list[str]]:
    """Returns (page_urls, nested_sitemap_urls)."""
    pages: list[str] = []
    nested: list[str] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return [], []

    # Strip namespace for simpler matching
    tag = root.tag.split("}", 1)[-1] if "}" in root.tag else root.tag
    if tag == "sitemapindex":
        for child in root:
            for sub in child:
                sub_tag = sub.tag.split("}", 1)[-1] if "}" in sub.tag else sub.tag
                if sub_tag == "loc" and (sub.text or "").strip():
                    nested.append(sub.text.strip())
    elif tag == "urlset":
        for child in root:
            for sub in child:
                sub_tag = sub.tag.split("}", 1)[-1] if "}" in sub.tag else sub.tag
                if sub_tag == "loc" and (sub.text or "").strip():
                    pages.append(sub.text.strip())
    return pages, nested


def discover_sitemap(site_url: str, *, max_pages: int = 200) -> SitemapResult:
    origin = _origin(site_url)
    result = SitemapResult(base_url=origin)

    # 1. Check robots.txt for Sitemap: lines
    robots_url = urljoin(origin + "/", "/robots.txt")
    result.sitemap_urls_tried.append(robots_url)
    robots_resp = _try_fetch(robots_url)

    candidate_sitemaps: list[str] = []
    if robots_resp is not None and 200 <= robots_resp.status_code < 300:
        for url in _parse_robots_for_sitemap(robots_resp.text):
            candidate_sitemaps.append(url)
            result.discovered_via_robots = True

    # 2. Fall back to common locations
    for fallback in ("/sitemap.xml", "/sitemap_index.xml"):
        absolute = urljoin(origin + "/", fallback)
        if absolute not in candidate_sitemaps:
            candidate_sitemaps.append(absolute)

    pages: list[str] = []
    found_url: str | None = None

    for sitemap_url in candidate_sitemaps:
        result.sitemap_urls_tried.append(sitemap_url)
        response = _try_fetch(sitemap_url)
        if response is None or response.status_code >= 400:
            continue

        page_urls, nested = _parse_sitemap_xml(response.content)
        if page_urls or nested:
            found_url = sitemap_url

        for url in page_urls:
            if url not in pages:
                pages.append(url)
            if len(pages) >= max_pages:
                break

        # Resolve one level of sitemap-index nesting
        for nested_url in nested[:5]:
            nested_resp = _try_fetch(nested_url)
            if nested_resp is None or nested_resp.status_code >= 400:
                continue
            nested_pages, _ = _parse_sitemap_xml(nested_resp.content)
            for url in nested_pages:
                if url not in pages:
                    pages.append(url)
                if len(pages) >= max_pages:
                    break
            if len(pages) >= max_pages:
                break
        if found_url:
            break

    result.sitemap_url_found = found_url
    result.page_urls = pages
    if not found_url:
        result.error = "No sitemap.xml found at /robots.txt, /sitemap.xml, or /sitemap_index.xml."
    return result
