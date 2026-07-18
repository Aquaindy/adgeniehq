"""Billing orchestration: PayPal checkout/portal + webhook processing,
plan-limit enforcement, and usage tracking.

Recurring subscriptions are billed exclusively through **PayPal** (server-created
subscription + redirect approval). One-off platform *fees* are a separate,
provider-agnostic system (see `app.payments` / `fee_billing_service`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.plans import (
    BillingNotConfiguredError,
    PLANS,
    Plan,
    UnknownPlanError,
    get_plan,
)
from app.core.exceptions import AdGenieError
from app.core.logging import get_logger
from app.core.config import settings
from app.core.superuser_context import is_superuser_request
from app.integrations import paypal_billing
from app.models.billing_subscription import (
    BillingSubscription,
    SubscriptionSource,
    SubscriptionStatus,
)
from app.models.processed_webhook_event import ProcessedWebhookEvent
from app.models.usage_event import UsageEvent, UsageEventType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_invitation import InvitationStatus, WorkspaceInvitation
from app.models.workspace_member import WorkspaceMember
from app.security.permissions import MemberStatus

log = get_logger(__name__)


class PlanLimitExceededError(AdGenieError):
    status_code = 402
    code = "plan_limit_exceeded"


class InsufficientCreditsError(AdGenieError):
    status_code = 402
    code = "insufficient_credits"


# ---------------------------------------------------------------------------
# Plan resolution + status
# ---------------------------------------------------------------------------


def _ensure_subscription(db: Session, *, workspace_id: UUID) -> BillingSubscription:
    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    if sub is not None:
        return sub
    # No subscription row yet → return an un-persisted free record purely for
    # limit lookups. PayPal creates the real row on the first webhook.
    return BillingSubscription(
        workspace_id=workspace_id,
        plan_code="free",
        status=SubscriptionStatus.NONE,
    )


def get_active_plan(db: Session, *, workspace_id: UUID) -> Plan:
    sub = _ensure_subscription(db, workspace_id=workspace_id)
    code = sub.plan_code or "free"
    if sub.status not in (
        SubscriptionStatus.NONE,
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.ACTIVE,
    ):
        # Past-due / canceled / incomplete fall back to the free plan limits.
        code = "free"
    return PLANS.get(code, PLANS["free"])


# ---------------------------------------------------------------------------
# Usage + plan-limit enforcement
# ---------------------------------------------------------------------------


def record_usage_event(
    db: Session,
    *,
    workspace_id: UUID,
    event_type: UsageEventType,
    quantity: int = 1,
    metadata: dict[str, Any] | None = None,
) -> UsageEvent:
    """Persist a usage event. Most callers pass `quantity=1`; LLM calls pass
    the total token count so plan caps can throttle by tokens rather than
    request count."""

    event = UsageEvent(
        workspace_id=workspace_id,
        event_type=event_type,
        quantity=max(1, int(quantity)),
        occurred_at=datetime.now(timezone.utc),
        metadata_json=metadata,
    )
    db.add(event)
    db.flush()
    return event


def _month_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    return start, end


def usage_in_last_30d(
    db: Session, *, workspace_id: UUID, event_type: UsageEventType
) -> int:
    start, end = _month_window()
    return (
        db.query(func.coalesce(func.sum(UsageEvent.quantity), 0))
        .filter(
            UsageEvent.workspace_id == workspace_id,
            UsageEvent.event_type == event_type,
            UsageEvent.occurred_at >= start,
            UsageEvent.occurred_at <= end,
        )
        .scalar()
        or 0
    )


def llm_cost_cents_last_30d(db: Session, *, workspace_id: UUID) -> int:
    """Sum every LLM_CALL event's per-call `estimated_cost_usd_micros` metadata
    over the last 30 days and return the total in cents (rounded to the
    nearest cent). Returns 0 when no events are present or the metadata is
    missing — old events created before cost tracking landed don't carry the
    field and are simply ignored."""

    start, end = _month_window()
    rows = (
        db.query(UsageEvent.metadata_json)
        .filter(
            UsageEvent.workspace_id == workspace_id,
            UsageEvent.event_type == UsageEventType.LLM_CALL,
            UsageEvent.occurred_at >= start,
            UsageEvent.occurred_at <= end,
        )
        .all()
    )
    total_micros = 0
    for (md,) in rows:
        if not isinstance(md, dict):
            continue
        cost = md.get("estimated_cost_usd_micros")
        if isinstance(cost, (int, float)) and cost > 0:
            total_micros += int(cost)
    # 1 USD = 1_000_000 micros = 100 cents → 1 cent = 10_000 micros.
    return total_micros // 10_000


# ---------------------------------------------------------------------------
# AI credits — a single monthly pool that meters AI work. Each AI action
# deducts credits per CREDIT_COST; non-AI caps (landing pages, seats, provider
# writes) are enforced separately below.
# ---------------------------------------------------------------------------

# Credits charged per AI action, keyed by the usage event the action records.
# Events with no entry (raw LLM_CALL token meter, provider writes, reports)
# cost no credits — an action's LLM usage is already priced into its cost.
CREDIT_COST: dict[UsageEventType, int] = {
    UsageEventType.AGENT_RUN: 10,
    UsageEventType.CONTENT_DRAFT: 5,
    UsageEventType.AB_TEST_CREATED: 3,
    UsageEventType.OUTREACH_EMAIL_SENT: 2,
    # Image generation is the priciest per-unit AI action, so it costs the most
    # credits.
    UsageEventType.IMAGE_GENERATION: 10,
}


def credits_used_last_30d(db: Session, *, workspace_id: UUID) -> int:
    """Total AI credits consumed in the trailing 30-day window — the sum of
    CREDIT_COST over every metered action event."""
    start, end = _month_window()
    total = 0
    for event_type, cost in CREDIT_COST.items():
        if cost <= 0:
            continue
        count = (
            db.query(func.count(UsageEvent.id))
            .filter(
                UsageEvent.workspace_id == workspace_id,
                UsageEvent.event_type == event_type,
                UsageEvent.occurred_at >= start,
                UsageEvent.occurred_at <= end,
            )
            .scalar()
            or 0
        )
        total += int(count) * cost
    return total


def assert_within_credit_budget(
    db: Session, *, workspace_id: UUID, cost: int, action_label: str
) -> None:
    """Block an AI action when it would exceed the plan's monthly credit pool.
    Superusers bypass; unlimited plans (`monthly_credits is None`) never block."""
    if is_superuser_request():
        return
    plan = get_active_plan(db, workspace_id=workspace_id)
    allotment = plan.limits.monthly_credits
    if allotment is None:
        return
    used = credits_used_last_30d(db, workspace_id=workspace_id)
    if used + cost > allotment:
        raise InsufficientCreditsError(
            f"Plan `{plan.code}` includes {allotment} AI credits / 30 days "
            f"(used {used}); {action_label} needs {cost}. Upgrade for more credits."
        )


def assert_within_agent_run_limit(db: Session, *, workspace_id: UUID) -> None:
    assert_within_credit_budget(
        db,
        workspace_id=workspace_id,
        cost=CREDIT_COST[UsageEventType.AGENT_RUN],
        action_label="an agent run",
    )


def assert_within_landing_page_limit(
    db: Session, *, workspace_id: UUID, current_count: int
) -> None:
    if is_superuser_request():
        return
    plan = get_active_plan(db, workspace_id=workspace_id)
    cap = plan.limits.landing_pages
    if cap is None:
        return
    if current_count >= cap:
        raise PlanLimitExceededError(
            f"Plan `{plan.code}` allows {cap} tracked landing page(s). "
            f"Upgrade to add more."
        )


def assert_within_member_limit(db: Session, *, workspace_id: UUID) -> None:
    """Block invitations once the workspace would exceed its seat cap.

    Counts active workspace_members + pending invitations against
    `plan.limits.members`. Pending invites count because once accepted
    they become members, and we want to surface the error at invite-time
    rather than at accept-time (when the invitee has already clicked the
    email link). Revoked/expired/accepted invitations are excluded.
    """
    if is_superuser_request():
        return
    plan = get_active_plan(db, workspace_id=workspace_id)
    cap = plan.limits.members
    if cap is None:
        return

    active_members = (
        db.query(func.count(WorkspaceMember.id))
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.status == MemberStatus.ACTIVE,
        )
        .scalar()
        or 0
    )
    pending_invites = (
        db.query(func.count(WorkspaceInvitation.id))
        .filter(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.status == InvitationStatus.PENDING,
        )
        .scalar()
        or 0
    )
    used = int(active_members) + int(pending_invites)
    if used >= cap:
        raise PlanLimitExceededError(
            f"Plan `{plan.code}` allows {cap} workspace member(s). "
            f"Upgrade to invite more (used {used}, including pending invites)."
        )


def _assert_event_under_cap(
    db: Session,
    *,
    workspace_id: UUID,
    event_type: UsageEventType,
    cap: int | None,
    resource_label: str,
    cap_unit: str = "per 30 days",
) -> None:
    # Single bypass point for every event-counted limit (content drafts,
    # outreach sends, A/B tests, outbound writes). The four public
    # wrappers below all funnel through here, so checking the flag once
    # covers all of them.
    if is_superuser_request():
        return
    if cap is None:
        return
    plan = get_active_plan(db, workspace_id=workspace_id)
    used = usage_in_last_30d(
        db, workspace_id=workspace_id, event_type=event_type
    )
    if used >= cap:
        raise PlanLimitExceededError(
            f"Plan `{plan.code}` allows {cap} {resource_label} {cap_unit}. "
            f"Upgrade to lift the limit (used {used})."
        )


def assert_within_content_draft_limit(db: Session, *, workspace_id: UUID) -> None:
    assert_within_credit_budget(
        db,
        workspace_id=workspace_id,
        cost=CREDIT_COST[UsageEventType.CONTENT_DRAFT],
        action_label="a content draft",
    )


def assert_within_image_generation_limit(db: Session, *, workspace_id: UUID) -> None:
    assert_within_credit_budget(
        db,
        workspace_id=workspace_id,
        cost=CREDIT_COST[UsageEventType.IMAGE_GENERATION],
        action_label="an AI image",
    )


def assert_within_outreach_email_limit(db: Session, *, workspace_id: UUID) -> None:
    assert_within_credit_budget(
        db,
        workspace_id=workspace_id,
        cost=CREDIT_COST[UsageEventType.OUTREACH_EMAIL_SENT],
        action_label="an outreach email",
    )


def assert_within_ab_test_limit(db: Session, *, workspace_id: UUID) -> None:
    assert_within_credit_budget(
        db,
        workspace_id=workspace_id,
        cost=CREDIT_COST[UsageEventType.AB_TEST_CREATED],
        action_label="an A/B test",
    )


def assert_within_outbound_write_limit(db: Session, *, workspace_id: UUID) -> None:
    plan = get_active_plan(db, workspace_id=workspace_id)
    _assert_event_under_cap(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.OUTBOUND_WRITE,
        cap=plan.limits.outbound_writes_per_month,
        resource_label="outbound provider writes",
    )


def assert_within_llm_token_limit(db: Session, *, workspace_id: UUID) -> None:
    """No-op: LLM usage is metered at the action level via the AI-credit pool
    (see CREDIT_COST), not per raw token. Kept for the existing call site in the
    LLM client so an out-of-credits action is blocked before it starts, not
    mid-generation."""
    return None


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def subscription_provider() -> str:
    """Which processor handles *recurring* subscriptions. PayPal is the only
    processor; returns "none" until it's configured."""
    return "paypal" if paypal_billing.is_configured() else "none"


