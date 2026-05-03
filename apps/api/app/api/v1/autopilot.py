from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.autopilot_config import AutopilotMode
from app.models.recommendation import Recommendation, RecommendationStatus, RiskLevel
from app.models.workspace_member import WorkspaceMember
from app.security.dependencies import get_current_member
from app.security.permissions import Role, require_role_at_least
from app.services import autopilot_service

router = APIRouter()


class AutopilotConfigPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mode: AutopilotMode
    max_daily_spend_increase_cents: int | None
    max_daily_spend_total_cents: int | None
    max_pct_increase_per_change: int | None
    min_conversion_threshold: int | None
    allowed_action_types: list[str] | None
    risk_ceiling: RiskLevel
    stop_loss_active: bool
    stop_loss_reason: str | None


class AutopilotConfigPatch(BaseModel):
    mode: AutopilotMode | None = None
    max_daily_spend_increase_cents: int | None = None
    max_daily_spend_total_cents: int | None = None
    max_pct_increase_per_change: int | None = None
    min_conversion_threshold: int | None = None
    allowed_action_types: list[str] | None = None
    risk_ceiling: RiskLevel | None = None
    stop_loss_active: bool | None = None
    stop_loss_reason: str | None = None


class AutopilotPreviewItem(BaseModel):
    recommendation_id: str
    recommendation_type: str
    risk_level: RiskLevel
    allow: bool
    reason: str
    matched_rules: list[str]


@router.get(
    "/{workspace_id}/autopilot",
    response_model=AutopilotConfigPublic,
)
def get_autopilot_config(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AutopilotConfigPublic:
    config = autopilot_service.get_or_create_config(db, workspace_id=workspace_id)
    return AutopilotConfigPublic.model_validate(config)


@router.patch(
    "/{workspace_id}/autopilot",
    response_model=AutopilotConfigPublic,
)
def update_autopilot_config(
    workspace_id: UUID,
    payload: AutopilotConfigPatch,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AutopilotConfigPublic:
    # Only owners may toggle autopilot mode or change spend caps.
    require_role_at_least(member.role, Role.OWNER)
    patch = payload.model_dump(exclude_none=True)
    config = autopilot_service.update_config(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        patch=patch,
    )
    return AutopilotConfigPublic.model_validate(config)


@router.get(
    "/{workspace_id}/autopilot/preview",
    response_model=list[AutopilotPreviewItem],
)
def preview_autopilot(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AutopilotPreviewItem]:
    """Show what autopilot would auto-approve right now without writing
    anything. Useful before flipping the switch."""
    config = autopilot_service.get_or_create_config(db, workspace_id=workspace_id)
    open_recs = (
        db.query(Recommendation)
        .filter(
            Recommendation.workspace_id == workspace_id,
            Recommendation.status == RecommendationStatus.OPEN,
        )
        .all()
    )
    out: list[AutopilotPreviewItem] = []
    for rec in open_recs:
        v = autopilot_service.evaluate_recommendation(db, rec=rec, config=config)
        out.append(
            AutopilotPreviewItem(
                recommendation_id=str(rec.id),
                recommendation_type=rec.recommendation_type,
                risk_level=rec.risk_level,
                allow=v.allow,
                reason=v.reason,
                matched_rules=v.matched_rules,
            )
        )
    return out
