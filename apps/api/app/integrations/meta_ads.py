from datetime import date, datetime, timezone
from typing import ClassVar

import httpx

from app.integrations.base import (
    BaseProvider,
    CampaignData,
    ProviderAccountInfo,
    ProviderError,
)
from app.models.campaign import CampaignStatus

GRAPH = "https://graph.facebook.com/v19.0"

META_STATUS_MAP = {
    "ACTIVE": CampaignStatus.ACTIVE,
    "PAUSED": CampaignStatus.PAUSED,
    "DELETED": CampaignStatus.ENDED,
    "ARCHIVED": CampaignStatus.ARCHIVED,
}


def _parse_meta_datetime(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).date()
    except ValueError:
        return None


class MetaAdsProvider(BaseProvider):
    provider_id: ClassVar[str] = "meta_ads"
    display_name: ClassVar[str] = "Meta Ads"
    description: ClassVar[str] = (
        "Sync campaigns and conversions from Facebook + Instagram ad accounts."
    )

    auth_url: ClassVar[str] = "https://www.facebook.com/v19.0/dialog/oauth"
    token_url: ClassVar[str] = f"{GRAPH}/oauth/access_token"

    scopes: ClassVar[list[str]] = [
        "ads_management",
        "ads_read",
        "business_management",
    ]
    # `ads_management` is the gate Meta enforces for any outbound write
    # (creating ads, pausing campaigns, updating budgets). `ads_read` alone
    # is read-only.
    write_scopes: ClassVar[list[str]] = ["ads_management"]

    client_id_env: ClassVar[str] = "META_APP_ID"
    client_secret_env: ClassVar[str] = "META_APP_SECRET"

    @classmethod
    def fetch_account_info(cls, *, access_token: str) -> ProviderAccountInfo:
        response = httpx.get(
            f"{GRAPH}/me",
            params={"fields": "id,name", "access_token": access_token},
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Meta `/me` returned HTTP {response.status_code}.")
        body = response.json()
        return ProviderAccountInfo(
            provider_account_id=body.get("id"),
            display_name=body.get("name"),
        )

    @classmethod
    def sync_campaigns(cls, *, access_token: str) -> list[CampaignData]:
        accounts = cls._fetch_ad_accounts(access_token=access_token)
        out: list[CampaignData] = []
        for account in accounts:
            account_id = account.get("id")
            currency = account.get("currency")
            if not account_id:
                continue
            try:
                campaigns = cls._fetch_campaigns(
                    access_token=access_token, account_id=account_id
                )
            except ProviderError:
                # Skip just this account — do not fail the entire sync.
                continue
            for raw in campaigns:
                out.append(cls._normalize(raw, account_id=account_id, currency=currency))
        return out

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @classmethod
    def _fetch_ad_accounts(cls, *, access_token: str) -> list[dict]:
        response = httpx.get(
            f"{GRAPH}/me/adaccounts",
            params={
                "fields": "id,name,currency",
                "access_token": access_token,
                "limit": 50,
            },
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"Meta `/me/adaccounts` returned HTTP {response.status_code}."
            )
        return response.json().get("data", [])

    @classmethod
    def _fetch_campaigns(cls, *, access_token: str, account_id: str) -> list[dict]:
        response = httpx.get(
            f"{GRAPH}/{account_id}/campaigns",
            params={
                "fields": "id,name,status,objective,daily_budget,lifetime_budget,start_time,stop_time",
                "access_token": access_token,
                "limit": 100,
            },
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"Meta `/{account_id}/campaigns` returned HTTP {response.status_code}."
            )
        return response.json().get("data", [])

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    @classmethod
    def fetch_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:
        # external_account_id is unused for the Graph endpoint, but we keep the
        # signature consistent across providers.
        del external_account_id
        response = httpx.get(
            f"{GRAPH}/{external_id}",
            params={
                "fields": "id,name,status,objective,daily_budget,lifetime_budget,targeting",
                "access_token": access_token,
            },
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"Meta GET /{external_id} returned HTTP {response.status_code}."
            )
        return response.json()

    @classmethod
    def _post_campaign_update(
        cls, *, access_token: str, external_id: str, fields: dict
    ) -> dict:
        response = httpx.post(
            f"{GRAPH}/{external_id}",
            data={"access_token": access_token, **fields},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"Meta POST /{external_id} returned HTTP {response.status_code}: {response.text[:200]}"
            )
        return response.json()

    @classmethod
    def pause_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:
        prior = cls.fetch_campaign(
            access_token=access_token,
            external_account_id=external_account_id,
            external_id=external_id,
        )
        result = cls._post_campaign_update(
            access_token=access_token, external_id=external_id, fields={"status": "PAUSED"}
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
        result = cls._post_campaign_update(
            access_token=access_token, external_id=external_id, fields={"status": "ACTIVE"}
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
        result = cls._post_campaign_update(
            access_token=access_token,
            external_id=external_id,
            fields={"daily_budget": str(int(daily_budget_cents))},
        )
        prior_daily = prior.get("daily_budget")
        return {
            "ok": True,
            "prior_state": {
                "daily_budget_cents": (
                    int(prior_daily) if prior_daily not in (None, "") else None
                ),
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
        # Meta targeting must be applied at the ad-set level. We accept either
        # a single ad_set_id + targeting dict, or a list of {ad_set_id, targeting}.
        items = (
            targeting.get("ad_sets")
            if isinstance(targeting.get("ad_sets"), list)
            else [
                {
                    "ad_set_id": targeting.get("ad_set_id"),
                    "targeting": targeting.get("targeting"),
                }
            ]
        )
        results = []
        priors = []
        for item in items:
            ad_set_id = item.get("ad_set_id")
            spec = item.get("targeting")
            if not ad_set_id or not spec:
                raise ProviderError(
                    "Meta audience update needs ad_set_id and targeting per item."
                )
            prior_resp = httpx.get(
                f"{GRAPH}/{ad_set_id}",
                params={"fields": "targeting", "access_token": access_token},
                timeout=15.0,
            )
            priors.append(
                {
                    "ad_set_id": ad_set_id,
                    "targeting": (
                        prior_resp.json().get("targeting")
                        if prior_resp.status_code < 400
                        else None
                    ),
                }
            )
            import json

            results.append(
                cls._post_campaign_update(
                    access_token=access_token,
                    external_id=ad_set_id,
                    fields={"targeting": json.dumps(spec)},
                )
            )
        return {
            "ok": True,
            "prior_state": {"ad_sets": priors},
            "result": {"ad_sets": results},
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
        objective = payload.get("objective", "OUTCOME_LEADS")
        if not name:
            raise ProviderError("Meta create_campaign requires payload.name.")
        # Meta ad accounts are addressed as "act_<id>" for the campaigns edge.
        account_path = (
            external_account_id
            if str(external_account_id).startswith("act_")
            else f"act_{external_account_id}"
        )
        special_categories = payload.get("special_ad_categories") or []
        import json as _json

        response = httpx.post(
            f"{GRAPH}/{account_path}/campaigns",
            data={
                "access_token": access_token,
                "name": name,
                "objective": objective,
                "status": payload.get("status", "PAUSED"),
                "special_ad_categories": _json.dumps(special_categories),
            },
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"Meta create campaign returned HTTP {response.status_code}: {response.text[:200]}"
            )
        body = response.json()
        return {
            "ok": True,
            "external_id": body.get("id"),
            "external_account_id": external_account_id,
            "result": body,
        }

    @classmethod
    def _normalize(cls, raw: dict, *, account_id: str, currency: str | None) -> CampaignData:
        # Meta returns budget in the account-currency's smallest unit (cents for USD).
        def _to_cents(value: object) -> int | None:
            if value in (None, "", 0):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        return CampaignData(
            external_id=str(raw.get("id")),
            name=raw.get("name") or "(unnamed)",
            status=META_STATUS_MAP.get(
                str(raw.get("status", "")).upper(), CampaignStatus.UNKNOWN
            ),
            external_account_id=account_id,
            objective=raw.get("objective"),
            daily_budget_cents=_to_cents(raw.get("daily_budget")),
            lifetime_budget_cents=_to_cents(raw.get("lifetime_budget")),
            currency=currency,
            start_date=_parse_meta_datetime(raw.get("start_time")),
            end_date=_parse_meta_datetime(raw.get("stop_time")),
            raw=raw,
        )
