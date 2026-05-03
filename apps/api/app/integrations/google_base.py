"""Shared OAuth wiring for Google products (Ads, Analytics, Search Console)."""

from typing import ClassVar

import httpx

from app.integrations.base import BaseProvider, ProviderAccountInfo, ProviderError

USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v1/userinfo"


class GoogleProviderBase(BaseProvider):
    auth_url: ClassVar[str] = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url: ClassVar[str] = "https://oauth2.googleapis.com/token"

    # All Google providers share these env vars.
    client_id_env: ClassVar[str] = "GOOGLE_CLIENT_ID"
    client_secret_env: ClassVar[str] = "GOOGLE_CLIENT_SECRET"

    # `access_type=offline` + `prompt=consent` are what coax Google into returning a refresh token.
    extra_auth_params: ClassVar[dict[str, str]] = {
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    }

    USERINFO_SCOPES: ClassVar[list[str]] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    @classmethod
    def fetch_account_info(cls, *, access_token: str) -> ProviderAccountInfo:
        response = httpx.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )
        if response.status_code >= 400:
            raise ProviderError(
                f"{cls.display_name} userinfo returned HTTP {response.status_code}.",
            )
        body = response.json()
        return ProviderAccountInfo(
            provider_account_id=body.get("id") or body.get("sub"),
            display_name=body.get("name") or body.get("email"),
        )
