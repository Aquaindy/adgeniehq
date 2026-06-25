"""Publish ad-structure drafts to the ad platform.

Takes an `advanta_draft` ad group or ad and pushes it live via the same
recommendation → approval → execution stack as campaign launch. On success the
execution service writes the new platform `external_id` back onto the local row
and flips it to `platform_synced` (see execution_service._materialize_published_ad_object).

Objects are created PAUSED for safety. Publishing is MEDIUM risk: an admin can
one-click; a marketer's request queues for approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.ad import Ad
from app.models.ad_group import AdGroup, AdObjectSource
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalStatus
from app.models.audit_log import AuditActorType
from app.models.campaign import Campaign
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.creative import Creative
from app.models.recommendation import Recommendation, RecommendationStatus, RiskLevel
from app.models.recommendation_execution import ExecutionStatus, RecommendationExecution
from app.security.permissions import Role, role_at_least
from app.services import audit_service, recommendation_service
from app.services.ad_builder_service import AdGroupNotFoundError, AdNotFoundError

PUBLISHABLE_PROVIDERS = {"meta_ads", "google_ads", "linkedin_ads"}
PUBLISH_RISK = RiskLevel.MEDIUM


def enrich_ad_payload(payload: dict, creative: Creative | None, provider: str) -> None:
    """Attach the creative content each provider's create_ad needs.

    Meta uses a pre-existing platform creative_id; Google builds a responsive
    search ad from headlines/descriptions; LinkedIn sponsors an existing share
    URN. We never fabricate a platform creative — if a provider needs something
    that isn't present, its create_ad raises a clear, actionable error."""
    if creative is None:
        return
    meta = creative.metadata_json or {}
    ext = meta.get("external_ids") or {}
    cid = ext.get(provider) or meta.get("creative_id")
    if cid:
        payload["creative_id"] = str(cid)
    if provider == "linkedin_ads":
        share = ext.get("linkedin_share") or meta.get("share_urn")
        if share:
            payload["share_urn"] = share
    if creative.headline:
        payload.setdefault("headlines", [creative.headline])
    descriptions = [d for d in (creative.primary_text, creative.description) if d]
    if descriptions:
        payload.setdefault("descriptions", descriptions)


class InvalidPublishError(AdVantaError):
    status_code = 422
    code = "invalid_publish"


class AlreadyPublishedError(AdVantaError):
    status_code = 409
    code = "already_published"


class ProviderNotConnectedError(AdVantaError):
    status_code = 409
    code = "provider_not_connected"


@dataclass
class PublishResult:
    status: str  # "executed" | "failed" | "queued"
    object_type: str  # "ad_group" | "ad"
    risk_level: RiskLevel
    required_role: Role
    recommendation: Recommendation
    approval: Approval
    execution: RecommendationExecution | None
    external_id: str | None
    message: str


def _connected_account(db: Session, *, workspace_id: UUID, provider: str) -> ConnectedAccount:
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
            f"{provider} is not connected — connect it before publishing."
        )
    return account


