"""Email-campaign sync + management.

Pulls email campaigns (with engagement + deliverability metrics) from the
workspace's connected ESP — Omnisend today — into `email_campaigns`, computes
rates, and lets a campaign be linked to a paid-ads `Campaign`. The
email-marketing agent reads these rows; this service owns the ingest + writes.

Reuses the autoresponder connection (API key, encrypted) rather than a separate
credential, so connecting Omnisend once powers both contact sync and analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdGenieError
from app.core.logging import get_logger
from app.integrations.autoresponders.omnisend import OmnisendAdapter
from app.models.audit_log import AuditActorType
from app.models.autoresponder_connection import AutoresponderConnection
from app.models.campaign import Campaign
from app.models.connected_account import ConnectionStatus
from app.models.email_campaign import EmailCampaign
from app.security.encryption import decrypt
from app.services import audit_service
from app.services.autoresponder_service import AutoresponderNotConnectedError

log = get_logger(__name__)

PROVIDER = "omnisend"


class EmailCampaignNotFoundError(AdGenieError):
    status_code = 404
    code = "email_campaign_not_found"


def _omnisend_api_key(db: Session, *, workspace_id: UUID) -> str:
    conn = (
        db.query(AutoresponderConnection)
        .filter(
            AutoresponderConnection.workspace_id == workspace_id,
            AutoresponderConnection.provider == PROVIDER,
        )
        .first()
    )
    if conn is None or conn.status != ConnectionStatus.CONNECTED or not conn.encrypted_api_key:
        raise AutoresponderNotConnectedError(
            "Omnisend is not connected for this workspace. Connect it under "
            "Settings → Autoresponders to sync email campaigns."
        )
    return decrypt(conn.encrypted_api_key)


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 6) if whole > 0 else None


def sync_email_campaigns(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    request: Request | None = None,
) -> list[EmailCampaign]:
    """Pull Omnisend campaigns and upsert them. Returns the workspace's email
    campaigns (most recent first) after the sync."""
    api_key = _omnisend_api_key(db, workspace_id=workspace_id)
    rows = OmnisendAdapter.list_campaigns(api_key=api_key)

    now = datetime.now(timezone.utc)
    existing = {
        ec.external_id: ec
        for ec in db.query(EmailCampaign)
        .filter(
            EmailCampaign.workspace_id == workspace_id,
            EmailCampaign.provider == PROVIDER,
        )
        .all()
    }

    upserted = 0
    for r in rows:
        external_id = (r.get("external_id") or "").strip()
        if not external_id:
            continue
        ec = existing.get(external_id)
        if ec is None:
            ec = EmailCampaign(
                workspace_id=workspace_id,
                provider=PROVIDER,
                external_id=external_id,
            )
            db.add(ec)

        sent = int(r.get("sent") or 0)
        ec.name = r.get("name")
        ec.subject = r.get("subject")
        ec.from_name = r.get("from_name")
        ec.campaign_type = r.get("campaign_type")
        ec.status = (r.get("status") or None)
        ec.sent_at = r.get("sent_at")
        ec.sent_count = sent
        ec.opened_count = int(r.get("opened") or 0)
        ec.clicked_count = int(r.get("clicked") or 0)
        ec.bounced_count = int(r.get("bounced") or 0)
        ec.complained_count = int(r.get("complained") or 0)
        ec.unsubscribed_count = int(r.get("unsubscribed") or 0)
        ec.open_rate = _rate(ec.opened_count, sent)
        ec.click_rate = _rate(ec.clicked_count, sent)
        ec.bounce_rate = _rate(ec.bounced_count, sent)
        ec.complaint_rate = _rate(ec.complained_count, sent)
        ec.unsubscribe_rate = _rate(ec.unsubscribed_count, sent)
        ec.revenue_cents = r.get("revenue_cents")
        ec.currency = r.get("currency")
        ec.raw_payload = r.get("raw")
        ec.synced_at = now
        upserted += 1

    conn = (
        db.query(AutoresponderConnection)
        .filter(
            AutoresponderConnection.workspace_id == workspace_id,
            AutoresponderConnection.provider == PROVIDER,
        )
        .first()
    )
    if conn is not None:
        conn.last_sync_at = now

    db.commit()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action="email_campaigns.synced",
        resource_type="email_campaign_sync",
        resource_id=None,
        metadata={"provider": PROVIDER, "campaigns": upserted},
        request=request,
    )
    db.commit()

    log.info("email_campaigns.synced", workspace_id=str(workspace_id), count=upserted)
    return list_email_campaigns(db, workspace_id=workspace_id)


def list_email_campaigns(
    db: Session, *, workspace_id: UUID, limit: int = 500
) -> list[EmailCampaign]:
    return (
        db.query(EmailCampaign)
        .filter(EmailCampaign.workspace_id == workspace_id)
        .order_by(EmailCampaign.sent_at.desc().nullslast(), EmailCampaign.created_at.desc())
        .limit(limit)
        .all()
    )


def get_email_campaign(
    db: Session, *, workspace_id: UUID, email_campaign_id: UUID
) -> EmailCampaign:
    ec = (
        db.query(EmailCampaign)
        .filter(
            EmailCampaign.id == email_campaign_id,
            EmailCampaign.workspace_id == workspace_id,
        )
        .first()
    )
    if ec is None:
        raise EmailCampaignNotFoundError("Email campaign not found.")
    return ec


def associate_with_ad_campaign(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    email_campaign_id: UUID,
    ad_campaign_id: UUID | None,
    request: Request | None = None,
) -> EmailCampaign:
    """Link (or unlink, with ad_campaign_id=None) an email campaign to a paid-ads
    campaign. Both must belong to the workspace."""
    ec = get_email_campaign(db, workspace_id=workspace_id, email_campaign_id=email_campaign_id)

    if ad_campaign_id is not None:
        ad = (
            db.query(Campaign)
            .filter(Campaign.id == ad_campaign_id, Campaign.workspace_id == workspace_id)
            .first()
        )
        if ad is None:
            raise EmailCampaignNotFoundError("Ad campaign not found in this workspace.")

    ec.ad_campaign_id = ad_campaign_id
    db.commit()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action="email_campaign.associated",
        resource_type="email_campaign",
        resource_id=ec.id,
        metadata={"ad_campaign_id": str(ad_campaign_id) if ad_campaign_id else None},
        request=request,
    )
    db.commit()
    db.refresh(ec)
    return ec
