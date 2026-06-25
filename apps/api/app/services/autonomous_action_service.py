"""Agent → executable-action bridge for autonomous ad operations.

The AI agents emit *advisory* recommendations (descriptive findings). This
service turns real campaign signals into **executable** recommendations — ones
carrying the `{provider, action, external_id, external_account_id, payload}`
action plan the execution layer dispatches — so the autopilot scan can run them
unattended within the existing guardrails.

It only *creates* OPEN recommendations (+ pending approvals). It never executes:
the autopilot loop (`autopilot_service.auto_approve_pending`) applies the risk
ceiling / spend caps / stop-loss and executes, exactly as for human-originated
actions. Generation is gated on the workspace's `allowed_action_types`, so an
admin enables each autonomy tier independently:

  * `campaign.pause`         — Tier 1: stop-loss (spend-down), LOW risk
  * `campaign.update_budget` — Tier 1 (decrease) + Tier 2 (small increase)
  * `ad_set.create` / `ad.create` — Tier 3: publish human-built drafts, MEDIUM

Detectors are data-driven off synced campaigns + `campaign_metrics` (no
fabricated signals); a per-(target, action) 24h cooldown prevents runaway loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.ad import Ad
from app.models.ad_group import AdGroup, AdObjectSource
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.approval import Approval, ApprovalStatus
from app.models.autopilot_config import AutopilotConfig
from app.models.campaign import Campaign, CampaignStatus
from app.models.creative import Creative
from app.models.recommendation import Recommendation, RecommendationStatus, RiskLevel
from app.services import ad_publish_service, metrics_service

log = get_logger(__name__)

ACTION_PAUSE = "campaign.pause"
ACTION_UPDATE_BUDGET = "campaign.update_budget"
ACTION_AD_SET_CREATE = "ad_set.create"
ACTION_AD_CREATE = "ad.create"

AUTONOMOUS_ACTION_TYPES = [
    ACTION_PAUSE,
    ACTION_UPDATE_BUDGET,
    ACTION_AD_SET_CREATE,
    ACTION_AD_CREATE,
]

_PUBLISHABLE_PROVIDERS = {"meta_ads", "google_ads", "linkedin_ads"}

# --- Detector tunables -----------------------------------------------------
# A campaign needs at least this much recent spend before a signal is trusted.
_MIN_SPEND_FOR_SIGNAL_CENTS = 5_000  # $50 over the recent window
# Trim budget when recent CPA is this many times the trailing baseline.
_OVERSPEND_CPA_MULTIPLE = 1.5
_BUDGET_TRIM_PCT = 25  # reduce by 25%
# Scale when recent ROAS clears this and conversions clear the config threshold.
_SCALE_ROAS_MIN = 2.0
_DEFAULT_SCALE_PCT = 20  # default increase when config has no cap
_DEFAULT_MIN_CONVERSIONS = 5
_COOLDOWN_HOURS = 24


@dataclass
class ActionCandidate:
    provider: str
    action: str
    risk: RiskLevel
    title: str
    summary: str
    expected_impact: str
    suggested_action: str
    payload: dict
    dedup_key: str
    external_id: str | None = None
    external_account_id: str | None = None
    campaign_id: UUID | None = None
    metadata_extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def _active_campaigns(db: Session, workspace_id: UUID) -> list[Campaign]:
    return (
        db.query(Campaign)
        .filter(
            Campaign.workspace_id == workspace_id,
            Campaign.status == CampaignStatus.ACTIVE,
            Campaign.external_id.isnot(None),
            Campaign.external_account_id.isnot(None),
        )
        .all()
    )


def _detect_pause_stale(db: Session, workspace_id: UUID) -> list[ActionCandidate]:
    """Active campaigns whose end_date has passed — they keep spending against a
    finished objective. Pausing is spend-down (LOW risk)."""
    today = datetime.now(timezone.utc).date()
    out: list[ActionCandidate] = []
    for c in _active_campaigns(db, workspace_id):
        if c.end_date is None or c.end_date >= today:
            continue
        out.append(
            ActionCandidate(
                provider=c.provider,
                action=ACTION_PAUSE,
                risk=RiskLevel.LOW,
                title=f"Auto-pause past-end-date campaign: {c.name[:70]}",
                summary=(
                    f"“{c.name}” is active but its end date ({c.end_date.isoformat()}) "
                    "has passed — pause it to stop spend against a finished objective."
                ),
                expected_impact="Stops all spend on this campaign. Fully reversible.",
                suggested_action="Pause the campaign on the platform.",
                payload={},
                dedup_key=f"pause:{c.id}",
                external_id=c.external_id,
                external_account_id=c.external_account_id,
                campaign_id=c.id,
            )
        )
    return out


def _recent_kpis(db: Session, workspace_id: UUID, campaign_id: UUID, days: int) -> dict:
    return metrics_service.campaign_series(
        db, workspace_id=workspace_id, campaign_id=campaign_id, days=days
    )["totals"]


def _detect_budget_trim(db: Session, workspace_id: UUID) -> list[ActionCandidate]:
    """Stop-loss: when recent CPA deteriorates sharply versus the trailing
    baseline, trim the daily budget. Spend-down (LOW risk)."""
    out: list[ActionCandidate] = []
    for c in _active_campaigns(db, workspace_id):
        if not c.daily_budget_cents or c.daily_budget_cents <= 0:
            continue
        recent = _recent_kpis(db, workspace_id, c.id, 7)
        baseline = _recent_kpis(db, workspace_id, c.id, 30)
        if recent["spend_cents"] < _MIN_SPEND_FOR_SIGNAL_CENTS:
            continue
        rc, bc = recent["cpa_cents"], baseline["cpa_cents"]
        # Need a real baseline CPA and a real recent CPA to compare.
        if rc <= 0 or bc <= 0:
            continue
        if rc < bc * _OVERSPEND_CPA_MULTIPLE:
            continue
        new_budget = max(1, c.daily_budget_cents * (100 - _BUDGET_TRIM_PCT) // 100)
        if new_budget >= c.daily_budget_cents:
            continue
        out.append(
            ActionCandidate(
                provider=c.provider,
                action=ACTION_UPDATE_BUDGET,
                risk=RiskLevel.LOW,  # a decrease — spend-down
                title=f"Auto-trim budget on CPA spike: {c.name[:60]}",
                summary=(
                    f"“{c.name}” recent CPA (${rc / 100:,.2f}) is "
                    f"{rc / bc:.1f}× its baseline (${bc / 100:,.2f}). Trim the daily "
                    f"budget {_BUDGET_TRIM_PCT}% to ${new_budget / 100:,.2f} to limit waste."
                ),
                expected_impact="Reduces daily spend while efficiency is poor. Reversible.",
                suggested_action=f"Lower the daily budget to ${new_budget / 100:,.2f}.",
                payload={"daily_budget_cents": new_budget},
                dedup_key=f"trim:{c.id}",
                external_id=c.external_id,
                external_account_id=c.external_account_id,
                campaign_id=c.id,
                metadata_extra={
                    "prior_budget_cents": c.daily_budget_cents,
                    "recent_cpa_cents": rc,
                    "baseline_cpa_cents": bc,
                },
            )
        )
    return out


def _detect_scale_winners(
    db: Session, workspace_id: UUID, config: AutopilotConfig | None
) -> list[ActionCandidate]:
    """Scale proven winners: strong recent ROAS + enough conversions → a small
    budget increase, bounded by the autopilot per-change cap. The increase
    metadata (budget_increase_cents / pct_increase / recent_conversions) is what
    the autopilot spend guardrails evaluate."""
    pct = _DEFAULT_SCALE_PCT
    min_conv = _DEFAULT_MIN_CONVERSIONS
    if config is not None:
        if config.max_pct_increase_per_change:
            pct = min(pct, config.max_pct_increase_per_change)
        if config.min_conversion_threshold is not None:
            min_conv = config.min_conversion_threshold
    out: list[ActionCandidate] = []
    for c in _active_campaigns(db, workspace_id):
        if not c.daily_budget_cents or c.daily_budget_cents <= 0:
            continue
        recent = _recent_kpis(db, workspace_id, c.id, 7)
        if recent["spend_cents"] < _MIN_SPEND_FOR_SIGNAL_CENTS:
            continue
        if recent["roas"] < _SCALE_ROAS_MIN or recent["conversions"] < min_conv:
            continue
        increase = c.daily_budget_cents * pct // 100
        if increase <= 0:
            continue
        new_budget = c.daily_budget_cents + increase
        out.append(
            ActionCandidate(
                provider=c.provider,
                action=ACTION_UPDATE_BUDGET,
                risk=RiskLevel.MEDIUM,  # an increase — restarts/raises spend
                title=f"Auto-scale winning campaign: {c.name[:60]}",
                summary=(
                    f"“{c.name}” recent ROAS is {recent['roas']:.1f} on "
                    f"{recent['conversions']} conversions. Raise the daily budget "
                    f"{pct}% to ${new_budget / 100:,.2f} to capture more volume."
                ),
                expected_impact="Increases daily spend on a proven-efficient campaign.",
                suggested_action=f"Raise the daily budget to ${new_budget / 100:,.2f}.",
                payload={"daily_budget_cents": new_budget},
                dedup_key=f"scale:{c.id}",
                external_id=c.external_id,
                external_account_id=c.external_account_id,
                campaign_id=c.id,
                metadata_extra={
                    "prior_budget_cents": c.daily_budget_cents,
                    "budget_increase_cents": increase,
                    "pct_increase": pct,
                    "recent_conversions": recent["conversions"],
                    "recent_roas": recent["roas"],
                },
            )
        )
    return out


def _detect_publish_drafts(db: Session, workspace_id: UUID) -> list[ActionCandidate]:
    """Tier 3: publish human-built drafts that sit under a live campaign / ad
    set. Mirrors the ad_publish_service action plan, but as an OPEN rec the
    autopilot loop pushes live (MEDIUM risk, highest gate)."""
    out: list[ActionCandidate] = []

    draft_groups = (
        db.query(AdGroup)
        .filter(
            AdGroup.workspace_id == workspace_id,
            AdGroup.source == AdObjectSource.ADVANTA_DRAFT,
            AdGroup.external_id.is_(None),
        )
        .all()
    )
    for ag in draft_groups:
        campaign = db.get(Campaign, ag.campaign_id)
        if (
            campaign is None
            or campaign.provider not in _PUBLISHABLE_PROVIDERS
            or not campaign.external_id
            or not campaign.external_account_id
        ):
            continue
        out.append(
            ActionCandidate(
                provider=campaign.provider,
                action=ACTION_AD_SET_CREATE,
                risk=RiskLevel.MEDIUM,
                title=f"Auto-publish ad set “{ag.name[:50]}”",
                summary=f"Publish the draft ad set “{ag.name}” live under “{campaign.name}” (paused).",
                expected_impact="Creates a new (paused) ad set on the platform.",
                suggested_action=f"Create the ad set on {campaign.provider}.",
                payload={
                    "name": ag.name,
                    "daily_budget_cents": ag.daily_budget_cents,
                    "targeting": ag.targeting or {},
                    "status": "PAUSED",
                },
                dedup_key=f"adset:{ag.id}",
                external_id=campaign.external_id,  # parent campaign
                external_account_id=campaign.external_account_id,
                metadata_extra={"local_object_id": str(ag.id), "local_object_type": "ad_group"},
            )
        )

    draft_ads = (
        db.query(Ad)
        .filter(
            Ad.workspace_id == workspace_id,
            Ad.source == AdObjectSource.ADVANTA_DRAFT,
            Ad.external_id.is_(None),
        )
        .all()
    )
    for ad in draft_ads:
        ag = db.get(AdGroup, ad.ad_group_id)
        campaign = db.get(Campaign, ad.campaign_id)
        if ag is None or not ag.external_id or campaign is None:
            continue  # parent ad set must be live first
        if campaign.provider not in _PUBLISHABLE_PROVIDERS or not campaign.external_account_id:
            continue
        payload: dict = {"name": ad.name, "status": "PAUSED"}
        if ad.landing_page_url:
            payload["landing_page_url"] = ad.landing_page_url
        if ad.creative_id:
            creative = db.get(Creative, ad.creative_id)
            ad_publish_service.enrich_ad_payload(payload, creative, campaign.provider)
        out.append(
            ActionCandidate(
                provider=campaign.provider,
                action=ACTION_AD_CREATE,
                risk=RiskLevel.MEDIUM,
                title=f"Auto-publish ad “{ad.name[:50]}”",
                summary=f"Publish the draft ad “{ad.name}” live under ad set “{ag.name}” (paused).",
                expected_impact="Creates a new (paused) ad on the platform.",
                suggested_action=f"Create the ad on {campaign.provider}.",
                payload=payload,
                dedup_key=f"ad:{ad.id}",
                external_id=ag.external_id,  # parent ad set
                external_account_id=campaign.external_account_id,
                metadata_extra={"local_object_id": str(ad.id), "local_object_type": "ad"},
            )
        )
    return out


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------


def _recent_rec_exists(
    db: Session, *, workspace_id: UUID, dedup_key: str, action: str
) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_COOLDOWN_HOURS)
    return (
        db.query(Recommendation.id)
        .filter(
            Recommendation.workspace_id == workspace_id,
            Recommendation.recommendation_type == action,
            Recommendation.metadata_json["dedup"].astext == dedup_key,
            or_(
                Recommendation.status == RecommendationStatus.OPEN,
                Recommendation.created_at >= cutoff,
            ),
        )
        .first()
        is not None
    )


def _materialize(
    db: Session, *, workspace_id: UUID, system_actor_id: UUID, c: ActionCandidate
) -> Recommendation:
    now = datetime.now(timezone.utc)
    run = AgentRun(
        workspace_id=workspace_id,
        triggered_by_user_id=system_actor_id,
        agent_type="budget_guardian_autonomous",
        status=AgentRunStatus.SUCCEEDED,
        input_payload={"action": c.action, "dedup": c.dedup_key},
        output_payload={"recommendation_type": c.action},
        started_at=now,
        completed_at=now,
    )
    db.add(run)
    db.flush()

    metadata = {
        "provider": c.provider,
        "external_id": c.external_id,
        "external_account_id": c.external_account_id,
        "action": c.action,
        "payload": c.payload,
        "dedup": c.dedup_key,
        "source": "autonomous",
        **c.metadata_extra,
    }
    if c.campaign_id is not None:
        metadata["campaign_id"] = str(c.campaign_id)

    rec = Recommendation(
        workspace_id=workspace_id,
        agent_run_id=run.id,
        title=c.title,
        summary=c.summary,
        recommendation_type=c.action,
        risk_level=c.risk,
        expected_impact=c.expected_impact,
        suggested_action=c.suggested_action,
        status=RecommendationStatus.OPEN,
        platform=c.provider,
        metadata_json=metadata,
    )
    db.add(rec)
    db.flush()

    db.add(
        Approval(
            workspace_id=workspace_id,
            recommendation_id=rec.id,
            action_type=c.action,
            risk_level=c.risk,
            status=ApprovalStatus.PENDING,
        )
    )
    db.flush()
    return rec


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def collect_candidates(
    db: Session, *, workspace_id: UUID, config: AutopilotConfig | None
) -> list[ActionCandidate]:
    candidates: list[ActionCandidate] = []
    candidates += _detect_pause_stale(db, workspace_id)
    candidates += _detect_budget_trim(db, workspace_id)
    candidates += _detect_scale_winners(db, workspace_id, config)
    candidates += _detect_publish_drafts(db, workspace_id)
    return candidates


def generate_for_workspace(
    db: Session,
    *,
    workspace_id: UUID,
    system_actor_id: UUID,
    config: AutopilotConfig | None = None,
    only_allowed: bool = True,
) -> list[Recommendation]:
    """Run detectors and create OPEN executable recommendations for any whose
    action type the workspace has opted into (`allowed_action_types`). Skips
    duplicates within the cooldown window. Does NOT execute — the autopilot loop
    handles approval + execution under its guardrails."""
    allowed = set(config.allowed_action_types or []) if config is not None else set()
    created: list[Recommendation] = []
    for c in collect_candidates(db, workspace_id=workspace_id, config=config):
        if only_allowed and c.action not in allowed:
            continue
        if _recent_rec_exists(
            db, workspace_id=workspace_id, dedup_key=c.dedup_key, action=c.action
        ):
            continue
        created.append(
            _materialize(db, workspace_id=workspace_id, system_actor_id=system_actor_id, c=c)
        )
    if created:
        db.commit()
    return created
