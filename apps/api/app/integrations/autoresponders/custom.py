"""Generic HTTP autoresponder connector for the long-tail.

For any provider AdVanta doesn't ship a dedicated adapter for, a workspace can
point this connector at their own HTTP endpoints. Contacts are POSTed as JSON
to a configured ``push_url``; if a ``pull_url`` is configured, contacts can be
read back. Optional auth is sent as a header (default ``Authorization``) using
the connection's API key as the value, optionally prefixed by an auth scheme
(e.g. ``Bearer``).

This is intentionally unopinionated — it lets users integrate Mailchimp,
ActiveCampaign, ConvertKit, Klaviyo, Brevo, or a homegrown webhook without
waiting for a first-class adapter."""

from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

import httpx

from app.integrations.autoresponders.base import (
    AutoresponderAccountInfo,
    AutoresponderAdapter,
    AutoresponderError,
    ConfigField,
    Contact,
    PushResult,
)


class CustomWebhookAdapter(AutoresponderAdapter):
    provider_id: ClassVar[str] = "custom"
    display_name: ClassVar[str] = "Custom / Webhook"
    description: ClassVar[str] = (
        "Connect any autoresponder by URL. Contacts are POSTed as JSON to your "
        "endpoint; optionally read back from a pull URL. Use this for providers "
        "without a built-in adapter."
    )

    requires_api_key: ClassVar[bool] = False
    api_key_label: ClassVar[str] = "Auth token (optional)"
    api_key_help: ClassVar[str | None] = (
        "Sent as the auth header value. Leave blank for unauthenticated endpoints."
    )

    supports_audience_listing: ClassVar[bool] = False
    supports_contact_pull: ClassVar[bool] = True
    freeform_audience: ClassVar[bool] = True

    config_fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="push_url",
            label="Push URL",
            type="url",
            required=True,
            placeholder="https://hooks.example.com/contacts",
            help_text="Each contact is POSTed here as JSON.",
        ),
        ConfigField(
            key="pull_url",
            label="Pull URL (optional)",
            type="url",
            required=False,
            placeholder="https://api.example.com/contacts",
            help_text="GET endpoint returning a JSON array of contacts.",
        ),
        ConfigField(
            key="auth_header",
            label="Auth header name",
            required=False,
            placeholder="Authorization",
            help_text="Defaults to Authorization.",
        ),
        ConfigField(
            key="auth_scheme",
            label="Auth scheme",
            required=False,
            placeholder="Bearer",
            help_text="Prefix for the token, e.g. Bearer. Leave blank to send the raw token.",
        ),
    ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _auth_headers(api_key: str | None, config: dict) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            name = (config.get("auth_header") or "Authorization").strip() or "Authorization"
            scheme = (config.get("auth_scheme") or "").strip()
            headers[name] = f"{scheme} {api_key}".strip() if scheme else api_key
        return headers

    @staticmethod
    def _require_url(config: dict, key: str) -> str:
        url = (config.get(key) or "").strip()
        if not url:
            raise AutoresponderError(f"Custom connector is missing the {key} setting.")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise AutoresponderError(f"{key} must be a valid http(s) URL.")
        return url

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    @classmethod
    def verify(cls, *, api_key: str | None, config: dict) -> AutoresponderAccountInfo:
        push_url = cls._require_url(config, "push_url")
        host = urlparse(push_url).netloc
        pull_url = (config.get("pull_url") or "").strip()
        # Only the pull URL is safe to probe (a GET). A push endpoint would
        # receive a junk contact, so we don't call it during verification.
        if pull_url:
            try:
                resp = httpx.get(
                    pull_url,
                    headers=cls._auth_headers(api_key, config),
                    params={"limit": 1},
                    timeout=15.0,
                )
            except httpx.HTTPError as exc:
                raise AutoresponderError(f"Pull URL unreachable: {exc}") from exc
            if resp.status_code >= 400:
                raise AutoresponderError(
                    f"Pull URL returned HTTP {resp.status_code}."
                )
        return AutoresponderAccountInfo(account_id=None, display_name=host)

    @classmethod
    def push_contacts(
        cls,
        *,
        api_key: str | None,
        config: dict,
        audience_id: str | None,
        contacts: list[Contact],
    ) -> PushResult:
        push_url = cls._require_url(config, "push_url")
        headers = cls._auth_headers(api_key, config)
        succeeded = 0
        errors: list[str] = []
        for contact in contacts:
            if not contact.is_addressable():
                errors.append("Skipped contact with no email or phone.")
                continue
            body = {
                "email": contact.email,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "phone": contact.phone,
                "tags": contact.tags,
                "custom_fields": contact.custom_fields,
                "list": audience_id,
            }
            try:
                resp = httpx.post(push_url, headers=headers, json=body, timeout=20.0)
            except httpx.HTTPError as exc:
                errors.append(f"{contact.email or contact.phone}: {exc}")
                continue
            if resp.status_code >= 400:
                errors.append(
                    f"{contact.email or contact.phone}: HTTP {resp.status_code}"
                )
                continue
            succeeded += 1
        return PushResult(
            requested=len(contacts),
            succeeded=succeeded,
            failed=len(contacts) - succeeded,
            errors=errors[:20],
        )

    @classmethod
    def pull_contacts(
        cls,
        *,
        api_key: str | None,
        config: dict,
        audience_id: str | None,
        limit: int,
    ) -> list[Contact]:
        pull_url = (config.get("pull_url") or "").strip()
        if not pull_url:
            raise AutoresponderError(
                "This custom connection has no pull URL configured."
            )
        params: dict[str, object] = {"limit": max(1, min(limit, 1000))}
        if audience_id:
            params["list"] = audience_id
        try:
            resp = httpx.get(
                pull_url,
                headers=cls._auth_headers(api_key, config),
                params=params,
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            raise AutoresponderError(f"Pull URL unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise AutoresponderError(f"Pull URL returned HTTP {resp.status_code}.")
        payload = resp.json()
        rows = payload.get("contacts", []) if isinstance(payload, dict) else payload
        out: list[Contact] = []
        for raw in rows if isinstance(rows, list) else []:
            if not isinstance(raw, dict):
                continue
            out.append(
                Contact(
                    email=raw.get("email"),
                    first_name=raw.get("first_name") or raw.get("firstName"),
                    last_name=raw.get("last_name") or raw.get("lastName"),
                    phone=raw.get("phone"),
                    tags=list(raw.get("tags") or []),
                    raw=raw,
                )
            )
        return out
