"""GetResponse adapter.

GetResponse authenticates with an API key sent as ``X-Auth-Token: api-key <KEY>``.
Unlike Omnisend it has a real list API — lists are called *campaigns* — so
audiences can be enumerated and selected from a dropdown.

Docs: https://apidocs.getresponse.com/v3
"""

from __future__ import annotations

from typing import ClassVar

import httpx

from app.integrations.autoresponders.base import (
    Audience,
    AutoresponderAccountInfo,
    AutoresponderAdapter,
    AutoresponderAuthError,
    AutoresponderError,
    Contact,
    PushResult,
)

API_BASE = "https://api.getresponse.com/v3"


def _headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        raise AutoresponderAuthError("GetResponse requires an API key.")
    return {
        "X-Auth-Token": f"api-key {api_key}",
        "Content-Type": "application/json",
    }


def _raise_for_auth(resp: httpx.Response) -> None:
    if resp.status_code in (401, 403):
        raise AutoresponderAuthError(
            f"GetResponse rejected the API key (HTTP {resp.status_code}). "
            "Create one under Integrations & API → API."
        )


class GetResponseAdapter(AutoresponderAdapter):
    provider_id: ClassVar[str] = "getresponse"
    display_name: ClassVar[str] = "GetResponse"
    description: ClassVar[str] = (
        "Sync contacts to GetResponse lists (campaigns). Supports list selection "
        "and pulling subscribers back into AdVanta."
    )

    api_key_label: ClassVar[str] = "GetResponse API key"
    api_key_help: ClassVar[str | None] = "Menu → Integrations & API → API → Generate API key."

    supports_audience_listing: ClassVar[bool] = True
    supports_contact_pull: ClassVar[bool] = True
    freeform_audience: ClassVar[bool] = False
    docs_url: ClassVar[str | None] = "https://apidocs.getresponse.com/v3"

    @classmethod
    def verify(cls, *, api_key: str | None, config: dict) -> AutoresponderAccountInfo:
        try:
            resp = httpx.get(
                f"{API_BASE}/accounts", headers=_headers(api_key), timeout=15.0
            )
        except httpx.HTTPError as exc:
            raise AutoresponderError(f"Could not reach GetResponse: {exc}") from exc
        _raise_for_auth(resp)
        if resp.status_code >= 400:
            raise AutoresponderError(
                f"GetResponse verification returned HTTP {resp.status_code}."
            )
        body = resp.json() if resp.content else {}
        name = body.get("companyName") or body.get("email") or "GetResponse account"
        return AutoresponderAccountInfo(
            account_id=str(body.get("accountId") or "") or None,
            display_name=name,
        )

    @classmethod
    def list_audiences(cls, *, api_key: str | None, config: dict) -> list[Audience]:
        try:
            resp = httpx.get(
                f"{API_BASE}/campaigns",
                headers=_headers(api_key),
                params={"perPage": 100},
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            raise AutoresponderError(f"Could not reach GetResponse: {exc}") from exc
        _raise_for_auth(resp)
        if resp.status_code >= 400:
            raise AutoresponderError(
                f"GetResponse list fetch returned HTTP {resp.status_code}."
            )
        out: list[Audience] = []
        for raw in resp.json():
            cid = raw.get("campaignId")
            if not cid:
                continue
            out.append(
                Audience(external_id=str(cid), name=raw.get("name") or str(cid), raw=raw)
            )
        return out

    @classmethod
    def push_contacts(
        cls,
        *,
        api_key: str | None,
        config: dict,
        audience_id: str | None,
        contacts: list[Contact],
    ) -> PushResult:
        if not audience_id:
            raise AutoresponderError("GetResponse push requires a list (campaign) id.")
        headers = _headers(api_key)
        succeeded = 0
        errors: list[str] = []
        for contact in contacts:
            if not contact.email:
                errors.append("Skipped contact with no email (GetResponse requires email).")
                continue
            body: dict = {
                "email": contact.email,
                "campaign": {"campaignId": audience_id},
            }
            name = " ".join(p for p in (contact.first_name, contact.last_name) if p).strip()
            if name:
                body["name"] = name
            if contact.custom_fields:
                body["customFieldValues"] = contact.custom_fields
            try:
                resp = httpx.post(
                    f"{API_BASE}/contacts", headers=headers, json=body, timeout=20.0
                )
            except httpx.HTTPError as exc:
                errors.append(f"{contact.email}: {exc}")
                continue
            _raise_for_auth(resp)
            # GetResponse returns 202 Accepted (queued import) on success.
            if resp.status_code >= 400:
                errors.append(f"{contact.email}: HTTP {resp.status_code} {resp.text[:120]}")
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
        headers = _headers(api_key)
        params: dict[str, object] = {"perPage": max(1, min(limit, 1000))}
        if audience_id:
            params["query[campaignId]"] = audience_id
        try:
            resp = httpx.get(
                f"{API_BASE}/contacts", headers=headers, params=params, timeout=20.0
            )
        except httpx.HTTPError as exc:
            raise AutoresponderError(f"Could not reach GetResponse: {exc}") from exc
        _raise_for_auth(resp)
        if resp.status_code >= 400:
            raise AutoresponderError(
                f"GetResponse contact pull returned HTTP {resp.status_code}."
            )
        out: list[Contact] = []
        for raw in resp.json():
            name = (raw.get("name") or "").strip()
            first, _, last = name.partition(" ")
            out.append(
                Contact(
                    email=raw.get("email"),
                    first_name=first or None,
                    last_name=last or None,
                    raw=raw,
                )
            )
        return out
