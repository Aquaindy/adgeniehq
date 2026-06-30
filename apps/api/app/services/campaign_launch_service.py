"""Campaign launch (Phase 2) — create + launch a new campaign from the app.

Reuses the same approval + execution stack as campaign management: a launch is
a `campaign.create` recommendation. On a successful platform write, the
execution service materializes the local Campaign row and accrues the one-time
listing fee (see execution_service._materialize_created_campaign), so both the
one-click and queued-then-approved paths stay consistent.

Campaigns are launched PAUSED/DRAFT for safety — the operator resumes them via
the existing manage controls once they're happy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdGenieError
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalStatus
from app.models.audit_log import AuditActorType
from app.models.campaign import Campaign
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.recommendation import Recommendation, RecommendationStatus, RiskLevel
from app.models.recommendation_execution import ExecutionStatus, RecommendationExecution
from app.security.permissions import Role, role_at_least
from app.services import audit_service, recommendation_service

LAUNCHABLE_PROVIDERS = {"meta_ads", "google_ads", "linkedin_ads"}
ACTION_CREATE = "campaign.create"
# Launching starts new spend → requires approval (admin one-click, marketer queues).
LAUNCH_RISK = RiskLevel.MEDIUM


class ProviderNotConnectedError(AdGenieError):
    status_code = 409
    code = "provider_not_connected"


class InvalidLaunchError(AdGenieError):
    status_code = 422
    code = "invalid_launch"


# Map our coarse campaign_type to each platform's objective vocabulary.
_META_OBJECTIVE = {
    "leads": "OUTCOME_LEADS",
    "sales": "OUTCOME_SALES",
    "traffic": "OUTCOME_TRAFFIC",
    "awareness": "OUTCOME_AWARENESS",
    "engagement": "OUTCOME_ENGAGEMENT",
    "app": "OUTCOME_APP_PROMOTION",
}
_LINKEDIN_OBJECTIVE = {
    "leads": "LEAD_GENERATION",
    "sales": "WEBSITE_CONVERSION",
    "traffic": "WEBSITE_VISIT",
    "awareness": "BRAND_AWARENESS",
    "engagement": "ENGAGEMENT",
}


def build_create_payload(
    provider: str, *, name: str, campaign_type: str, daily_budget_cents: int
) -> dict:
    if provider == "meta_ads":
        return {
            "name": name,
            "objective": _META_OBJECTIVE.get(campaign_type, "OUTCOME_LEADS"),
            "status": "PAUSED",
            "special_ad_categories": [],
        }
    if provider == "google_ads":
        return {
            "name": name,
            "daily_budget_cents": daily_budget_cents,
            "advertising_channel_type": "DISPLAY" if campaign_type == "awareness" else "SEARCH",
            "status": "PAUSED",
        }
    if provider == "linkedin_ads":
        return {
            "name": name,
            "objective": _LINKEDIN_OBJECTIVE.get(campaign_type, "LEAD_GENERATION"),
            "type": "TEXT_AD",
            "cost_type": "CPM",
            "status": "DRAFT",
            "daily_budget_cents": daily_budget_cents,
            "currency": "USD",
        }
    raise InvalidLaunchError(f"Provider `{provider}` does not support launching from AdGenieHQ.")


@dataclass
class LaunchResult:
    status: str  # "executed" | "failed" | "queued"
    risk_level: RiskLevel
    required_role: Role
    recommendation: Recommendation
    approval: Approval
    execution: RecommendationExecution | None
    campaign: Campaign | None
    message: str


def _normalize_google_customer_id(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) != 10:
        raise InvalidLaunchError(
            "Enter a valid Google Ads account ID — 10 digits, e.g. 959-335-5662."
        )
    return digits


def _resolve_target_account_id(
    db: Session, *, provider: str, account: ConnectedAccount, requested: str | None
) -> str:
    """Resolve which ad-account id to publish into.

    Google Ads is special: the connected account stores the OAuth *user* id
    (from userinfo), NOT an Ads customer id — so we never use
    provider_account_id there. The operator can pass the customer id
    explicitly; otherwise we try to auto-resolve a single accessible
    (non-manager) account, and ask them to pick if it's ambiguous. Meta and
    LinkedIn already persist the ad-account id as provider_account_id.
    """
    if provider == "google_ads":
        if requested:
            return _normalize_google_customer_id(requested)
        # Deferred imports avoid an import cycle and keep the provider optional.
        from app.integrations.google_ads import GoogleAdsProvider
        from app.services import integration_service

        try:
            token = integration_service.get_fresh_access_token(db, account=account)
            accounts = GoogleAdsProvider.list_ad_accounts(access_token=token)
        except Exception:
            accounts = []
        if len(accounts) == 1:
            return accounts[0]["id"]
        raise InvalidLaunchError(
            "Couldn't determine which Google Ads account to launch into. Enter your "
            "Google Ads account ID (10 digits, e.g. 959-335-5662) in the launch form."
        )

    if requested:
        return requested.strip()
    if not account.provider_account_id:
        raise InvalidLaunchError(
            f"The connected {provider} account has no ad-account id on record — "
            "reconnect the integration and try again."
        )
    return account.provider_account_id


def launch_campaign(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    provider: str,
    name: str,
    campaign_type: str,
    daily_budget_cents: int,
    external_account_id: str | None = None,
    request: Request | None = None,
) -> LaunchResult:
    if provider not in LAUNCHABLE_PROVIDERS:
        raise InvalidLaunchError(
            f"Unsupported provider `{provider}`. Launchable: {sorted(LAUNCHABLE_PROVIDERS)}."
        )
    name = (name or "").strip()
    if not name:
        raise InvalidLaunchError("Campaign name is required.")
    if not isinstance(daily_budget_cents, int) or daily_budget_cents <= 0:
        raise InvalidLaunchError("A positive daily budget is required.")
    campaign_type = (campaign_type or "other").strip().lower()

    account = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == provider,
            ConnectedAccount.status == ConnectionStatus.CONNECTED,
        )
        .first()
    )
    if account is None:
        raise ProviderNotConnectedError(
            f"{provider} is not connected — connect it before launching a campaign."
        )

    target_account_id = _resolve_target_account_id(
        db, provider=provider, account=account, requested=external_account_id
    )

    payload = build_create_payload(
        provider, name=name, campaign_type=campaign_type, daily_budget_cents=daily_budget_cents
    )
    metadata = {
        "provider": provider,
        "external_account_id": target_account_id,
        "action": ACTION_CREATE,
        "payload": payload,
        "daily_budget_cents": daily_budget_cents,
        "campaign_type": campaign_type,
        "connected_account_id": str(account.id),
        "source": "manual_launch",
    }

    now = datetime.now(timezone.utc)
    run = AgentRun(
        workspace_id=workspace_id,
        triggered_by_user_id=actor_user_id,
        agent_type="manual_campaign_launch",
        status=AgentRunStatus.SUCCEEDED,
        input_payload={
            "provider": provider,
            "name": name,
            "campaign_type": campaign_type,
            "daily_budget_cents": daily_budget_cents,
        },
        output_payload={"recommendation_type": ACTION_CREATE},
        started_at=now,
        completed_at=now,
    )
    db.add(run)
    db.flush()

    rec = Recommendation(
        workspace_id=workspace_id,
        agent_run_id=run.id,
        title=f"Launch “{name}” on {provider}",
        summary=(
            f"Create and launch a new {provider} {campaign_type} campaign “{name}” at "
            f"${daily_budget_cents / 100:,.2f}/day. It launches paused for review."
        ),
        recommendation_type=ACTION_CREATE,
        risk_level=LAUNCH_RISK,
        expected_impact="Starts a new campaign (paused) on the connected ad account.",
        suggested_action=f"Create the campaign on {provider} and add it to AdGenieHQ.",
        status=RecommendationStatus.OPEN,
        platform=provider,
        metadata_json=metadata,
    )
    db.add(rec)
    db.flush()

    approval = Approval(
        workspace_id=workspace_id,
        recommendation_id=rec.id,
        action_type=ACTION_CREATE,
        risk_level=LAUNCH_RISK,
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    db.flush()

    required_role = recommendation_service.RISK_TO_MIN_ROLE[LAUNCH_RISK]

    if not role_at_least(actor_role, required_role):
        audit_service.log_event(
            db,
            workspace_id=workspace_id,
            actor_type=AuditActorType.USER,
            actor_id=actor_user_id,
            action="campaign.launch.queued",
            resource_type="recommendation",
            resource_id=rec.id,
            metadata={"provider": provider, "name": name, "required_role": required_role.value},
            request=request,
        )
        db.commit()
        db.refresh(rec)
        db.refresh(approval)
        return LaunchResult(
            status="queued",
            risk_level=LAUNCH_RISK,
            required_role=required_role,
            recommendation=rec,
            approval=approval,
            execution=None,
            campaign=None,
            message=(
                f"Launching needs {required_role.value} approval. "
                "It's queued in Recommendations for sign-off."
            ),
        )

    rec, execution = recommendation_service.approve_recommendation(
        db,
        workspace_id=workspace_id,
        recommendation_id=rec.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        request=request,
        auto_execute=True,
        audit_action="campaign.launch.executed",
        audit_metadata_extra={"provider": provider, "name": name},
    )

    campaign: Campaign | None = None
    if execution is not None and execution.status == ExecutionStatus.SUCCEEDED:
        new_external_id = (execution.result or {}).get("external_id")
        if new_external_id:
            campaign = (
                db.query(Campaign)
                .filter(
                    Campaign.workspace_id == workspace_id,
                    Campaign.provider == provider,
                    Campaign.external_id == str(new_external_id),
                )
                .first()
            )
        status = "executed"
        message = f"Launched “{name}” (paused) on {provider}. Resume it when you're ready."
    elif execution is not None and execution.status == ExecutionStatus.FAILED:
        status = "failed"
        message = (
            "Approved, but the platform rejected the launch: "
            f"{execution.error_message or 'unknown error'}."
        )
    else:
        status = "queued"
        message = "Approved. Execution is pending."

    return LaunchResult(
        status=status,
        risk_level=LAUNCH_RISK,
        required_role=required_role,
        recommendation=rec,
        approval=rec.approval,
        execution=execution,
        campaign=campaign,
        message=message,
    )
