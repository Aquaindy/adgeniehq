"""Ad-structure builder — user-built ad groups, ads, and creatives.

Lets an operator define the structure under a campaign inside AdVanta:
campaign → ad group (targeting + budget) → ad → creative. These are saved as
`advanta_draft` rows (no platform `external_id` yet). Pushing them to the ad
platform is a separate step (needs provider create_ad_set/create_ad methods);
until then this is the canonical, editable blueprint in the app.

Platform-synced ad groups/ads stay read-only — only drafts are editable here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.ad import Ad, AdStatus
from app.models.ad_group import AdGroup, AdGroupStatus, AdObjectSource
from app.models.audit_log import AuditActorType
from app.models.campaign import Campaign
from app.models.creative import Creative, CreativeSource, CreativeType
from app.services import audit_service


class CampaignNotFoundError(AdVantaError):
    status_code = 404
    code = "campaign_not_found"


class AdGroupNotFoundError(AdVantaError):
    status_code = 404
    code = "ad_group_not_found"


class AdNotFoundError(AdVantaError):
    status_code = 404
    code = "ad_not_found"


class CreativeNotFoundError(AdVantaError):
    status_code = 404
    code = "creative_not_found"


class NotEditableError(AdVantaError):
    status_code = 409
    code = "not_editable"


def _campaign(db: Session, *, workspace_id: UUID, campaign_id: UUID) -> Campaign:
    c = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.workspace_id == workspace_id)
        .first()
    )
    if c is None:
        raise CampaignNotFoundError("Campaign not found in this workspace.")
    return c


def _draft_ad_group(db: Session, *, workspace_id: UUID, ad_group_id: UUID) -> AdGroup:
    ag = (
        db.query(AdGroup)
        .filter(AdGroup.id == ad_group_id, AdGroup.workspace_id == workspace_id)
        .first()
    )
    if ag is None:
        raise AdGroupNotFoundError("Ad group not found in this workspace.")
    return ag


def _draft_ad(db: Session, *, workspace_id: UUID, ad_id: UUID) -> Ad:
    ad = (
        db.query(Ad)
        .filter(Ad.id == ad_id, Ad.workspace_id == workspace_id)
        .first()
    )
    if ad is None:
        raise AdNotFoundError("Ad not found in this workspace.")
    return ad


def _ensure_draft(obj: AdGroup | Ad) -> None:
    if obj.source != AdObjectSource.ADVANTA_DRAFT:
        raise NotEditableError(
            "Platform-synced objects are read-only here; only AdVanta drafts can be edited."
        )


def _resolve_creative(db: Session, *, workspace_id: UUID, creative_id: UUID | None) -> Creative | None:
    if creative_id is None:
        return None
    creative = (
        db.query(Creative)
        .filter(Creative.id == creative_id, Creative.workspace_id == workspace_id)
        .first()
    )
    if creative is None:
        raise CreativeNotFoundError("Creative not found in this workspace.")
    return creative


def _audit(db, *, workspace_id, actor_user_id, action, resource_type, resource_id, metadata, request):
    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
        request=request,
    )


# ---------------------------------------------------------------------------
# Ad groups
# ---------------------------------------------------------------------------


def create_ad_group(
    db: Session,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    name: str,
    daily_budget_cents: int | None,
    targeting: dict,
    actor_user_id: UUID,
    request: Request | None = None,
) -> AdGroup:
    campaign = _campaign(db, workspace_id=workspace_id, campaign_id=campaign_id)
    now = datetime.now(timezone.utc)
    ag = AdGroup(
        workspace_id=workspace_id,
        campaign_id=campaign.id,
        external_id=None,
        source=AdObjectSource.ADVANTA_DRAFT,
        name=name.strip(),
        status=AdGroupStatus.PAUSED,
        daily_budget_cents=daily_budget_cents,
        targeting=targeting,
        last_synced_at=now,
    )
    db.add(ag)
    db.flush()
    _audit(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action="ad_group.draft_created",
        resource_type="ad_group",
        resource_id=ag.id,
        metadata={"campaign_id": str(campaign.id), "name": ag.name},
        request=request,
    )
    db.commit()
    db.refresh(ag)
    return ag


def update_ad_group(
    db: Session,
    *,
    workspace_id: UUID,
    ad_group_id: UUID,
    updates: dict,
    actor_user_id: UUID,
    request: Request | None = None,
) -> AdGroup:
    ag = _draft_ad_group(db, workspace_id=workspace_id, ad_group_id=ad_group_id)
    _ensure_draft(ag)
    if "name" in updates and updates["name"]:
        ag.name = updates["name"].strip()
    if "daily_budget_cents" in updates and updates["daily_budget_cents"] is not None:
        ag.daily_budget_cents = updates["daily_budget_cents"]
    if updates.get("targeting") is not None:
        ag.targeting = updates["targeting"]
    db.commit()
    db.refresh(ag)
    return ag


def delete_ad_group(
    db: Session, *, workspace_id: UUID, ad_group_id: UUID
) -> None:
    ag = _draft_ad_group(db, workspace_id=workspace_id, ad_group_id=ad_group_id)
    _ensure_draft(ag)
    db.delete(ag)
    db.commit()


# ---------------------------------------------------------------------------
# Ads
# ---------------------------------------------------------------------------


def create_ad(
    db: Session,
    *,
    workspace_id: UUID,
    ad_group_id: UUID,
    name: str,
    landing_page_url: str | None,
    creative_id: UUID | None,
    actor_user_id: UUID,
    request: Request | None = None,
) -> Ad:
    ag = _draft_ad_group(db, workspace_id=workspace_id, ad_group_id=ad_group_id)
    _ensure_draft(ag)
    creative = _resolve_creative(db, workspace_id=workspace_id, creative_id=creative_id)
    now = datetime.now(timezone.utc)
    ad = Ad(
        workspace_id=workspace_id,
        campaign_id=ag.campaign_id,
        ad_group_id=ag.id,
        creative_id=creative.id if creative else None,
        external_id=None,
        source=AdObjectSource.ADVANTA_DRAFT,
        name=name.strip(),
        status=AdStatus.PAUSED,
        landing_page_url=landing_page_url,
        last_synced_at=now,
    )
    db.add(ad)
    db.flush()
    _audit(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action="ad.draft_created",
        resource_type="ad",
        resource_id=ad.id,
        metadata={"ad_group_id": str(ag.id), "name": ad.name},
        request=request,
    )
    db.commit()
    db.refresh(ad)
    return ad


def update_ad(
    db: Session,
    *,
    workspace_id: UUID,
    ad_id: UUID,
    updates: dict,
    actor_user_id: UUID,
    request: Request | None = None,
) -> Ad:
    ad = _draft_ad(db, workspace_id=workspace_id, ad_id=ad_id)
    _ensure_draft(ad)
    if "name" in updates and updates["name"]:
        ad.name = updates["name"].strip()
    if "landing_page_url" in updates:
        ad.landing_page_url = updates["landing_page_url"]
    if "creative_id" in updates:
        creative = _resolve_creative(
            db, workspace_id=workspace_id, creative_id=updates["creative_id"]
        )
        ad.creative_id = creative.id if creative else None
    db.commit()
    db.refresh(ad)
    return ad


def delete_ad(db: Session, *, workspace_id: UUID, ad_id: UUID) -> None:
    ad = _draft_ad(db, workspace_id=workspace_id, ad_id=ad_id)
    _ensure_draft(ad)
    db.delete(ad)
    db.commit()


# ---------------------------------------------------------------------------
# Creatives (user-created)
# ---------------------------------------------------------------------------


def create_creative(
    db: Session,
    *,
    workspace_id: UUID,
    type: CreativeType,
    title: str | None,
    headline: str | None,
    primary_text: str | None,
    description: str | None,
    cta: str | None,
    image_url: str | None,
    video_url: str | None,
    actor_user_id: UUID,
    request: Request | None = None,
) -> Creative:
    creative = Creative(
        workspace_id=workspace_id,
        type=type,
        source=CreativeSource.USER_UPLOADED,
        title=title,
        headline=headline,
        primary_text=primary_text,
        description=description,
        cta=cta,
        image_url=image_url,
        video_url=video_url,
        metadata_json={"created_via": "ad_builder"},
    )
    db.add(creative)
    db.flush()
    _audit(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action="creative.created",
        resource_type="creative",
        resource_id=creative.id,
        metadata={"type": type.value},
        request=request,
    )
    db.commit()
    db.refresh(creative)
    return creative
