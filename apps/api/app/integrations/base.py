"""OAuth 2.0 provider abstraction shared by every external integration.

Each provider exposes a tiny surface — enough to build an authorization URL,
exchange an authorization code for tokens, refresh access tokens, and verify
a connection by fetching basic account info."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import ClassVar
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.models.campaign import CampaignStatus


class ProviderNotConfiguredError(AdVantaError):
    status_code = 503
    code = "provider_not_configured"


class ProviderError(AdVantaError):
    status_code = 502
    code = "provider_error"


class ProviderNotImplementedError(AdVantaError):
    status_code = 501
    code = "provider_not_implemented"


@dataclass
class ProviderTokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scopes: list[str] | None
    raw: dict | None = None


@dataclass
class ProviderAccountInfo:
    provider_account_id: str | None
    display_name: str | None


@dataclass
class CampaignData:
    """Normalized campaign record returned by provider.sync_campaigns()."""

    external_id: str
    name: str
    status: CampaignStatus
    external_account_id: str | None = None
    objective: str | None = None
    daily_budget_cents: int | None = None
    lifetime_budget_cents: int | None = None
    currency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    raw: dict = field(default_factory=dict)


class BaseProvider:
    """OAuth 2.0 provider interface.

    Subclasses set the class-level configuration; behavior comes from the
    methods below."""

    provider_id: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str]

    auth_url: ClassVar[str]
    token_url: ClassVar[str]
    scopes: ClassVar[list[str]]
    # Subset of `scopes` that are required for outbound writes (campaigns,
    # budgets, creatives). When empty, all `scopes` are treated as needed for
    # writes. Override per provider when read vs write scopes differ.
    write_scopes: ClassVar[list[str]] = []

    client_id_env: ClassVar[str]
    client_secret_env: ClassVar[str]

    # Some providers (Google) need extra params on the auth URL to mint a refresh token.
    extra_auth_params: ClassVar[dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @classmethod
    def credentials(cls) -> tuple[str, str]:
        client_id = os.getenv(cls.client_id_env, "").strip()
        client_secret = os.getenv(cls.client_secret_env, "").strip()
        if not client_id or not client_secret:
            raise ProviderNotConfiguredError(
                f"{cls.display_name} is not configured. Set {cls.client_id_env} "
                f"and {cls.client_secret_env} in your environment.",
            )
        return client_id, client_secret

    @classmethod
    def is_configured(cls) -> bool:
        try:
            cls.credentials()
            return True
        except ProviderNotConfiguredError:
            return False

    @classmethod
    def callback_url(cls) -> str:
        base = settings.backend_url.rstrip("/")
        return f"{base}{settings.api_v1_prefix}/integrations/{cls.provider_id}/callback"

    # ------------------------------------------------------------------
    # OAuth flow
    # ------------------------------------------------------------------

    @classmethod
    def scopes_for_mode(cls, scope_mode: str) -> list[str]:
        """Scopes to request at connect-time. `scope_mode="read"` drops the
        write scopes (so the workspace connects read-only); `"write"` requests
        the full set including writes. Providers with no declared write_scopes
        always request all scopes."""
        if scope_mode == "read" and cls.write_scopes:
            write = set(cls.write_scopes)
            return [s for s in cls.scopes if s not in write]
        return list(cls.scopes)

    @classmethod
    def build_authorization_url(cls, *, state: str, scope_mode: str = "write") -> str:
        client_id, _ = cls.credentials()
        params = {
            "client_id": client_id,
            "redirect_uri": cls.callback_url(),
            "response_type": "code",
            "scope": " ".join(cls.scopes_for_mode(scope_mode)),
            "state": state,
        }
        params.update(cls.extra_auth_params)
        return f"{cls.auth_url}?{urlencode(params)}"

    @classmethod
    def exchange_code(cls, *, code: str) -> ProviderTokens:
        client_id, client_secret = cls.credentials()
        try:
            response = httpx.post(
                cls.token_url,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": cls.callback_url(),
                    "grant_type": "authorization_code",
                },
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{cls.display_name} token exchange failed: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(
                f"{cls.display_name} token exchange returned HTTP {response.status_code}.",
            )
        return cls._parse_token_response(response.json())

    @classmethod
    def refresh_access_token(cls, *, refresh_token: str) -> ProviderTokens:
        client_id, client_secret = cls.credentials()
        response = httpx.post(
            cls.token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"{cls.display_name} token refresh returned HTTP {response.status_code}."
            )
        return cls._parse_token_response(response.json())

    @classmethod
    def fetch_account_info(cls, *, access_token: str) -> ProviderAccountInfo:  # pragma: no cover — provider-specific
        return ProviderAccountInfo(provider_account_id=None, display_name=None)

    # ------------------------------------------------------------------
    # Campaign sync — overridden by ad-platform providers (Google/Meta/LinkedIn Ads)
    # ------------------------------------------------------------------

    @classmethod
    def sync_campaigns(cls, *, access_token: str) -> list[CampaignData]:  # pragma: no cover — provider-specific
        raise ProviderNotImplementedError(
            f"{cls.display_name} does not expose a campaign sync."
        )

    # ------------------------------------------------------------------
    # Outbound writes — overridden by ad-platform providers.
    # Each method returns a dict that becomes the execution.result;
    # mutating methods should also return enough to reconstruct prior_state
    # so the change can be reverted.
    # ------------------------------------------------------------------

    @classmethod
    def fetch_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:  # pragma: no cover — provider-specific
        raise ProviderNotImplementedError(
            f"{cls.display_name} does not expose a campaign read."
        )

    @classmethod
    def pause_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:  # pragma: no cover — provider-specific
        raise ProviderNotImplementedError(
            f"{cls.display_name} does not support pause."
        )

    @classmethod
    def resume_campaign(
        cls, *, access_token: str, external_account_id: str, external_id: str
    ) -> dict:  # pragma: no cover — provider-specific
        raise ProviderNotImplementedError(
            f"{cls.display_name} does not support resume."
        )

    @classmethod
    def update_campaign_budget(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        external_id: str,
        daily_budget_cents: int,
    ) -> dict:  # pragma: no cover — provider-specific
        raise ProviderNotImplementedError(
            f"{cls.display_name} does not support budget update."
        )

    @classmethod
    def update_campaign_audience(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        external_id: str,
        targeting: dict,
    ) -> dict:  # pragma: no cover — provider-specific
        raise ProviderNotImplementedError(
            f"{cls.display_name} does not support audience update."
        )

    @classmethod
    def create_campaign(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        payload: dict,
    ) -> dict:  # pragma: no cover — provider-specific
        raise ProviderNotImplementedError(
            f"{cls.display_name} does not support campaign creation."
        )

    @classmethod
    def create_ad_set(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        campaign_external_id: str,
        payload: dict,
    ) -> dict:  # pragma: no cover — provider-specific
        """Create an ad set / ad group under an existing campaign. Returns a
        dict carrying `external_id` (the new platform object id). Launches the
        object paused/draft for safety."""
        raise ProviderNotImplementedError(
            f"{cls.display_name} does not support ad-set creation yet."
        )

    @classmethod
    def create_ad(
        cls,
        *,
        access_token: str,
        external_account_id: str,
        ad_set_external_id: str,
        payload: dict,
    ) -> dict:  # pragma: no cover — provider-specific
        """Create an ad under an existing ad set / ad group. Returns a dict
        carrying `external_id` (the new platform object id)."""
        raise ProviderNotImplementedError(
            f"{cls.display_name} does not support ad creation yet."
        )

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
        """Return daily performance rows for a campaign over [date_from, date_to].

        Each row: {date (YYYY-MM-DD), impressions, clicks, spend_cents,
        conversions, conversion_value_cents}. Default is empty — providers
        override with the real insights/analytics call. Returning [] (rather
        than raising) lets the sync run cleanly for not-yet-wired platforms."""
        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _parse_token_response(cls, body: dict) -> ProviderTokens:
        access = body.get("access_token")
        if not access:
            raise ProviderError(f"{cls.display_name} returned no access_token.")
        expires_at = None
        if (expires_in := body.get("expires_in")) is not None:
            try:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            except (TypeError, ValueError):
                expires_at = None
        scope = body.get("scope")
        scopes = scope.split() if isinstance(scope, str) and scope else None
        return ProviderTokens(
            access_token=access,
            refresh_token=body.get("refresh_token"),
            expires_at=expires_at,
            scopes=scopes,
            raw={k: v for k, v in body.items() if k not in {"access_token", "refresh_token"}},
        )
