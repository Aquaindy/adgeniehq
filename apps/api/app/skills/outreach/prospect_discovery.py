"""Crawl-based prospect discovery.

Given a competitor URL, fetch up to N pages and extract outbound external
links. The intuition: a site that links *out* to a particular domain
multiple times is signalling that domain is a recognised authority in the
space. Those domains are good candidates to also link to *us*.

This intentionally avoids paid backlink data sources (Ahrefs/Moz/DataForSEO).
What it gives up in coverage it gains in being deployable today on any
workspace's free tier."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.core.logging import get_logger
from app.skills.website.fetch import WebsiteFetchError, fetch_html

log = get_logger(__name__)


# Domains we never want to surface as link prospects — social platforms,
# CDNs, bare image hosts, etc.
_SKIP_DOMAIN_SUFFIXES = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "github.com",
    "github.io",
    "gravatar.com",
    "wp.com",
    "w.org",
    "schema.org",
    "google.com",
    "googletagmanager.com",
    "googleapis.com",
    "cloudfront.net",
    "amazonaws.com",
    "amazon.com",
    "akamaized.net",
    "akamai.net",
    "cdninstagram.com",
    "fbcdn.net",
    "twimg.com",
    "ytimg.com",
    "doubleclick.net",
    "gstatic.com",
)


@dataclass
class ProspectCandidate:
    domain: str
    page_url: str | None  # most-recent page where we saw this link
    mention_count: int
    relevance_score: int  # 0-100; deterministic heuristic, not paid data
    sample_anchor_text: str | None


def _registrable_domain(host: str) -> str:
    """Return the public-suffix-aware base domain for grouping (e.g.,
    `news.example.co.uk` → `example.co.uk`). We use a coarse heuristic: take
    the last 2 labels for most TLDs, last 3 for known multi-part TLDs.
    Not perfect but good enough for grouping outbound links."""

    host = host.strip().lower().rstrip(".")
    if not host:
        return ""
    # Strip leading www.
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # Multi-part TLDs (small, hand-picked list — not exhaustive).
    multi = {"co.uk", "co.jp", "co.nz", "co.za", "com.au", "com.br", "com.mx", "com.ar"}
    last_two = ".".join(parts[-2:])
    if last_two in multi:
        return ".".join(parts[-3:])
    return last_two


def _is_skipped(domain: str) -> bool:
    return any(domain == s or domain.endswith("." + s) for s in _SKIP_DOMAIN_SUFFIXES)


def _extract_links(html: str, page_url: str) -> list[tuple[str, str]]:
    """Return [(absolute_url, anchor_text), ...] for each <a href> on the page."""

    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
            continue
        try:
            absolute = urljoin(page_url, href)
        except ValueError:
            continue
        anchor = re.sub(r"\s+", " ", (a.get_text() or "")).strip()
        out.append((absolute, anchor))
    return out


def discover_prospects(
    *,
    competitor_url: str,
    max_pages: int = 15,
    max_prospects: int = 50,
) -> list[ProspectCandidate]:
    """Walk the competitor site (BFS within the same registrable domain),
    collect outbound external links, score them by mention count, and
    return the top N candidates."""

    parsed = urlparse(competitor_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("competitor_url must be http(s)://…")
    if not parsed.netloc:
        raise ValueError("competitor_url must include a hostname.")

    competitor_domain = _registrable_domain(parsed.netloc)

    visited: set[str] = set()
    queue: deque[str] = deque([f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"])

    # outbound_domain → {"page_url": <last seen>, "count": int, "anchor": str}
    outbound: dict[str, dict] = {}

    pages_crawled = 0
    while queue and pages_crawled < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        try:
            page = fetch_html(url)
        except WebsiteFetchError:
            continue
        pages_crawled += 1

        for absolute, anchor in _extract_links(page.html, page.final_url):
            link_parsed = urlparse(absolute)
            if link_parsed.scheme not in ("http", "https") or not link_parsed.netloc:
                continue
            link_domain = _registrable_domain(link_parsed.netloc)
            if not link_domain:
                continue

            if link_domain == competitor_domain:
                # Internal link — enqueue for further crawling.
                if absolute not in visited and len(visited) + len(queue) < max_pages * 4:
                    queue.append(absolute)
                continue

            if _is_skipped(link_domain):
                continue

            entry = outbound.setdefault(
                link_domain,
                {"page_url": page.final_url, "count": 0, "anchor": ""},
            )
            entry["count"] += 1
            entry["page_url"] = page.final_url
            if anchor and not entry["anchor"]:
                entry["anchor"] = anchor[:120]

    candidates: list[ProspectCandidate] = []
    if not outbound:
        return candidates

    max_count = max(e["count"] for e in outbound.values())
    for domain, entry in outbound.items():
        # Score 0-100 by relative mention count. A domain mentioned on every
        # crawled page scores 100; one mentioned once scores ≥ 10 so it's
        # still surfaced as a candidate.
        score = max(10, min(100, round((entry["count"] / max(max_count, 1)) * 100)))
        candidates.append(
            ProspectCandidate(
                domain=domain,
                page_url=entry["page_url"],
                mention_count=entry["count"],
                relevance_score=score,
                sample_anchor_text=entry["anchor"] or None,
            )
        )

    candidates.sort(key=lambda c: (-c.mention_count, c.domain))
    return candidates[:max_prospects]
