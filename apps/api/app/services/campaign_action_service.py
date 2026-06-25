"""User-initiated campaign actions (pause / resume / edit budget).

This is the "manage your campaigns from the app" path. It deliberately reuses
the existing safety + write stack rather than calling providers directly:

    user clicks Pause
      -> create a manual AgentRun + Recommendation (carries the action plan)
      -> create a pending Approval (audit trail, money-movement rule compliance)
      -> if the actor's role can approve this risk level  -> approve + execute
         (recommendation_service.approve_recommendation -> execution_service ->
          real provider write), with optimistic local status update
         else                                              -> leave it queued
                                                              for someone with
                                                              the required role.

Every action therefore always produces an Approval record and audit log, which
satisfies the CLAUDE.md rule that money-moving / campaign-modifying actions go
through approval. "One-click if permitted" simply means the authorized actor
supplies that approval in the same request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalStatus
from app.models.audit_log import AuditActorType
from app.models.campaign import Campaign, CampaignStatus
from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    RiskLevel,
)
from app.models.recommendation_execution import (
    ExecutionStatus,
    RecommendationExecution,
)
from app.security.permissions import Role, role_at_least
from app.services import audit_service, recommendation_service

# Action identifiers — must match execution_service.SUPPORTED_ACTIONS.
ACTION_PAUSE = "campaign.pause"
ACTION_RESUME = "campaign.resume"
ACTION_UPDATE_BUDGET = "campaign.update_budget"
MANAGEABLE_ACTIONS = {ACTION_PAUSE, ACTION_RESUME, ACTION_UPDATE_BUDGET}

# Above this single-change increase we treat a budget bump as HIGH risk.
_PCT_INCREASE_MEDIUM_CEILING = 25


class CampaignNotFoundError(AdVantaError):
    status_code = 404
    code = "campaign_not_found"


class CampaignNotManageableError(AdVantaError):
    status_code = 422
    code = "campaign_not_manageable"


class InvalidCampaignActionError(AdVantaError):
    status_code = 409
    code = "invalid_campaign_action"


@dataclass
class CampaignActionResult:
    status: str  # "executed" | "failed" | "queued"
    action: str
    risk_level: RiskLevel
    required_role: Role
    recommendation: Recommendation
    approval: Approval
    execution: RecommendationExecution | None
    campaign: Campaign
    message: str


# ---------------------------------------------------------------------------
# Risk model — spend-direction aware. Reducing/stopping spend is low risk;
# restarting or increasing spend is gated harder. Every action still records an
# approval, so this only decides who may one-click vs who must queue it.
# ---------------------------------------------------------------------------

def _risk_for(
    action: str, *, current_budget_cents: int | None, new_budget_cents: int | None
) -> RiskLevel:
    if action == ACTION_PAUSE:
        return RiskLevel.LOW  # stops spend, fully reversible
    if action == ACTION_RESUME:
        return RiskLevel.MEDIUM  # restarts spend
    if action == ACTION_UPDATE_BUDGET:
        if current_budget_cents and new_budget_cents and new_budget_cents <= current_budget_cents:
            return RiskLevel.LOW  # a decrease
        if current_budget_cents and new_budget_cents:
            pct = (new_budget_cents - current_budget_cents) / current_budget_cents * 100
            return RiskLevel.MEDIUM if pct <= _PCT_INCREASE_MEDIUM_CEILING else RiskLevel.HIGH
        # Setting a budget where none was known — treat as a meaningful increase.
        return RiskLevel.HIGH
    return RiskLevel.HIGH


def _fmt_money(cents: int | None, currency: str | None) -> str:
    if cents is None:
        return "—"
    symbol = "$" if (currency in (None, "USD")) else f"{currency} "
    return f"{symbol}{cents / 100:,.2f}"


def _action_copy(
    action: str,
    campaign: Campaign,
    *,
    current_budget_cents: int | None,
    new_budget_cents: int | None,
) -> tuple[str, str, str, str, dict]:
    """Returns (title, summary, expected_impact, suggested_action, payload)."""
    name = campaign.name or "campaign"
    cur = _fmt_money(current_budget_cents, campaign.currency)
    if action == ACTION_PAUSE:
        return (
            f"Pause “{name}”",
            f"Pause the {campaign.provider} campaign “{name}”. Spend stops until it is resumed.",
            "Stops all spend on this campaign immediately. Fully reversible.",
            "Pause the campaign on the platform.",
            {},
        )
    if action == ACTION_RESUME:
        return (
            f"Resume “{name}”",
            f"Resume the {campaign.provider} campaign “{name}”. It will start spending again at {cur}/day.",
            "Restarts delivery and spend on this campaign.",
            "Resume (enable) the campaign on the platform.",
            {},
        )
    # update_budget
    new = _fmt_money(new_budget_cents, campaign.currency)
    direction = "increase" if (not current_budget_cents or (new_budget_cents or 0) > current_budget_cents) else "decrease"
    return (
        f"Set “{name}” daily budget to {new}",
        f"Change the daily budget of the {campaign.provider} campaign “{name}” from {cur} to {new}.",
        f"A budget {direction} changes daily spend and delivery volume.",
        f"Update the campaign daily budget to {new} on the platform.",
        {"daily_budget_cents": new_budget_cents},
    )


def _apply_local_status(
    campaign: Campaign, action: str, new_budget_cents: int | None
) -> None:
    """Optimistically reflect a SUCCEEDED platform write locally so the UI
    updates immediately; the next sync reconciles with the source of truth."""
    if action == ACTION_PAUSE:
        campaign.status = CampaignStatus.PAUSED
    elif action == ACTION_RESUME:
        campaign.status = CampaignStatus.ACTIVE
    elif action == ACTION_UPDATE_BUDGET and new_budget_cents:
        campaign.daily_budget_cents = new_budget_cents


def create_campaign_action(
    db: Session,
    *,
    workspace_id: UUID,
    campaign_id: UUID,
    action: str,
    actor_user_id: UUID,
    actor_role: Role,
    new_daily_budget_cents: int | None = None,
    request: Request | None = None,
) -> CampaignActionResult:
    if action not in MANAGEABLE_ACTIONS:
        raise InvalidCampaignActionError(
            f"Unsupported campaign action `{action}`. Supported: {sorted(MANAGEABLE_ACTIONS)}."
        )

    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.workspace_id == workspace_id)
        .first()
    )
    if campaign is None:
        raise CampaignNotFoundError("Campaign not found in this workspace.")
    if not campaign.external_id or not campaign.external_account_id:
        raise CampaignNotManageableError(
            "Campaign is missing its platform identifiers — re-sync the account before managing it."
        )

    current_budget = campaign.daily_budget_cents

    # State + input guards.
    if action == ACTION_PAUSE and campaign.status == CampaignStatus.PAUSED:
        raise InvalidCampaignActionError("Campaign is already paused.")
    if action == ACTION_RESUME and campaign.status == CampaignStatus.ACTIVE:
        raise InvalidCampaignActionError("Campaign is already active.")
    if action == ACTION_UPDATE_BUDGET:
        if not isinstance(new_daily_budget_cents, int) or new_daily_budget_cents <= 0:
            raise InvalidCampaignActionError(
                "A positive daily_budget_cents is required for a budget change."
            )
        if current_budget is not None and new_daily_budget_cents == current_budget:
            raise InvalidCampaignActionError(
                "The new daily budget matches the current budget."
            )

    risk = _risk_for(
        action, current_budget_cents=current_budget, new_budget_cents=new_daily_budget_cents
    )
    title, summary, impact, suggested, payload = _action_copy(
        action,
        campaign,
        current_budget_cents=current_budget,
        new_budget_cents=new_daily_budget_cents,
    )

    metadata = {
        "provider": campaign.provider,
        "external_id": campaign.external_id,
        "external_account_id": campaign.external_account_id,
        "action": action,
        "payload": payload,
        "campaign_id": str(campaign.id),
        "source": "manual",
    }

    now = datetime.now(timezone.utc)
    run = AgentRun(
        workspace_id=workspace_id,
        triggered_by_user_id=actor_user_id,
        agent_type="manual_campaign_action",
        status=AgentRunStatus.SUCCEEDED,
        input_payload={
            "action": action,
            "campaign_id": str(campaign.id),
            "daily_budget_cents": new_daily_budget_cents,
        },
        output_payload={"recommendation_type": action},
        started_at=now,
        completed_at=now,
    )
    db.add(run)
    db.flush()

    rec = Recommendation(
        workspace_id=workspace_id,
        agent_run_id=run.id,
        title=title,
        summary=summary,
        recommendation_type=action,
        risk_level=risk,
        expected_impact=impact,
        suggested_action=suggested,
        status=RecommendationStatus.OPEN,
        platform=campaign.provider,
        metadata_json=metadata,
    )
    db.add(rec)
    db.flush()

    approval = Approval(
        workspace_id=workspace_id,
        recommendation_id=rec.id,
        action_type=action,
        risk_level=risk,
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    db.flush()

    required_role = recommendation_service.RISK_TO_MIN_ROLE[risk]

    # --- Queue path: actor can't approve this risk level ------------------
    if not role_at_least(actor_role, required_role):
        audit_service.log_event(
            db,
            workspace_id=workspace_id,
            actor_type=AuditActorType.USER,
            actor_id=actor_user_id,
            action="campaign.action.queued",
            resource_type="recommendation",
            resource_id=rec.id,
            metadata={
                "campaign_id": str(campaign.id),
                "action": action,
                "risk_level": risk.value,
                "required_role": required_role.value,
            },
            request=request,
        )
        db.commit()
        db.refresh(rec)
        db.refresh(approval)
        db.refresh(campaign)
        return CampaignActionResult(
            status="queued",
            action=action,
            risk_level=risk,
            required_role=required_role,
            recommendation=rec,
            approval=approval,
            execution=None,
            campaign=campaign,
            message=(
                f"This {risk.value}-risk change needs {required_role.value} approval. "
                "It's queued in Recommendations for sign-off."
            ),
        )

    # --- One-click path: actor is authorized -> approve + execute now -----
    rec, execution = recommendation_service.approve_recommendation(
        db,
        workspace_id=workspace_id,
        recommendation_id=rec.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        request=request,
        auto_execute=True,
        audit_action="campaign.action.executed",
        audit_metadata_extra={"campaign_id": str(campaign.id), "action": action},
    )

    succeeded = execution is not None and execution.status == ExecutionStatus.SUCCEEDED
    if succeeded:
        _apply_local_status(campaign, action, new_daily_budget_cents)
        db.commit()
    db.refresh(campaign)

    if succeeded:
        message = "Done — the change was applied on the platform."
        status = "executed"
    elif execution is not None and execution.status == ExecutionStatus.FAILED:
        status = "failed"
        message = (
            "Approved, but the platform write failed: "
            f"{execution.error_message or 'unknown error'}. "
            "Fix the issue (e.g. connect the account) and retry."
        )
    else:
        # No execution attempted (shouldn't happen for these actions, but be honest).
        status = "queued"
        message = "Approved. Execution is pending."

    return CampaignActionResult(
        status=status,
        action=action,
        risk_level=risk,
        required_role=required_role,
        recommendation=rec,
        approval=rec.approval,
        execution=execution,
        campaign=campaign,
        message=message,
    )
