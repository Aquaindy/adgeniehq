"""Omnisend adapter (email + SMS marketing).

Omnisend authenticates with a single API key sent in the ``X-API-KEY`` header.
Its audience model is tag/segment based — there is no public endpoint to
enumerate lists — so audiences are addressed by a free-text **tag**: pushing a
contact applies that tag, which Omnisend automations and segments can target.

Docs: https://api-docs.omnisend.com/
"""

from __future__ import annotations

from datetime import datetime, timezone
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

API_BASE = "https://api.omnisend.com/v3"


def _headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        raise AutoresponderAuthError("Omnisend requires an API key.")
    return {"X-API-KEY": api_key, "Content-Type": "application/json"}


def _raise_for_auth(resp: httpx.Response) -> None:
    if resp.status_code in (401, 403):
        raise AutoresponderAuthError(
            "Omnisend rejected the API key (HTTP "
            f"{resp.status_code}). Generate a key in Store settings → Integrations → API keys."
        )


class OmnisendAdapter(AutoresponderAdapter):
    provider_id: ClassVar[str] = "omnisend"
    display_name: ClassVar[str] = "Omnisend"
    description: ClassVar[str] = (
        "Sync contacts to Omnisend email & SMS audiences. Contacts are tagged so "
        "Omnisend segments and automations can target them."
    )

    api_key_label: ClassVar[str] = "Omnisend API key"
    api_key_help: ClassVar[str | None] = (
        "Store settings → Integrations & API → API keys. Starts with your store's key."
    )

    # Omnisend has no list-enumeration API; push to a free-text tag instead.
    supports_audience_listing: ClassVar[bool] = False
    supports_contact_pull: ClassVar[bool] = True
    freeform_audience: ClassVar[bool] = True
    docs_url: ClassVar[str | None] = "https://api-docs.omnisend.com/"

    @classmethod
    def verify(cls, *, api_key: str | None, config: dict) -> AutoresponderAccountInfo:
        try:
            resp = httpx.get(
                f"{API_BASE}/contacts",
                headers=_headers(api_key),
                params={"limit": 1},
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise AutoresponderError(f"Could not reach Omnisend: {exc}") from exc
        _raise_for_auth(resp)
        if resp.status_code >= 400:
            raise AutoresponderError(
                f"Omnisend verification returned HTTP {resp.status_code}."
            )
        return AutoresponderAccountInfo(account_id=None, display_name="Omnisend store")

    @classmethod
    def push_contacts(
        cls,
        *,
        api_key: str | None,
        config: dict,
        audience_id: str | None,
        contacts: list[Contact],
    ) -> PushResult:
        headers = _headers(api_key)
        succeeded = 0
        errors: list[str] = []
        tag = (audience_id or "").strip()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for contact in contacts:
            if not contact.is_addressable():
                errors.append("Skipped contact with no email or phone.")
                continue
            body = cls._contact_body(contact, tag=tag, status_date=now_iso)
            try:
                resp = httpx.post(
                    f"{API_BASE}/contacts",
                    headers=headers,
                    json=body,
                    timeout=20.0,
                )
            except httpx.HTTPError as exc:
                errors.append(f"{contact.email or contact.phone}: {exc}")
                continue
            _raise_for_auth(resp)
            if resp.status_code >= 400:
                errors.append(
                    f"{contact.email or contact.phone}: HTTP {resp.status_code} {resp.text[:120]}"
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
        headers = _headers(api_key)
        params: dict[str, object] = {"limit": max(1, min(limit, 250))}
        # Omnisend filters contacts by tag via the `tag` query param.
        if audience_id:
            params["tag"] = audience_id
        try:
            resp = httpx.get(
                f"{API_BASE}/contacts", headers=headers, params=params, timeout=20.0
            )
        except httpx.HTTPError as exc:
            raise AutoresponderError(f"Could not reach Omnisend: {exc}") from exc
        _raise_for_auth(resp)
        if resp.status_code >= 400:
            raise AutoresponderError(
                f"Omnisend contact pull returned HTTP {resp.status_code}."
            )
        out: list[Contact] = []
        for raw in resp.json().get("contacts", []):
            out.append(cls._parse_contact(raw))
        return out

    # ------------------------------------------------------------------
    # Email-campaign analytics (beyond the contact-sync interface).
    # Omnisend exposes campaigns at GET /v3/campaigns; the campaign object
    # carries engagement + deliverability counts whose field names vary across
    # API revisions, so we look them up defensively and keep the raw payload.
    # ------------------------------------------------------------------

    @classmethod
    def list_campaigns(
        cls, *, api_key: str | None, max_campaigns: int = 500
    ) -> list[dict]:
        """Pull email campaigns with their metrics. Returns normalized dicts
        (see ``_normalize_campaign``). Raises AutoresponderAuthError on bad keys."""
        headers = _headers(api_key)
        out: list[dict] = []
        offset = 0
        page = 100
        while len(out) < max_campaigns:
            try:
                resp = httpx.get(
                    f"{API_BASE}/campaigns",
                    headers=headers,
                    params={"limit": page, "offset": offset},
                    timeout=30.0,
                )
            except httpx.HTTPError as exc:
                raise AutoresponderError(f"Could not reach Omnisend: {exc}") from exc
            _raise_for_auth(resp)
            if resp.status_code >= 400:
                raise AutoresponderError(
                    f"Omnisend campaign list returned HTTP {resp.status_code}."
                )
            body = resp.json() if resp.content else {}
            rows = body.get("campaigns") or body.get("data") or []
            if not rows:
                break
            for raw in rows:
                out.append(_normalize_campaign(raw))
            if len(rows) < page:
                break
            offset += page
        return out[:max_campaigns]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _contact_body(contact: Contact, *, tag: str, status_date: str) -> dict:
        identifiers: list[dict] = []
        if contact.email:
            identifiers.append(
                {
                    "type": "email",
                    "id": contact.email,
                    "channels": {
                        "email": {"status": "subscribed", "statusDate": status_date}
                    },
                }
            )
        if contact.phone:
            identifiers.append(
                {
                    "type": "phone",
                    "id": contact.phone,
                    "channels": {
                        "sms": {"status": "subscribed", "statusDate": status_date}
                    },
                }
            )
        tags = list(contact.tags)
        if tag and tag not in tags:
            tags.append(tag)
        body: dict = {"identifiers": identifiers}
        if contact.first_name:
            body["firstName"] = contact.first_name
        if contact.last_name:
            body["lastName"] = contact.last_name
        if tags:
            body["tags"] = tags
        if contact.custom_fields:
            body["customProperties"] = contact.custom_fields
        return body

    @staticmethod
    def _parse_contact(raw: dict) -> Contact:
        email = raw.get("email")
        phone = raw.get("phone")
        if not email or not phone:
            for ident in raw.get("identifiers", []) or []:
                if ident.get("type") == "email" and not email:
                    email = ident.get("id")
                elif ident.get("type") == "phone" and not phone:
                    phone = ident.get("id")
        return Contact(
            email=email,
            first_name=raw.get("firstName"),
            last_name=raw.get("lastName"),
            phone=phone,
            tags=list(raw.get("tags") or []),
            raw=raw,
        )


# ---------------------------------------------------------------------------
# Campaign normalization — tolerant of Omnisend field-name variation across
# API revisions. Metrics may sit top-level or under a nested container.
# ---------------------------------------------------------------------------

_ID_KEYS = ("campaignID", "campaignId", "id", "ID")
_SUBJECT_KEYS = ("subject", "emailSubject", "subjectLine")
_FROM_KEYS = ("fromName", "senderName", "from_name")
_SENT_AT_KEYS = ("startDate", "sendDate", "sentAt", "scheduledDate", "created", "createdAt")
_STATUS_KEYS = ("status", "state")
_TYPE_KEYS = ("type", "channel", "campaignType")
_SENT_KEYS = ("sent", "sends", "sentCount", "delivered", "recipients", "totalRecipients")
_OPEN_KEYS = ("opened", "opens", "uniqueOpens", "openedCount", "opensCount")
_CLICK_KEYS = ("clicked", "clicks", "uniqueClicks", "clickedCount", "clicksCount")
_BOUNCE_KEYS = ("bounced", "bounces", "bouncedCount", "hardBounces")
_COMPLAINT_KEYS = ("complained", "complaints", "spam", "spamReports", "complaintsCount")
_UNSUB_KEYS = ("unsubscribed", "unsubscribes", "unsubscribedCount", "optOuts")
_REVENUE_KEYS = ("revenue", "totalRevenue", "sales")
_METRIC_CONTAINERS = ("campaignDetails", "statistics", "stats", "report", "metrics", "summary")


def _flatten_metrics(raw: dict) -> dict:
    """Merge any nested metric containers + scalar top-level fields into one
    flat lookup dict (top-level wins on key collisions)."""
    flat: dict = {}
    for container in _METRIC_CONTAINERS:
        val = raw.get(container)
        if isinstance(val, dict):
            flat.update(val)
    flat.update({k: v for k, v in raw.items() if not isinstance(v, (dict, list))})
    return flat


def _first(d: dict, keys: tuple[str, ...]):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _to_int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _parse_dt(v):
    if not v:
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(v).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _normalize_campaign(raw: dict) -> dict:
    flat = _flatten_metrics(raw)
    revenue = _first(flat, _REVENUE_KEYS)
    revenue_cents = None
    if revenue is not None:
        try:
            revenue_cents = int(round(float(revenue) * 100))
        except (TypeError, ValueError):
            revenue_cents = None
    return {
        "external_id": str(_first(raw, _ID_KEYS) or _first(flat, _ID_KEYS) or ""),
        "name": raw.get("name"),
        "subject": _first(raw, _SUBJECT_KEYS),
        "from_name": _first(raw, _FROM_KEYS),
        "campaign_type": _first(raw, _TYPE_KEYS),
        "status": _first(raw, _STATUS_KEYS),
        "sent_at": _parse_dt(_first(raw, _SENT_AT_KEYS) or _first(flat, _SENT_AT_KEYS)),
        "sent": _to_int(_first(flat, _SENT_KEYS)),
        "opened": _to_int(_first(flat, _OPEN_KEYS)),
        "clicked": _to_int(_first(flat, _CLICK_KEYS)),
        "bounced": _to_int(_first(flat, _BOUNCE_KEYS)),
        "complained": _to_int(_first(flat, _COMPLAINT_KEYS)),
        "unsubscribed": _to_int(_first(flat, _UNSUB_KEYS)),
        "revenue_cents": revenue_cents,
        "currency": _first(flat, ("currency",)),
        "raw": raw,
    }