# ---------------------------------------------------------------------------
# PayPal checkout (server-created subscription + redirect approval)
# ---------------------------------------------------------------------------

# custom_id round-trips workspace/plan/interval through PayPal since its webhook
# echoes it back on the subscription resource. Pipe-delimited, well under
# PayPal's 127-char cap.
_CUSTOM_SEP = "|"


def _encode_custom_id(workspace_id: UUID, plan_code: str, interval: str) -> str:
    return _CUSTOM_SEP.join([str(workspace_id), plan_code, interval])


def _decode_custom_id(custom_id: str | None) -> tuple[UUID | None, str | None, str | None]:
    if not custom_id:
        return None, None, None
    parts = custom_id.split(_CUSTOM_SEP)
    ws_raw = parts[0] if len(parts) > 0 else None
    plan_code = parts[1] if len(parts) > 1 else None
    interval = parts[2] if len(parts) > 2 else None
    try:
        workspace_id = UUID(str(ws_raw)) if ws_raw else None
    except (ValueError, TypeError):
        workspace_id = None
    return workspace_id, plan_code, interval


def create_paypal_checkout(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    plan_code: str,
    interval: str = "month",
) -> dict[str, Any]:
    """Create a PayPal subscription and return `{approval_url}`. The caller
    redirects the buyer there; activation is confirmed by the webhook."""
    if not paypal_billing.is_configured():
        raise BillingNotConfiguredError("PayPal billing is not configured.")
    get_plan(plan_code)  # validates the plan exists (raises UnknownPlanError)
    plan_id = paypal_billing.plan_id_for_plan(plan_code, interval)
    base = settings.frontend_url.rstrip("/")
    result = paypal_billing.create_subscription(
        plan_id=plan_id,
        subscriber_email=user.email,
        custom_id=_encode_custom_id(workspace.id, plan_code, interval),
        return_url=f"{base}/billing?checkout=success",
        cancel_url=f"{base}/billing?checkout=cancelled",
    )
    return {"approval_url": result["approval_url"]}


