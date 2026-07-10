"""Fetch a public URL and pull out its readable article text.

Thin layer over the SSRF-guarded `fetch_html` (see `app/security/safe_http.py`)
plus a best-effort BeautifulSoup extraction. Used anywhere the product turns a
customer-supplied page into new content — content refresh, and repurposing a
link into social posts. Every fetch is SSRF-guarded because the URL is
customer-controlled.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.skills.website.fetch import WebsiteFetchError, fetch_html

# Tags that never carry article text; stripped before extraction so the body
# isn't polluted with script bodies, nav chrome, or cookie banners.
_NOISE_TAGS = ("script", "style", "noscript", "template", "svg")


class ArticleExtractionError(WebsiteFetchError):
    """The page was fetched but yielded no usable text."""


@dataclass
class ExtractedArticle:
    url: str
    final_url: str
    title: str
    text: str


def _collapse_blank_lines(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    out: list[str] = []
    blank = False
    for line in lines:
        if line:
            out.append(line)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def fetch_and_extract(url: str, *, max_chars: int = 8000) -> ExtractedArticle:
    """Fetch `url` and return its title + readable body.

    Raises `WebsiteFetchError` (which `BlockedURLError` and transport failures
    surface as) when the page can't be reached, and `ArticleExtractionError`
    when it's reachable but empty. `max_chars` bounds the returned text so a
    huge page can't blow up downstream token budgets."""

    from bs4 import BeautifulSoup

    page = fetch_html(url)
    soup = BeautifulSoup(page.html, "html.parser")

    for tag in soup(list(_NOISE_TAGS)):
        tag.decompose()

    # Title: prefer the on-page H1, fall back to <title>, then the URL itself.
    title_tag = soup.find("h1") or soup.find("title")
    title = (title_tag.get_text() if title_tag else url).strip()[:512] or url

    # Body: prefer the semantic article/main landmark, else the whole body.
    container = soup.find("article") or soup.find("main") or soup.body or soup
    text = _collapse_blank_lines(container.get_text("\n"))
    if not text:
        raise ArticleExtractionError(
            f"{url} was reached but contained no readable text.", url=url
        )

    if len(text) > max_chars:
        # Trim on a paragraph boundary so we don't cut mid-sentence.
        text = text[:max_chars].rsplit("\n", 1)[0].strip() or text[:max_chars]

    return ExtractedArticle(
        url=url, final_url=page.final_url, title=title, text=text
    )
