from typing import ClassVar
from urllib.parse import urlparse

import httpx

from app.integrations.base import ProviderError
from app.integrations.google_base import GoogleProviderBase


GA4_DATA_API = "https://analyticsdata.googleapis.com/v1beta"
GA4_ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"


class GoogleAnalyticsProvider(GoogleProviderBase):
    provider_id: ClassVar[str] = "google_analytics"
    display_name: ClassVar[str] = "Google Analytics 4"
    description: ClassVar[str] = (
        "Read GA4 conversion and funnel data. Required for ROAS and attribution."
    )

    scopes: ClassVar[list[str]] = [
        *GoogleProviderBase.USERINFO_SCOPES,
        "https://www.googleapis.com/auth/analytics.readonly",
    ]
    # GA4 is consumed read-only — `_resolve_connection` is only called for
    # write actions, so this list stays empty by design.
    write_scopes: ClassVar[list[str]] = []

    @classmethod
    def list_properties(cls, *, access_token: str) -> list[dict]:
        """List GA4 properties the connected account can read."""

        # Step 1: account summaries.
        response = httpx.get(
            f"{GA4_ADMIN_API}/accountSummaries",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"GA4 accountSummaries returned HTTP {response.status_code}."
            )
        body = response.json()
        out: list[dict] = []
        for acct in body.get("accountSummaries", []):
            for prop in acct.get("propertySummaries", []):
                out.append(
                    {
                        "property": prop.get("property"),  # "properties/12345"
                        "display_name": prop.get("displayName"),
                        "account_name": acct.get("displayName"),
                    }
                )
        return out

    @classmethod
    def report_page_metrics(
        cls,
        *,
        access_token: str,
        property_id: str,  # "properties/12345"
        page_paths: list[str],
        start_date: str = "30daysAgo",
        end_date: str = "today",
        conversion_event: str | None = None,
    ) -> dict[str, dict]:
        """Run a GA4 report keyed by `pagePath` for a given list of paths.

        Returns `{path: {"sessions": int, "conversions": int}}`. When
        `conversion_event` is set we filter the conversions metric to events
        matching that name; otherwise we use the built-in `conversions`
        metric (which counts all events flagged as conversions in GA4)."""

        if not page_paths:
            return {}

        body = {
            "dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [
                {"name": "sessions"},
                {"name": "conversions"},
            ],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "pagePath",
                    "inListFilter": {"values": page_paths},
                }
            },
            "limit": 100,
        }
        if conversion_event:
            # Override the conversions metric with a filtered event count.
            body["metrics"] = [
                {"name": "sessions"},
                {
                    "name": "eventCount",
                    "expression": (
                        f"eventCount, eventName="
                        f"\"{conversion_event}\""
                    ),
                },
            ]

        response = httpx.post(
            f"{GA4_DATA_API}/{property_id}:runReport",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"GA4 runReport returned HTTP {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        out: dict[str, dict] = {}
        for row in payload.get("rows", []):
            dims = row.get("dimensionValues", [])
            metrics = row.get("metricValues", [])
            if not dims or not metrics:
                continue
            path = dims[0].get("value", "")
            sessions = int(float(metrics[0].get("value", 0)))
            conversions = int(float(metrics[1].get("value", 0))) if len(metrics) > 1 else 0
            out[path] = {"sessions": sessions, "conversions": conversions}
        return out


def url_to_path(url: str) -> str:
    """Helper: strip scheme + host, leaving the path GA4 reports against."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return path
