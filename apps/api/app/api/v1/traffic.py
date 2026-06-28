"""Traffic Genie endpoints.

Catalog (source cards + recipes), traffic campaigns CRUD + asset generation, the
AI traffic-recommendation, and the Smart UTM Builder. All workspace-scoped and
permission-gated; reads need membership, writes need Marketer+.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.traffic import (
    CreateTrafficCampaignRequest,
    CreateUtmLinkRequest,
    GenerateAssetsRequest,
    LogMetricRequest,
    RecommendationRequest,
    TrafficCampaignAssetPublic,
    TrafficCampaignDetail,
    TrafficCampaignPublic,
    TrafficCatalogResponse,
    TrafficMetricPublic,
    UpdateTrafficCampaignRequest,
    UtmLinkPublic,
)
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import traffic_analytics_service, traffic_service, utm_service
from app.traffic import catalog as cat

router = APIRouter()


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/traffic/catalog", response_model=TrafficCatalogResponse)
def get_traffic_catalog(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
) -> TrafficCatalogResponse:
    return TrafficCatalogResponse(**cat.catalog_payload())


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/traffic/campaigns", response_model=list[TrafficCampaignPublic])
def list_traffic_campaigns(
    workspace_id: UUID,
    source_slug: str | None = None,
    status_filter: str | None = None,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[TrafficCampaignPublic]:
    rows = traffic_service.list_campaigns(
        db, workspace_id=workspace_id, source_slug=source_slug, status=status_filter
    )
    return [TrafficCampaignPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/traffic/campaigns",
    response_model=TrafficCampaignDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_traffic_campaign(
    workspace_id: UUID,
    payload: CreateTrafficCampaignRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> TrafficCampaignDetail:
    campaign = traffic_service.create_campaign(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        source_slug=payload.source_slug,
        name=payload.name,
        goal=payload.goal,
        offer_name=payload.offer_name,
        offer_url=payload.offer_url,
        audience=payload.audience,
        budget_cents=payload.budget_cents,
        currency=payload.currency,
        omnisend_segment=payload.omnisend_segment,
        omnisend_flow=payload.omnisend_flow,
        request=request,
    )
    return TrafficCampaignDetail.model_validate(campaign)


@router.get(
    "/{workspace_id}/traffic/campaigns/{campaign_id}",
    response_model=TrafficCampaignDetail,
)
def get_traffic_campaign(
    workspace_id: UUID,
    campaign_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> TrafficCampaignDetail:
    campaign = traffic_service.get_campaign(db, workspace_id=workspace_id, campaign_id=campaign_id)
    return TrafficCampaignDetail.model_validate(campaign)


@router.patch(
    "/{workspace_id}/traffic/campaigns/{campaign_id}",
    response_model=TrafficCampaignDetail,
)
def update_traffic_campaign(
    workspace_id: UUID,
    campaign_id: UUID,
    payload: UpdateTrafficCampaignRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> TrafficCampaignDetail:
    campaign = traffic_service.update_campaign(
        db,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        actor_user_id=member.user_id,
        updates=payload.model_dump(exclude_unset=True),
        request=request,
    )
    return TrafficCampaignDetail.model_validate(campaign)


@router.delete(
    "/{workspace_id}/traffic/campaigns/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_traffic_campaign(
    workspace_id: UUID,
    campaign_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> None:
    traffic_service.delete_campaign(
        db,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        actor_user_id=member.user_id,
        request=request,
    )


@router.post(
    "/{workspace_id}/traffic/campaigns/{campaign_id}/generate-assets",
    response_model=list[TrafficCampaignAssetPublic],
    status_code=status.HTTP_201_CREATED,
)
def generate_traffic_assets(
    workspace_id: UUID,
    campaign_id: UUID,
    payload: GenerateAssetsRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> list[TrafficCampaignAssetPublic]:
    assets = traffic_service.generate_campaign_assets(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        campaign_id=campaign_id,
        asset_types=payload.asset_types,
        request=request,
    )
    return [TrafficCampaignAssetPublic.model_validate(a) for a in assets]


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/traffic/recommend", response_model=dict)
def recommend_traffic(
    workspace_id: UUID,
    payload: RecommendationRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> dict:
    return traffic_service.generate_recommendation(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        inputs=payload.model_dump(exclude_none=True),
        request=request,
    )


# ---------------------------------------------------------------------------
# Smart UTM Builder
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/traffic/utm-links", response_model=list[UtmLinkPublic])
def list_utm_links(
    workspace_id: UUID,
    campaign_id: UUID | None = None,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[UtmLinkPublic]:
    rows = utm_service.list_links(db, workspace_id=workspace_id, campaign_id=campaign_id)
    return [UtmLinkPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/traffic/utm-links",
    response_model=UtmLinkPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_utm_link(
    workspace_id: UUID,
    payload: CreateUtmLinkRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> UtmLinkPublic:
    link = utm_service.create_link(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        destination_url=payload.destination_url,
        source=payload.source,
        medium=payload.medium,
        campaign=payload.campaign,
        content=payload.content,
        term=payload.term,
        vendor_name=payload.vendor_name,
        campaign_id=payload.campaign_id,
        request=request,
    )
    return UtmLinkPublic.model_validate(link)


@router.delete(
    "/{workspace_id}/traffic/utm-links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_utm_link(
    workspace_id: UUID,
    link_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> None:
    utm_service.delete_link(
        db,
        workspace_id=workspace_id,
        link_id=link_id,
        actor_user_id=member.user_id,
        request=request,
    )


# ---------------------------------------------------------------------------
# Analytics & optimization (Phase 6)
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/traffic/analytics/overview", response_model=dict)
def traffic_analytics_overview(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> dict:
    return traffic_analytics_service.compute_overview(db, workspace_id=workspace_id)


@router.get("/{workspace_id}/traffic/metrics", response_model=list[TrafficMetricPublic])
def list_traffic_metrics(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[TrafficMetricPublic]:
    rows = traffic_analytics_service.list_metrics(db, workspace_id=workspace_id)
    return [TrafficMetricPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/traffic/metrics",
    response_model=TrafficMetricPublic,
    status_code=status.HTTP_201_CREATED,
)
def log_traffic_metric(
    workspace_id: UUID,
    payload: LogMetricRequest,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> TrafficMetricPublic:
    metric = traffic_analytics_service.log_metric(
        db, workspace_id=workspace_id, actor_user_id=member.user_id,
        data=payload.model_dump(exclude_unset=True), request=request,
    )
    return TrafficMetricPublic.model_validate(metric)


@router.post("/{workspace_id}/traffic/analytics/optimize", response_model=dict)
def optimize_traffic(
    workspace_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> dict:
    return traffic_analytics_service.run_optimizer(
        db, workspace_id=workspace_id, actor_user_id=member.user_id,
    )
