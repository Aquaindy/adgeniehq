"""Google PageSpeed Insights skill.

Calls the PSI v5 endpoint. An API key in `PAGESPEED_API_KEY` raises the rate
limit; without one, calls still work but are throttled to a few per minute."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
TIMEOUT_SECONDS = 60.0


class PageSpeedError(Exception):
    pass


@dataclass
class PageSpeedResult:
    url: str
    strategy: str
    performance: float | None
    accessibility: float | None
    best_practices: float | None
    seo: float | None
    raw: dict


def fetch_page_speed(*, url: str, strategy: str = "mobile") -> PageSpeedResult:
    api_key = os.getenv("PAGESPEED_API_KEY", "").strip()
    params: dict[str, str | list[str]] = {
        "url": url,
        "strategy": strategy,
        "category": ["performance", "accessibility", "best-practices", "seo"],
    }
    if api_key:
        params["key"] = api_key

    try:
        response = httpx.get(PSI_ENDPOINT, params=params, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise PageSpeedError(f"PageSpeed Insights request failed: {exc}") from exc

    if response.status_code >= 400:
        raise PageSpeedError(f"PageSpeed Insights returned HTTP {response.status_code}.")

    body = response.json()
    categories = (body.get("lighthouseResult") or {}).get("categories") or {}

    def _score(name: str) -> float | None:
        cat = categories.get(name)
        if not cat or cat.get("score") is None:
            return None
        try:
            return float(cat["score"])
        except (TypeError, ValueError):
            return None

    return PageSpeedResult(
        url=url,
        strategy=strategy,
        performance=_score("performance"),
        accessibility=_score("accessibility"),
        best_practices=_score("best-practices"),
        seo=_score("seo"),
        raw=body,
    )
