"""JSON-LD schema markup generation.

Pure-Python — no LLM call. For SEO-relevant content types we emit a small
JSON-LD object the user can paste into their site's <head>. Schema.org
types per content type:

  blog_post     → Article
  landing_page  → WebPage
  meta_description → WebPage (with description filled in)
  social_post   → Article
  ad_copy       → no schema (not a published page)
  email         → no schema
"""

from __future__ import annotations

from typing import Any

from app.models.content_draft import ContentDraftType


def build_jsonld(
    *,
    type: ContentDraftType,
    title: str,
    body: str,
    target_url: str | None,
    image_url: str | None,
    author_name: str | None = None,
    site_name: str | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any] | None:
    """Return a JSON-LD-compatible dict, or None when the type doesn't take a
    page-level schema (e.g. ad copy, email)."""

    if type in (ContentDraftType.AD_COPY, ContentDraftType.EMAIL):
        return None

    description = _summary(body, limit=200)
    schema: dict[str, Any] = {
        "@context": "https://schema.org",
    }

    if type in (ContentDraftType.BLOG_POST, ContentDraftType.SOCIAL_POST):
        schema["@type"] = "Article"
        schema["headline"] = title[:110]
        schema["description"] = description
        if target_url:
            schema["url"] = target_url
            schema["mainEntityOfPage"] = {
                "@type": "WebPage",
                "@id": target_url,
            }
        if image_url:
            schema["image"] = image_url
        if author_name:
            schema["author"] = {"@type": "Person", "name": author_name}
        if site_name:
            schema["publisher"] = {"@type": "Organization", "name": site_name}
        if keywords:
            schema["keywords"] = ", ".join(keywords[:10])
        # The user fills these on publish; keeping placeholders surfaces the
        # fact that they should set them rather than silently shipping junk.
        schema["datePublished"] = "REPLACE_AT_PUBLISH"
        return schema

    if type == ContentDraftType.LANDING_PAGE:
        schema["@type"] = "WebPage"
        schema["name"] = title[:110]
        schema["description"] = description
        if target_url:
            schema["url"] = target_url
        if image_url:
            schema["image"] = image_url
        if site_name:
            schema["publisher"] = {"@type": "Organization", "name": site_name}
        if keywords:
            schema["keywords"] = ", ".join(keywords[:10])
        return schema

    if type == ContentDraftType.META_DESCRIPTION:
        schema["@type"] = "WebPage"
        schema["description"] = description
        if target_url:
            schema["url"] = target_url
        return schema

    return None


def _summary(body: str, *, limit: int) -> str:
    text = " ".join(body.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"
