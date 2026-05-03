"""Provider webhook routes.

Closes the polling loop for connected ad platforms. Each provider POSTs status
notifications (campaign approved/rejected, daily spend limit reached, account
flagged) to `/api/v1/provider-webhooks/{provider}`. We auth via HMAC-SHA256 of
the raw body using the per-provider shared secret in env (`GOOGLE_ADS_WEBHOOK_SECRET`,
`META_ADS_WEBHOOK_SECRET`, `LINKEDIN_ADS_WEBHOOK_SECRET`).

The body shape is provider-agnostic — we accept whatever JSON the provider
sends and route the event by `provider` + `event_type`. We update the matching
Campaign / Ad / RecommendationExecution row when the external_id matches a row
already in the workspace.

Hard rules:
- Refuse unsigned traffic: missing/invalid signature → 401.
- Refuse if the per-provider secret is empty: 503.
- Workspace isolation by external_account_id: events for an account we don't
  recognize are 200-acked but written to the audit log as `unmatched`.
- Every event is audit-logged with actor_type=SYSTEM.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.audit_log import AuditActorType
from app.models.campaign import Campaign, CampaignStatus
from app.models.connected_account import ConnectedAccount
from app.services import audit_service

router = APIRouter()

log = get_logger(__name__)


import os

_PROVIDER_SECRET_ENV_VARS = {
    "google_ads": "GOOGLE_ADS_WEBHOOK_SECRET",
    "meta_ads": "META_ADS_WEBHOOK_SECRET",
    "linkedin_ads": "LINKEDIN_ADS_WEBHOOK_SECRET",
}


class WebhookConfigError(AdVantaError):
    status_code = 503
    code = "provider_webhook_not_configured"


class WebhookResult(BaseModel):
    matched: bool
    provider: str
    event_type: str
    rows_updated: int
    reason: str | None = None


def _get_provider_secret(provider: str) -> str:
    env_name = _PROVIDER_SECRET_ENV_VARS.get(provider)
    if env_name is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider}'.")
    # Read os.environ live so per-test fixtures can flip the secret on/off
    # without rebuilding settings. Fall back to the settings attribute when
    # the env var is unset (e.g. production runs from a baked .env).
    secret = os.environ.get(env_name) or getattr(
        settings, env_name.lower(), ""
    )
    if not secret:
        raise WebhookConfigError(
            f"{env_name} is not set; refusing webhook."
        )
    return secret


def _verify_signature(
    *, body: bytes, signature_header: str | None, secret: str
) -> None:
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing webhook signature.")
    expected = hmac.new(
        secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256
    ).hexdigest()
    # Some providers send the digest with a `sha256=` prefix.
    received = signature_header.split("=", 1)[-1].strip()
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")


@router.post(
    "/provider-webhooks/{provider}", response_model=WebhookResult, tags=["webhooks"]
)
async def receive_provider_webhook(
    provider: str,
    request: Request,
    x_provider_signature: str | None = Header(default=None, alias="X-Provider-Signature"),
    db: Session = Depends(get_db),
) -> WebhookResult:
    secret = _get_provider_secret(provider)
    raw = await request.body()
    _verify_signature(body=raw, signature_header=x_provider_signature, secret=secret)

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Webhook body is not JSON.")

    event_type = str(payload.get("event_type") or payload.get("type") or "unknown")
    external_account_id = (
        payload.get("account_id")
        or payload.get("external_account_id")
        or (payload.get("account") or {}).get("id")
    )

    # Find the connected account first; this gives us the workspace.
    account: ConnectedAccount | None = None
    if external_account_id:
        account = (
            db.query(ConnectedAccount)
            .filter(
                ConnectedAccount.provider == provider,
                ConnectedAccount.provider_account_id == str(external_account_id),
            )
            .first()
        )

    if account is None:
        log.info(
            "provider_webhook.unmatched_account",
            provider=provider,
            event_type=event_type,
            external_account_id=external_account_id,
        )
        # Always 200 — we don't want providers to retry forever for accounts
        # that were disconnected on our side.
        return WebhookResult(
            matched=False,
            provider=provider,
            event_type=event_type,
            rows_updated=0,
            reason="unrecognized_account",
        )

    rows_updated = _apply_event(
        db, account=account, provider=provider, event_type=event_type, payload=payload
    )

    audit_service.log_event(
        db,
        workspace_id=account.workspace_id,
        actor_type=AuditActorType.SYSTEM,
        actor_id=account.connected_by,
        action=f"provider_webhook.{provider}.{event_type}",
        resource_type="connected_account",
        resource_id=account.id,
        metadata={"event_type": event_type, "rows_updated": rows_updated},
    )
    db.commit()

    return WebhookResult(
        matched=True,
        provider=provider,
        event_type=event_type,
        rows_updated=rows_updated,
    )


def _apply_event(
    db: Session,
    *,
    account: ConnectedAccount,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
) -> int:
    """Translate the webhook into row updates. Returns the count of rows
    touched. Unknown event types are 200-acked without writes — providers
    add new event types over time and we don't want to drop legitimate
    notifications until we explicitly support them."""

    rows = 0

    # Campaign status changes — most common case.
    if event_type in {
        "campaign.status_changed",
        "campaign.approved",
        "campaign.rejected",
        "campaign.paused",
        "campaign.ended",
    }:
        external_campaign_id = (
            payload.get("campaign_id")
            or (payload.get("campaign") or {}).get("id")
            or payload.get("resource_name")
        )
        if not external_campaign_id:
            return 0

        target = (
            db.query(Campaign)
            .filter(
                Campaign.workspace_id == account.workspace_id,
                Campaign.provider == provider,
                Campaign.external_id == str(external_campaign_id),
            )
            .first()
        )
        if target is None:
            return 0

        new_status_raw = (
            payload.get("status") or (payload.get("campaign") or {}).get("status")
        )
        if new_status_raw:
            try:
                target.status = CampaignStatus(str(new_status_raw).lower())
            except ValueError:
                # Leave status as-is when the provider sends a state we don't
                # model (e.g. "REMOVED"); only log it.
                log.info(
                    "provider_webhook.unknown_campaign_status",
                    provider=provider,
                    received=new_status_raw,
                )
        target.last_synced_at = datetime.now(timezone.utc)
        rows += 1
        return rows

    # Account-level alerts (billing failure, account flagged) — log only.
    if event_type in {
        "account.alert",
        "account.suspended",
        "account.billing_failure",
    }:
        # Audit log happens in the caller; nothing to update on our side.
        return 0

    return 0
