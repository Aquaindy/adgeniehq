from datetime import date
from typing import ClassVar
from urllib.parse import quote

import httpx

from app.integrations.base import (
    BaseProvider,
    CampaignData,
    ProviderAccountInfo,
    ProviderError,
)
from app.models.campaign import CampaignStatus

LI_API = "https://api.linkedin.com/rest"
LI_API_VERSION = "202410"

LINKEDIN_STATUS_MAP = {
    "ACTIVE": CampaignStatus.ACTIVE,
    "PAUSED": CampaignStatus.PAUSED,
    "DRAFT": CampaignStatus.PAUSED,
    "PENDING_DELETION": CampaignStatus.ENDED,
    "ARCHIVED": CampaignStatus.ARCHIVED,
    "CANCELED": CampaignStatus.ENDED,
    "COMPLETED": CampaignStatus.ENDED,
    "REMOVED": CampaignStatus.ENDED,
}


def _parse_li_run_schedule(schedule: dict | None, key: str) -> date | None:
    if not schedule:
        return None
    value = schedule.get(key)
    if value is None:
        return None
    try:
        # LinkedIn timestamps are millis-since-epoch
        from datetime import datetime, timezone

        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).date()
    except (TypeError, ValueError):
        return None


class LinkedInAdsProvider(BaseProvider):
    provider_id: ClassVar[str] = "linkedin_ads"
    display_name: ClassVar[str] = "LinkedIn Ads"
    description: ClassVar[str] = (
        "Sync B2B ad campaigns and reporting from LinkedIn Marketing Solutions."
    )

    auth_url: ClassVar[str] = "https://www.linkedin.com/oauth/v2/authorization"
    token_url: ClassVar[str] = "https://www.linkedin.com/oauth/v2/accessToken"

    scopes: ClassVar[list[str]] = [
        "r_ads",
        "r_ads_reporting",
        "r_organization_social",
        "rw_ads",  # Required for outbound campaign mutations.
    ]
    # LinkedIn separates read (`r_ads`) and write (`rw_ads`) scopes. Without
    # `rw_ads` any pause/budget/audience update would 403.
    write_scopes: ClassVar[list[str]] = ["rw_ads"]

    client_id_env: ClassVar[str] = "LINKEDIN_CLIENT_ID"
    client_secret_env: ClassVar[str] = "LINKEDIN_CLIENT_SECRET"

    @classmethod
    def _common_headers(cls, *, access_token: str) -> dict:
        return {
            "Authorization": f"Bearer {access_token}",
            "LinkedIn-Version": LI_API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        }

    @classmethod
    def fetch_account_info(cls, *, access_token: str) -> ProviderAccountInfo:
        response = httpx.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise ProviderError(f"LinkedIn `/me` returned HTTP {response.status_code}.")
        body = response.json()
        first = (body.get("localizedFirstName") or "").strip()
        last = (body.get("localizedLastName") or "").strip()
        name = f"{first} {last}".strip() or None
        return ProviderAccountInfo(
            provider_account_id=body.get("id"),
            display_name=name,
        )

    @classmethod
    def sync_campaigns(cls, *, access_token: str) -> list[CampaignData]:
        accounts = cls._fetch_ad_accounts(access_token=access_token)
        out: list[CampaignData] = []
        for account in accounts:
            account_id = str(account.get("id")) if account.get("id") else None
            currency = account.get("currency")
            if not account_id:
                continue
            try:
                campaigns = cls._fetch_campaigns(
                    access_token=access_token, account_id=account_id
                )
            except ProviderError:
                continue
            for raw in campaigns:
                out.append(cls._normalize(raw, account_id=account_id, currency=currency))
        return out

    @classmethod
    def _fetch_ad_accounts(cls, *, access_token: str) -> list[dict]:
        response = httpx.get(
            f"{LI_API}/adAccounts",
            params={"q": "search", "search.status.values[0]": "ACTIVE"},
            headers=cls._common_headers(access_token=access_token),
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"LinkedIn `/adAccounts` returned HTTP {response.status_code}."
            )
        return response.json().get("elements", [])

    @classmethod
    def _fetch_campaigns(cls, *, access_token: str, account_id: str) -> list[dict]:
        response = httpx.get(
            f"{LI_API}/adAccounts/{account_id}/adCampaigns",
            params={"q": "search"},
            headers=cls._common_headers(access_token=access_token),
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"LinkedIn campaigns for account {account_id} returned HTTP {response.status_code}."
            )
        return response.json().get("elements", [])

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    @classmethod
    def _campaign_url(cls, account_id: str, external_id: str) -> str:
        return f"{LI_API}/adAccounts/{account_id}/adCampaigns/{external_id}"

    @classmethod
    def fetch_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:
        response = httpx.get(
            cls._campaign_url(external_account_id, external_id),
            headers=cls._common_headers(access_token=access_token),
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"LinkedIn GET campaign returned HTTP {response.status_code}."
            )
        return response.json()

    @classmethod
    def _partial_update(
        cls, *, access_token: str, account_id: str, external_id: str, patch: dict
    ) -> dict:
        # LinkedIn partial updates use POST + X-RestLi-Method: PARTIAL_UPDATE
        # with a body of {"patch": {"$set": {...}}}.
        headers = cls._common_headers(access_token=access_token)
        headers["X-RestLi-Method"] = "PARTIAL_UPDATE"
        headers["Content-Type"] = "application/json"
        response = httpx.post(
            cls._campaign_url(account_id, external_id),
            headers=headers,
            json={"patch": {"$set": patch}},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"LinkedIn partial-update returned HTTP {response.status_code}: {response.text[:200]}"
            )
        # LinkedIn often returns 204 No Content on partial-update success.
        if not response.content:
            return {"ok": True}
        try:
            return response.json()
        except ValueError:
            return {"ok": True}

    @classmethod
    def pause_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:
        prior = cls.fetch_campaign(
            access_token=access_token,
            external_account_id=external_account_id,
            external_id=external_id,
        )
        result = cls._partial_update(
            access_token=access_token,
            account_id=external_account_id,
            external_id=external_id,
            patch={"status": "PAUSED"},
        )
        return {
            "ok": True,
            "prior_state": {"status": prior.get("status")},
            "result": result,
        }

    @classmethod
    def resume_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:
        prior = cls.fetch_campaign(
            access_token=access_token,
            external_account_id=external_account_id,
            external_id=external_id,
        )
        result = cls._partial_update(
            access_token=access_token,
            account_id=external_account_id,
            external_id=external_id,
            patch={"status": "ACTIVE"},
        )
        return {
            "ok": True,
            "prior_state": {"status": prior.get("status")},
            "result": result,
        }

    @classmethod
    def update_campaign_budget(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        external_id: str,
        daily_budget_cents: int,
    ) -> dict:
        if daily_budget_cents <= 0:
            raise ProviderError("daily_budget_cents must be positive.")
        prior = cls.fetch_campaign(
            access_token=access_token,
            external_account_id=external_account_id,
            external_id=external_id,
        )
        prior_daily = prior.get("dailyBudget") or {}
        currency = prior_daily.get("currencyCode") or "USD"
        amount_str = f"{(int(daily_budget_cents) / 100):.2f}"
        result = cls._partial_update(
            access_token=access_token,
            account_id=external_account_id,
            external_id=external_id,
            patch={
                "dailyBudget": {"amount": amount_str, "currencyCode": currency},
            },
        )
        prior_amount = prior_daily.get("amount")
        return {
            "ok": True,
            "prior_state": {
                "daily_budget_cents": (
                    int(round(float(prior_amount) * 100))
                    if prior_amount not in (None, "")
                    else None
                ),
                "currency": currency,
            },
            "result": result,
        }

    @classmethod
    def update_campaign_audience(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        external_id: str,
        targeting: dict,
    ) -> dict:
        prior = cls.fetch_campaign(
            access_token=access_token,
            external_account_id=external_account_id,
            external_id=external_id,
        )
        result = cls._partial_update(
            access_token=access_token,
            account_id=external_account_id,
            external_id=external_id,
            patch={"targetingCriteria": targeting},
        )
        return {
            "ok": True,
            "prior_state": {"targetingCriteria": prior.get("targetingCriteria")},
            "result": result,
        }

    @classmethod
    def create_campaign(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        payload: dict,
    ) -> dict:
        name = payload.get("name")
        if not name:
            raise ProviderError("LinkedIn create_campaign requires payload.name.")
        body = {
            "name": name,
            "type": payload.get("type", "TEXT_AD"),
            "objectiveType": payload.get("objective", "LEAD_GENERATION"),
            "costType": payload.get("cost_type", "CPM"),
            "status": payload.get("status", "DRAFT"),
            "account": f"urn:li:sponsoredAccount:{external_account_id}",
        }
        if payload.get("daily_budget_cents"):
            body["dailyBudget"] = {
                "amount": f"{(int(payload['daily_budget_cents']) / 100):.2f}",
                "currencyCode": payload.get("currency", "USD"),
            }
        if payload.get("targeting"):
            body["targetingCriteria"] = payload["targeting"]
        response = httpx.post(
            f"{LI_API}/adAccounts/{external_account_id}/adCampaigns",
            headers=cls._common_headers(access_token=access_token),
            json=body,
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"LinkedIn create campaign returned HTTP {response.status_code}: {response.text[:200]}"
            )
        # LinkedIn returns the new resource id in the X-LinkedIn-Id header.
        new_id = response.headers.get("X-LinkedIn-Id") or response.headers.get("x-linkedin-id")
        result_body: dict = {}
        if response.content:
            try:
                result_body = response.json()
            except ValueError:
                result_body = {}
        return {
            "ok": True,
            "external_id": new_id or result_body.get("id"),
            "external_account_id": external_account_id,
            "result": result_body or {"created": True, "id": new_id},
        }

    @classmethod
    def create_ad(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        ad_set_external_id: str,
        payload: dict,
    ) -> dict:
        # A LinkedIn "ad" is a creative that sponsors an existing share/post.
        # ad_set_external_id is the parent campaign id. We never fabricate a
        # post — a share URN must be supplied.
        del external_account_id
        reference = payload.get("share_urn") or payload.get("reference")
        if not reference:
            raise ProviderError(
                "LinkedIn create_ad needs a share/post URN (payload.share_urn) to "
                "sponsor; building a creative from copy alone isn't supported."
            )
        body = {
            "campaign": f"urn:li:sponsoredCampaign:{ad_set_external_id}",
            "content": {"reference": reference},
            "intendedStatus": payload.get("status", "DRAFT"),
        }
        response = httpx.post(
            f"{LI_API}/creatives",
            headers=cls._common_headers(access_token=access_token),
            json=body,
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"LinkedIn create creative returned HTTP {response.status_code}: {response.text[:200]}"
            )
        new_id = (
            response.headers.get("x-restli-id")
            or response.headers.get("x-linkedin-id")
            or response.headers.get("X-RestLi-Id")
        )
        result_body: dict = {}
        if response.content:
            try:
                result_body = response.json()
            except ValueError:
                result_body = {}
        return {
            "ok": True,
            "external_id": new_id or result_body.get("id"),
            "external_account_id": ad_set_external_id,
            "result": result_body or {"created": True, "id": new_id},
        }

    @classmethod
    def fetch_insights(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        external_id: str,
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        # LinkedIn analytics is addressed by campaign URN, not account.
        del external_account_id

        def _ymd(value: str) -> tuple[int, int, int]:
            y, m, d = value.split("-")
            return int(y), int(m), int(d)

        sy, sm, sd = _ymd(date_from)
        ey, em, ed = _ymd(date_to)
        # Rest.li wants the date tuple + List() literal un-encoded; only the
        # URN's colons are percent-encoded.
        date_range = (
            f"(start:(year:{sy},month:{sm},day:{sd}),"
            f"end:(year:{ey},month:{em},day:{ed}))"
        )
        encoded_urn = quote(f"urn:li:sponsoredCampaign:{external_id}", safe="")
        fields = (
            "impressions,clicks,costInLocalCurrency,"
            "externalWebsiteConversions,dateRange"
        )
        url = (
            f"{LI_API}/adAnalytics?q=analytics&pivot=CAMPAIGN&timeGranularity=DAILY"
            f"&dateRange={date_range}&campaigns=List({encoded_urn})&fields={fields}"
        )
        response = httpx.get(
            url, headers=cls._common_headers(access_token=access_token), timeout=30.0
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"LinkedIn adAnalytics returned HTTP {response.status_code}: {response.text[:200]}"
            )
        rows: list[dict] = []
        for el in response.json().get("elements", []):
            start = (el.get("dateRange") or {}).get("start") or {}
            try:
                on_date = date(
                    int(start["year"]), int(start["month"]), int(start["day"])
                ).isoformat()
            except (KeyError, ValueError, TypeError):
                continue
            rows.append(
                {
                    "date": on_date,
                    "impressions": int(float(el.get("impressions", 0) or 0)),
                    "clicks": int(float(el.get("clicks", 0) or 0)),
                    "spend_cents": round(float(el.get("costInLocalCurrency", 0) or 0) * 100),
                    "conversions": int(float(el.get("externalWebsiteConversions", 0) or 0)),
                    # LinkedIn's analytics finder doesn't expose revenue reliably.
                    "conversion_value_cents": 0,
                }
            )
        return rows

    @classmethod
    def _normalize(
        cls, raw: dict, *, account_id: str, currency: str | None
    ) -> CampaignData:
        # LinkedIn budget shape: {"dailyBudget": {"amount": "100.00", "currencyCode": "USD"}, ...}
        def _amount_to_cents(payload: dict | None) -> int | None:
            if not payload:
                return None
            amount = payload.get("amount")
            if amount is None:
                return None
            try:
                return int(round(float(amount) * 100))
            except (TypeError, ValueError):
                return None

        daily = raw.get("dailyBudget") or {}
        total = raw.get("totalBudget") or {}
        return CampaignData(
            external_id=str(raw.get("id")),
            name=raw.get("name") or "(unnamed)",
            status=LINKEDIN_STATUS_MAP.get(
                str(raw.get("status", "")).upper(), CampaignStatus.UNKNOWN
            ),
            external_account_id=account_id,
            objective=raw.get("objectiveType"),
            daily_budget_cents=_amount_to_cents(daily),
            lifetime_budget_cents=_amount_to_cents(total),
            currency=daily.get("currencyCode") or total.get("currencyCode") or currency,
            start_date=_parse_li_run_schedule(raw.get("runSchedule"), "start"),
            end_date=_parse_li_run_schedule(raw.get("runSchedule"), "end"),
            raw=raw,
        )
