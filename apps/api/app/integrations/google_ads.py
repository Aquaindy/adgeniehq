import os
from datetime import date, datetime
from typing import ClassVar

import httpx

from app.integrations.base import (
    CampaignData,
    ProviderError,
    ProviderNotConfiguredError,
)
from app.integrations.google_base import GoogleProviderBase
from app.models.campaign import CampaignStatus

ADS_API = "https://googleads.googleapis.com/v17"

GOOGLE_STATUS_MAP = {
    "ENABLED": CampaignStatus.ACTIVE,
    "PAUSED": CampaignStatus.PAUSED,
    "REMOVED": CampaignStatus.ENDED,
    "UNKNOWN": CampaignStatus.UNKNOWN,
    "UNSPECIFIED": CampaignStatus.UNKNOWN,
}


def _parse_google_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


class GoogleAdsProvider(GoogleProviderBase):
    provider_id: ClassVar[str] = "google_ads"
    display_name: ClassVar[str] = "Google Ads"
    description: ClassVar[str] = (
        "Sync campaigns and conversions from Google Ads. Requires a developer token."
    )

    scopes: ClassVar[list[str]] = [
        *GoogleProviderBase.USERINFO_SCOPES,
        "https://www.googleapis.com/auth/adwords",
    ]
    # Required for any outbound campaign / budget mutation. Google Ads exposes
    # a single `adwords` scope that covers both read + write — declare it
    # explicitly so `_resolve_connection` refuses to write when a workspace
    # was somehow connected without it.
    write_scopes: ClassVar[list[str]] = [
        "https://www.googleapis.com/auth/adwords",
    ]

    @classmethod
    def _developer_token(cls) -> str:
        token = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
        if not token:
            raise ProviderNotConfiguredError(
                "Google Ads sync requires GOOGLE_ADS_DEVELOPER_TOKEN. "
                "Apply for one at https://developers.google.com/google-ads/api."
            )
        return token

    @classmethod
    def _login_customer_id(cls) -> str | None:
        value = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").strip()
        return value.replace("-", "") or None

    @classmethod
    def sync_campaigns(cls, *, access_token: str) -> list[CampaignData]:
        developer_token = cls._developer_token()
        customer_ids = cls._fetch_accessible_customers(
            access_token=access_token, developer_token=developer_token
        )

        results: list[CampaignData] = []
        for customer_id in customer_ids:
            try:
                rows = cls._search_campaigns(
                    access_token=access_token,
                    developer_token=developer_token,
                    customer_id=customer_id,
                )
            except ProviderError:
                # Skip individual customer errors — surface in sync_log only.
                continue
            for row in rows:
                results.append(cls._normalize(row, customer_id=customer_id))
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @classmethod
    def _common_headers(cls, *, access_token: str, developer_token: str) -> dict:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": developer_token,
            "Content-Type": "application/json",
        }
        login_id = cls._login_customer_id()
        if login_id:
            headers["login-customer-id"] = login_id
        return headers

    @classmethod
    def _fetch_accessible_customers(
        cls, *, access_token: str, developer_token: str
    ) -> list[str]:
        response = httpx.get(
            f"{ADS_API}/customers:listAccessibleCustomers",
            headers=cls._common_headers(
                access_token=access_token, developer_token=developer_token
            ),
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"Google Ads listAccessibleCustomers returned HTTP {response.status_code}."
            )
        # Response shape: {"resourceNames": ["customers/1234567890", ...]}
        names = response.json().get("resourceNames", [])
        return [n.split("/", 1)[1] for n in names if "/" in n]

    @classmethod
    def _search_campaigns(
        cls, *, access_token: str, developer_token: str, customer_id: str
    ) -> list[dict]:
        query = (
            "SELECT campaign.id, campaign.name, campaign.status, "
            "campaign.advertising_channel_type, campaign.start_date, campaign.end_date, "
            "campaign_budget.amount_micros, campaign_budget.delivery_method "
            "FROM campaign LIMIT 500"
        )
        response = httpx.post(
            f"{ADS_API}/customers/{customer_id}/googleAds:search",
            headers=cls._common_headers(
                access_token=access_token, developer_token=developer_token
            ),
            json={"query": query},
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"Google Ads search returned HTTP {response.status_code} for customer {customer_id}."
            )
        return response.json().get("results", [])

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    @classmethod
    def _campaign_resource(cls, customer_id: str, external_id: str) -> str:
        return f"customers/{customer_id}/campaigns/{external_id}"

    @classmethod
    def _budget_resource(cls, customer_id: str, budget_id: str) -> str:
        return f"customers/{customer_id}/campaignBudgets/{budget_id}"

    @classmethod
    def _post_mutate(
        cls,
        *,
        access_token: str,
        customer_id: str,
        operations: list[dict],
        endpoint: str,
    ) -> dict:
        developer_token = cls._developer_token()
        response = httpx.post(
            f"{ADS_API}/customers/{customer_id}/{endpoint}",
            headers=cls._common_headers(
                access_token=access_token, developer_token=developer_token
            ),
            json={"operations": operations},
            timeout=30.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"Google Ads {endpoint} returned HTTP {response.status_code}: {response.text[:200]}"
            )
        return response.json()

    @classmethod
    def fetch_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:
        developer_token = cls._developer_token()
        query = (
            f"SELECT campaign.id, campaign.name, campaign.status, "
            f"campaign.advertising_channel_type, campaign.campaign_budget, "
            f"campaign_budget.id, campaign_budget.amount_micros "
            f"FROM campaign WHERE campaign.id = {external_id}"
        )
        response = httpx.post(
            f"{ADS_API}/customers/{external_account_id}/googleAds:search",
            headers=cls._common_headers(
                access_token=access_token, developer_token=developer_token
            ),
            json={"query": query},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"Google Ads campaign fetch returned HTTP {response.status_code}."
            )
        rows = response.json().get("results") or []
        if not rows:
            raise ProviderError(f"Google Ads campaign {external_id} not found.")
        row = rows[0]
        campaign = row.get("campaign") or {}
        budget = row.get("campaignBudget") or {}
        return {
            "id": str(campaign.get("id")),
            "name": campaign.get("name"),
            "status": campaign.get("status"),
            "budget_resource_name": campaign.get("campaignBudget"),
            "budget_id": str(budget.get("id")) if budget.get("id") else None,
            "budget_amount_micros": budget.get("amountMicros"),
            "raw": row,
        }

    @classmethod
    def _set_campaign_status(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        external_id: str,
        status: str,
    ) -> dict:
        prior = cls.fetch_campaign(
            access_token=access_token,
            external_account_id=external_account_id,
            external_id=external_id,
        )
        result = cls._post_mutate(
            access_token=access_token,
            customer_id=external_account_id,
            endpoint="campaigns:mutate",
            operations=[
                {
                    "update": {
                        "resourceName": cls._campaign_resource(
                            external_account_id, external_id
                        ),
                        "status": status,
                    },
                    "updateMask": "status",
                }
            ],
        )
        return {
            "ok": True,
            "prior_state": {"status": prior.get("status")},
            "result": result,
        }

    @classmethod
    def pause_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:
        return cls._set_campaign_status(
            access_token=access_token,
            external_account_id=external_account_id,
            external_id=external_id,
            status="PAUSED",
        )

    @classmethod
    def resume_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:
        return cls._set_campaign_status(
            access_token=access_token,
            external_account_id=external_account_id,
            external_id=external_id,
            status="ENABLED",
        )

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
        budget_id = prior.get("budget_id")
        if not budget_id:
            raise ProviderError(
                f"Campaign {external_id} has no campaign_budget — cannot update budget."
            )
        amount_micros = int(daily_budget_cents) * 10_000  # cents → micros
        result = cls._post_mutate(
            access_token=access_token,
            customer_id=external_account_id,
            endpoint="campaignBudgets:mutate",
            operations=[
                {
                    "update": {
                        "resourceName": cls._budget_resource(
                            external_account_id, budget_id
                        ),
                        "amountMicros": str(amount_micros),
                    },
                    "updateMask": "amount_micros",
                }
            ],
        )
        return {
            "ok": True,
            "prior_state": {
                "daily_budget_cents": (
                    int(prior["budget_amount_micros"]) // 10_000
                    if prior.get("budget_amount_micros") is not None
                    else None
                ),
                "budget_id": budget_id,
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
        # Google Ads targeting lives on ad_groups via ad_group_criterion.
        # Each op is: {"create": {...criterion fields...}} or {"remove": "<resource name>"}.
        ops = targeting.get("operations")
        if not isinstance(ops, list) or not ops:
            raise ProviderError(
                "Google Ads audience update requires targeting.operations list."
            )

        # Track what each op type does so we can construct a real revert plan
        # later. `removed_resource_names` are recorded for diagnostics — we
        # cannot restore a removed criterion without a pre-mutation snapshot,
        # so revert of a removal isn't supported and the revert builder will
        # fail loudly rather than silently no-op.
        removed_resource_names = [
            op["remove"] for op in ops if "remove" in op and isinstance(op["remove"], str)
        ]

        result = cls._post_mutate(
            access_token=access_token,
            customer_id=external_account_id,
            endpoint="adGroupCriteria:mutate",
            operations=ops,
        )

        # Pull resourceNames for criteria the mutate just *created*. Reverting
        # a create is straightforward: send a remove for each.
        created_resource_names: list[str] = []
        for entry in (result.get("results") or []):
            rn = entry.get("resourceName")
            if isinstance(rn, str) and "/adGroupCriteria/" in rn:
                created_resource_names.append(rn)

        return {
            "ok": True,
            "prior_state": {
                "operations": ops,
                "created_resource_names": created_resource_names,
                "removed_resource_names": removed_resource_names,
            },
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
        # Google Ads requires a campaign_budget first, then a campaign that
        # references it. We do both in two calls.
        name = payload.get("name")
        daily_budget_cents = payload.get("daily_budget_cents")
        channel = payload.get("advertising_channel_type", "SEARCH")
        if not name or not daily_budget_cents:
            raise ProviderError(
                "Google Ads create_campaign needs payload.name and payload.daily_budget_cents."
            )
        budget_amount_micros = int(daily_budget_cents) * 10_000
        budget_resp = cls._post_mutate(
            access_token=access_token,
            customer_id=external_account_id,
            endpoint="campaignBudgets:mutate",
            operations=[
                {
                    "create": {
                        "name": f"{name} budget",
                        "amountMicros": str(budget_amount_micros),
                        "deliveryMethod": "STANDARD",
                    }
                }
            ],
        )
        budget_resource = (
            budget_resp.get("results", [{}])[0].get("resourceName") or ""
        )
        if not budget_resource:
            raise ProviderError("Google Ads budget creation returned no resourceName.")

        campaign_resp = cls._post_mutate(
            access_token=access_token,
            customer_id=external_account_id,
            endpoint="campaigns:mutate",
            operations=[
                {
                    "create": {
                        "name": name,
                        "advertisingChannelType": channel,
                        "status": payload.get("status", "PAUSED"),
                        "campaignBudget": budget_resource,
                        "manualCpc": {"enhancedCpcEnabled": True},
                    }
                }
            ],
        )
        new_resource = (
            campaign_resp.get("results", [{}])[0].get("resourceName") or ""
        )
        new_id = new_resource.split("/")[-1] if new_resource else None
        return {
            "ok": True,
            "external_id": new_id,
            "external_account_id": external_account_id,
            "result": campaign_resp,
        }

    @classmethod
    def _normalize(cls, row: dict, *, customer_id: str) -> CampaignData:
        campaign = row.get("campaign", {})
        budget = row.get("campaignBudget", {})
        amount_micros = budget.get("amountMicros")
        try:
            daily_cents = int(amount_micros) // 10_000 if amount_micros is not None else None
        except (TypeError, ValueError):
            daily_cents = None

        return CampaignData(
            external_id=str(campaign.get("id")),
            name=campaign.get("name") or "(unnamed)",
            status=GOOGLE_STATUS_MAP.get(
                str(campaign.get("status", "")).upper(), CampaignStatus.UNKNOWN
            ),
            external_account_id=customer_id,
            objective=campaign.get("advertisingChannelType"),
            daily_budget_cents=daily_cents,
            lifetime_budget_cents=None,
            currency="USD",  # Google Ads micros are always denominated in account currency
            start_date=_parse_google_date(campaign.get("startDate")),
            end_date=_parse_google_date(campaign.get("endDate")),
            raw=row,
        )