def _route_through_approval(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    object_type: str,
    action: str,
    title: str,
    summary: str,
    provider: str,
    metadata: dict,
    request: Request | None,
) -> PublishResult:
    now = datetime.now(timezone.utc)
    run = AgentRun(
        workspace_id=workspace_id,
        triggered_by_user_id=actor_user_id,
        agent_type="manual_ad_publish",
        status=AgentRunStatus.SUCCEEDED,
        input_payload={"action": action, "metadata": metadata},
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
        risk_level=PUBLISH_RISK,
        expected_impact="Creates a new (paused) ad object on the connected ad account.",
        suggested_action=f"Create the {object_type.replace('_', ' ')} on {provider}.",
        status=RecommendationStatus.OPEN,
        platform=provider,
        metadata_json=metadata,
    )
    db.add(rec)
    db.flush()

    approval = Approval(
        workspace_id=workspace_id,
        recommendation_id=rec.id,
        action_type=action,
        risk_level=PUBLISH_RISK,
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    db.flush()

    required_role = recommendation_service.RISK_TO_MIN_ROLE[PUBLISH_RISK]

    if not role_at_least(actor_role, required_role):
        audit_service.log_event(
            db,
            workspace_id=workspace_id,
            actor_type=AuditActorType.USER,
            actor_id=actor_user_id,
            action="ad_publish.queued",
            resource_type="recommendation",
            resource_id=rec.id,
            metadata={"action": action, "required_role": required_role.value},
            request=request,
        )
        db.commit()
        db.refresh(rec)
        db.refresh(approval)
        return PublishResult(
            status="queued",
            object_type=object_type,
            risk_level=PUBLISH_RISK,
            required_role=required_role,
            recommendation=rec,
            approval=approval,
            execution=None,
            external_id=None,
            message=(
                f"Publishing needs {required_role.value} approval. "
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
        audit_action="ad_publish.executed",
        audit_metadata_extra={"action": action},
    )

    external_id = None
    if execution is not None and execution.status == ExecutionStatus.SUCCEEDED:
        external_id = (execution.result or {}).get("external_id")
        status = "executed"
        message = f"Published the {object_type.replace('_', ' ')} (paused) on {provider}."
    elif execution is not None and execution.status == ExecutionStatus.FAILED:
        status = "failed"
        message = (
            "Approved, but the platform rejected the publish: "
            f"{execution.error_message or 'unknown error'}."
        )
    else:
        status = "queued"
        message = "Approved. Execution is pending."

    return PublishResult(
        status=status,
        object_type=object_type,
        risk_level=PUBLISH_RISK,
        required_role=required_role,
        recommendation=rec,
        approval=rec.approval,
        execution=execution,
        external_id=str(external_id) if external_id else None,
        message=message,
    )


def publish_ad_group(
    db: Session,
    *,
    workspace_id: UUID,
    ad_group_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> PublishResult:
    ag = (
        db.query(AdGroup)
        .filter(AdGroup.id == ad_group_id, AdGroup.workspace_id == workspace_id)
        .first()
    )
    if ag is None:
        raise AdGroupNotFoundError("Ad group not found in this workspace.")
    if ag.source != AdObjectSource.ADVANTA_DRAFT or ag.external_id:
        raise AlreadyPublishedError("This ad group is already live on the platform.")

    campaign = db.get(Campaign, ag.campaign_id)
    if campaign is None or campaign.workspace_id != workspace_id:
        raise InvalidPublishError("Parent campaign not found.")
    if not campaign.external_id or not campaign.external_account_id:
        raise InvalidPublishError(
            "The parent campaign isn't on a platform yet — launch it before "
            "publishing ad sets under it."
        )
    provider = campaign.provider
    if provider not in PUBLISHABLE_PROVIDERS:
        raise InvalidPublishError(f"Provider `{provider}` does not support publishing ad sets.")
    _connected_account(db, workspace_id=workspace_id, provider=provider)

    payload = {
        "name": ag.name,
        "daily_budget_cents": ag.daily_budget_cents,
        "targeting": ag.targeting or {},
        "status": "PAUSED",
    }
    metadata = {
        "provider": provider,
        "external_account_id": campaign.external_account_id,
        "external_id": campaign.external_id,  # parent campaign
        "action": "ad_set.create",
        "payload": payload,
        "local_object_id": str(ag.id),
        "local_object_type": "ad_group",
        "source": "ad_builder_publish",
    }
    return _route_through_approval(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        object_type="ad_group",
        action="ad_set.create",
        title=f"Publish ad set “{ag.name}” to {provider}",
        summary=(
            f"Create the ad set “{ag.name}” under campaign “{campaign.name}” on "
            f"{provider}. It launches paused for review."
        ),
        provider=provider,
        metadata=metadata,
        request=request,
    )


def publish_ad(
    db: Session,
    *,
    workspace_id: UUID,
    ad_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> PublishResult:
    ad = (
        db.query(Ad)
        .filter(Ad.id == ad_id, Ad.workspace_id == workspace_id)
        .first()
    )
    if ad is None:
        raise AdNotFoundError("Ad not found in this workspace.")
    if ad.source != AdObjectSource.ADVANTA_DRAFT or ad.external_id:
        raise AlreadyPublishedError("This ad is already live on the platform.")

    ag = db.get(AdGroup, ad.ad_group_id)
    if ag is None:
        raise InvalidPublishError("Parent ad group not found.")
    if not ag.external_id:
        raise InvalidPublishError(
            "The parent ad set isn't on the platform yet — publish it first."
        )
    campaign = db.get(Campaign, ad.campaign_id)
    if campaign is None or campaign.workspace_id != workspace_id:
        raise InvalidPublishError("Parent campaign not found.")
    provider = campaign.provider
    if provider not in PUBLISHABLE_PROVIDERS:
        raise InvalidPublishError(f"Provider `{provider}` does not support publishing ads.")
    _connected_account(db, workspace_id=workspace_id, provider=provider)

    payload: dict = {"name": ad.name, "status": "PAUSED"}
    if ad.landing_page_url:
        payload["landing_page_url"] = ad.landing_page_url

    # Attach the creative content the provider's create_ad needs (existing
    # platform creative id for Meta, copy for Google, share URN for LinkedIn).
    if ad.creative_id:
        creative = db.get(Creative, ad.creative_id)
        enrich_ad_payload(payload, creative, provider)

    metadata = {
        "provider": provider,
        "external_account_id": campaign.external_account_id,
        "external_id": ag.external_id,  # parent ad set
        "action": "ad.create",
        "payload": payload,
        "local_object_id": str(ad.id),
        "local_object_type": "ad",
        "source": "ad_builder_publish",
    }
    return _route_through_approval(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        object_type="ad",
        action="ad.create",
        title=f"Publish ad “{ad.name}” to {provider}",
        summary=f"Create the ad “{ad.name}” under ad set “{ag.name}” on {provider} (paused).",
        provider=provider,
        metadata=metadata,
        request=request,
    )
