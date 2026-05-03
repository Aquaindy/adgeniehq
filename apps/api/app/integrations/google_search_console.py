from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar
from urllib.parse import quote

import httpx

from app.integrations.base import ProviderError
from app.integrations.google_base import GoogleProviderBase

GSC_API = "https://www.googleapis.com/webmasters/v3"


@dataclass
class GSCKeywordRow:
    query: str
    clicks: int
    impressions: int
    ctr: float
    position: float
    top_page: str | None


@dataclass
class GSCSearchAnalyticsResult:
    site_url: str
    period_start: date
    period_end: date
    rows: list[GSCKeywordRow]


class GoogleSearchConsoleProvider(GoogleProviderBase):
    provider_id: ClassVar[str] = "google_search_console"
    display_name: ClassVar[str] = "Google Search Console"
    description: ClassVar[str] = (
        "Read search visibility and keyword opportunities for the connected site."
    )

    scopes: ClassVar[list[str]] = [
        *GoogleProviderBase.USERINFO_SCOPES,
        "https://www.googleapis.com/auth/webmasters.readonly",
    ]
    # GSC is consumed read-only — explicit empty list documents the choice.
    write_scopes: ClassVar[list[str]] = []

    # ------------------------------------------------------------------
    # Search Analytics — used by M8's GSC sync
    # ------------------------------------------------------------------

    @classmethod
    def list_sites(cls, *, access_token: str) -> list[dict]:
        response = httpx.get(
            f"{GSC_API}/sites",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(f"GSC `/sites` returned HTTP {response.status_code}.")
        return response.json().get("siteEntry", [])

    @classmethod
    def fetch_search_analytics(
        cls,
        *,
        access_token: str,
        site_url: str,
        days: int = 28,
        row_limit: int = 250,
    ) -> GSCSearchAnalyticsResult:
        end = date.today()
        start = end - timedelta(days=days)
        path_site = quote(site_url, safe="")

        response = httpx.post(
            f"{GSC_API}/sites/{path_site}/searchAnalytics/query",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "dimensions": ["query", "page"],
                "rowLimit": row_limit,
                "type": "web",
            },
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"GSC searchAnalytics query for {site_url} returned HTTP {response.status_code}."
            )

        rows = response.json().get("rows", [])
        per_query: dict[str, GSCKeywordRow] = {}
        for raw in rows:
            keys = raw.get("keys", [])
            if not keys:
                continue
            query = keys[0]
            page = keys[1] if len(keys) > 1 else None
            clicks = int(raw.get("clicks", 0))
            impressions = int(raw.get("impressions", 0))
            position = float(raw.get("position", 0.0))

            existing = per_query.get(query)
            if existing is None:
                per_query[query] = GSCKeywordRow(
                    query=query,
                    clicks=clicks,
                    impressions=impressions,
                    ctr=0.0,
                    position=position,
                    top_page=page,
                )
            else:
                # Track the page that drives the most clicks as `top_page`
                if clicks > existing.clicks:
                    existing.top_page = page
                existing.clicks += clicks
                existing.impressions += impressions
                # Average position weighted by impressions
                if existing.impressions:
                    existing.position = (
                        (existing.position * (existing.impressions - impressions))
                        + (position * impressions)
                    ) / existing.impressions

        # Recompute aggregate CTR per query
        for kw in per_query.values():
            kw.ctr = (kw.clicks / kw.impressions) if kw.impressions else 0.0

        return GSCSearchAnalyticsResult(
            site_url=site_url,
            period_start=start,
            period_end=end,
            rows=sorted(per_query.values(), key=lambda r: r.impressions, reverse=True),
        )
