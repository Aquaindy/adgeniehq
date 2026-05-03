from datetime import date
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignStatus
from app.schemas.campaigns import CampaignDetail, CampaignPublic, CampaignSummary


def list_campaigns(
    db: Session,
    *,
    workspace_id: UUID,
    provider: str | None = None,
    status: CampaignStatus | None = None,
    limit: int = 200,
) -> list[CampaignPublic]:
    query = db.query(Campaign).filter(Campaign.workspace_id == workspace_id)
    if provider:
        query = query.filter(Campaign.provider == provider)
    if status:
        query = query.filter(Campaign.status == status)
    rows = query.order_by(Campaign.last_synced_at.desc()).limit(limit).all()
    return [CampaignPublic.model_validate(r) for r in rows]


def get_campaign(
    db: Session, *, workspace_id: UUID, campaign_id: UUID
) -> CampaignDetail | None:
    row = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.workspace_id == workspace_id)
        .first()
    )
    return CampaignDetail.model_validate(row) if row else None


def summary(db: Session, *, workspace_id: UUID) -> CampaignSummary:
    rows: list[Campaign] = (
        db.query(Campaign).filter(Campaign.workspace_id == workspace_id).all()
    )

    counts = {
        CampaignStatus.ACTIVE: 0,
        CampaignStatus.PAUSED: 0,
        CampaignStatus.ENDED: 0,
        CampaignStatus.ARCHIVED: 0,
        CampaignStatus.UNKNOWN: 0,
    }
    per_provider: dict[str, int] = {}
    active_without_budget = 0
    stale_active = 0
    today = date.today()
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
        per_provider[r.provider] = per_provider.get(r.provider, 0) + 1
        if r.status == CampaignStatus.ACTIVE:
            if not r.daily_budget_cents and not r.lifetime_budget_cents:
                active_without_budget += 1
            if r.end_date is not None and r.end_date < today:
                stale_active += 1

    last_synced_at = (
        db.query(func.max(Campaign.last_synced_at))
        .filter(Campaign.workspace_id == workspace_id)
        .scalar()
    )

    return CampaignSummary(
        total=len(rows),
        active=counts[CampaignStatus.ACTIVE],
        paused=counts[CampaignStatus.PAUSED],
        ended=counts[CampaignStatus.ENDED],
        archived=counts[CampaignStatus.ARCHIVED],
        unknown=counts[CampaignStatus.UNKNOWN],
        per_provider=per_provider,
        active_without_budget=active_without_budget,
        stale_active=stale_active,
        last_synced_at=last_synced_at,
    )
