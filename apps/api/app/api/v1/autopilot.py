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
from app.services import autonomous_action_service, autopilot_service

router = APIRouter()


# Catalog of action types the autonomous generator can produce, with the risk
# tier each carries — drives the allowlist UI.
AUTONOMOUS_ACTION_CATALOG = [
    {
        "action": "campaign.pause",
        "label": "Auto-pause (stop-loss)",
        "tier": "spend-down",
        "default_risk": "low",
        "description": "Pause past-end-date campaigns. Spend-down, fully reversible.",
    },
    {
        "action": "campaign.update_budget",
        "label": "Auto-adjust budget",
        "tier": "spend-down + scale",
        "default_risk": "low/medium",
        "description": "Trim budgets on CPA spikes (low risk) and scale winners within caps (medium).",
    },
    {
        "action": "ad_set.create",
        "label": "Auto-publish ad sets",
        "tier": "publish",
        "default_risk": "medium",
        "description": "Publish human-built draft ad sets under live campaigns (paused).",
    },
    {
        "action": "ad.create",
        "label": "Auto-publish ads",
        "tier": "publish",
        "default_risk": "medium",
        "description": "Publish human-built draft ads under live ad sets (paused).",
    },
]


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


class AutonomousCandidate(BaseModel):
    action: str
    risk_level: RiskLevel
    title: str
    summary: str
    allowed: bool  # whether the workspace has opted this action type in


class GenerateActionsResult(BaseModel):
    generated: int
    recommendation_ids: list[str]


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


@router.get("/{workspace_id}/autopilot/action-types")
def list_autonomous_action_types(
    _member: WorkspaceMember = Depends(get_current_member),
) -> list[dict]:
    """Catalog of action types the autonomous generator can produce, for the
    allowlist UI."""
    return AUTONOMOUS_ACTION_CATALOG


@router.get(
    "/{workspace_id}/autopilot/candidates",
    response_model=list[AutonomousCandidate],
)
def preview_autonomous_candidates(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AutonomousCandidate]:
    """What the autonomous generator would create right now from live campaign
    signals — without writing anything. `allowed` reflects the current
    allowlist."""
    config = autopilot_service.get_or_create_config(db, workspace_id=workspace_id)
    allowed = set(config.allowed_action_types or [])
    candidates = autonomous_action_service.collect_candidates(
        db, workspace_id=workspace_id, config=config
    )
    return [
        AutonomousCandidate(
            action=c.action,
            risk_level=c.risk,
            title=c.title,
            summary=c.summary,
            allowed=c.action in allowed,
        )
        for c in candidates
    ]


@router.post(
    "/{workspace_id}/autopilot/generate",
    response_model=GenerateActionsResult,
)
def generate_autonomous_actions(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> GenerateActionsResult:
    """Run the autonomous generator now (owner-only). Creates OPEN executable
    recommendations for opted-in action types; execution still goes through the
    autopilot guardrails (or manual approval). Lets an admin seed/test autonomy
    without waiting for the 15-minute beat."""
    require_role_at_least(member.role, Role.OWNER)
    config = autopilot_service.get_or_create_config(db, workspace_id=workspace_id)
    created = autonomous_action_service.generate_for_workspace(
        db,
        workspace_id=workspace_id,
        system_actor_id=member.user_id,
        config=config,
    )
    return GenerateActionsResult(
        generated=len(created),
        recommendation_ids=[str(r.id) for r in created],
    )