def paypal_management_url(db: Session, *, workspace_id: UUID) -> str:
    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    if sub is None or not sub.external_subscription_id:
        raise BillingNotConfiguredError("No PayPal subscription to manage yet.")
    # PayPal has no per-customer hosted portal; the autopay list is where the
    # buyer views + cancels. Stored on the row at activation time.
    return sub.management_url or paypal_billing.management_url()


# ---------------------------------------------------------------------------
# PayPal webhook — idempotent, signature already verified by the route
# ---------------------------------------------------------------------------


def _record_processed_event(
    db: Session, *, provider: str, event_id: str, event_type: str | None
) -> bool:
    """Insert the event into the idempotency ledger. Returns False (and leaves
    the session clean) if it was already processed — the unique constraint on
    (provider, event_id) is the real guard against replays."""
    db.add(
        ProcessedWebhookEvent(
            provider=provider, event_id=event_id, event_type=event_type
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True


def process_paypal_webhook(db: Session, event: dict[str, Any]) -> None:
    event_id = event.get("id")
    event_type = event.get("event_type")
    resource = event.get("resource") or {}
    log.info("paypal.webhook", event_type=event_type, event_id=event_id)

    if not event_id:
        log.warning("paypal.webhook.no_event_id", event_type=event_type)
        return
    if not _record_processed_event(
        db, provider="paypal", event_id=event_id, event_type=event_type
    ):
        log.info("paypal.webhook.duplicate", event_id=event_id)
        return

    if event_type in ("BILLING.SUBSCRIPTION.CANCELLED", "BILLING.SUBSCRIPTION.EXPIRED"):
        _on_paypal_subscription_canceled(db, resource)
    elif event_type and event_type.startswith("BILLING.SUBSCRIPTION."):
        # ACTIVATED / UPDATED / SUSPENDED / RE-ACTIVATED — reconcile the row.
        _on_paypal_subscription_changed(db, resource)
    elif event_type == "INVOICING.INVOICE.PAID":
        _on_paypal_invoice_paid(db, resource)

    db.commit()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _get_or_create_paypal_sub(
    db: Session, *, workspace_id: UUID
) -> BillingSubscription:
    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    if sub is None:
        sub = BillingSubscription(
            workspace_id=workspace_id, plan_code="free", source=SubscriptionSource.PAYPAL
        )
        db.add(sub)
        db.flush()
    return sub


def _on_paypal_subscription_changed(db: Session, resource: dict[str, Any]) -> None:
    workspace_id, custom_plan, _interval = _decode_custom_id(resource.get("custom_id"))
    if workspace_id is None:
        log.warning("paypal.webhook.no_workspace", subscription_id=resource.get("id"))
        return

    sub = _get_or_create_paypal_sub(db, workspace_id=workspace_id)
    sub.source = SubscriptionSource.PAYPAL
    sub.external_subscription_id = resource.get("id")

    plan_id = resource.get("plan_id")
    sub.external_price_id = plan_id
    sub.plan_code = (
        paypal_billing.plan_for_plan_id(plan_id)
        or custom_plan
        or sub.plan_code
        or "free"
    )

    sub.status = paypal_billing.map_status(resource.get("status"))

    sub.current_period_start = _parse_iso(resource.get("start_time"))
    billing_info = resource.get("billing_info") or {}
    sub.current_period_end = _parse_iso(billing_info.get("next_billing_time"))

    # PayPal signals a pending cancel via status; there's no separate
    # cancel-at-period-end flag, so it stays False until the CANCELLED event.
    sub.cancel_at_period_end = False
    sub.management_url = paypal_billing.management_url()


def _on_paypal_subscription_canceled(db: Session, resource: dict[str, Any]) -> None:
    workspace_id, _plan, _interval = _decode_custom_id(resource.get("custom_id"))
    sub = None
    if workspace_id is not None:
        sub = (
            db.query(BillingSubscription)
            .filter(BillingSubscription.workspace_id == workspace_id)
            .first()
        )
    if sub is None and resource.get("id"):
        # Fall back to the subscription id if custom_id was stripped.
        sub = (
            db.query(BillingSubscription)
            .filter(BillingSubscription.external_subscription_id == resource.get("id"))
            .first()
        )
    if sub is None:
        return
    sub.status = SubscriptionStatus.CANCELED
    sub.plan_code = "free"
    sub.cancel_at_period_end = False


def _on_paypal_invoice_paid(db: Session, resource: dict[str, Any]) -> None:
    """A PayPal *fee* invoice (System B — Invoicing API) was paid. Reconcile it
    against our fee ledger. Subscription payments don't come through here."""
    invoice_obj = resource.get("invoice") or resource
    invoice_id = invoice_obj.get("id")
    if not invoice_id:
        return
    from app.models.fee_invoice import FeeInvoice
    from app.services import fee_billing_service

    invoice = (
        db.query(FeeInvoice)
        .filter(FeeInvoice.external_id == invoice_id, FeeInvoice.provider == "paypal")
        .first()
    )
    if invoice is not None:
        fee_billing_service.confirm_invoice_payment(
            db, invoice=invoice, confirmation_ref=invoice_id
        )
