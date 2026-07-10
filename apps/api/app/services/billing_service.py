"""Billing orchestration: Paddle checkout/portal + webhook processing,
plan-limit enforcement, and usage tracking.

Recurring subscriptions are billed exclusively through **Paddle** (Merchant of
Record). One-off platform *fees* are a separate, provider-agnostic system (see
`app.payments` / `fee_billing_service`)."""

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
from app.core.superuser_context import is_superuser_request
from app.integrations import paddle_billing
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
    # limit lookups. Paddle creates the real row on the first webhook.
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
    """Which processor handles *recurring* subscriptions. Paddle (Merchant of
    Record) is the only processor; returns "none" until it's configured."""
    return "paddle" if paddle_billing.is_configured() else "none"


# ---------------------------------------------------------------------------
# Paddle checkout (client-side overlay — no server redirect URL)
# ---------------------------------------------------------------------------


def create_paddle_checkout(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    plan_code: str,
    interval: str = "month",
) -> dict[str, Any]:
    if not paddle_billing.is_configured():
        raise BillingNotConfiguredError("Paddle billing is not configured.")
    get_plan(plan_code)  # validates the plan exists (raises UnknownPlanError)
    price_id = paddle_billing.price_id_for_plan(plan_code, interval)
    return {
        "client_token": paddle_billing.client_token(),
        "environment": paddle_billing.environment(),
        "price_id": price_id,
        "customer_email": user.email,
        "custom_data": {
            "workspace_id": str(workspace.id),
            "plan_code": plan_code,
            "interval": interval,
        },
    }


def paddle_management_url(db: Session, *, workspace_id: UUID) -> str:
    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    if sub is None:
        raise BillingNotConfiguredError("No Paddle subscription to manage yet.")
    if sub.management_url:
        return sub.management_url
    # Paddle often omits management_urls from webhooks, so resolve it from the
    # API on demand and cache it for next time.
    if sub.external_subscription_id:
        url = paddle_billing.fetch_subscription_management_url(
            sub.external_subscription_id
        )
        if url:
            sub.management_url = url
            db.commit()
            return url
    raise BillingNotConfiguredError(
        "No Paddle management link is available for this subscription yet. "
        "If you need to cancel, use the link in your Paddle receipt email or "
        "contact support."
    )


# ---------------------------------------------------------------------------
# Paddle webhook — idempotent, signature already verified by the route
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


def process_paddle_webhook(db: Session, event: dict[str, Any]) -> None:
    event_id = event.get("event_id")
    event_type = event.get("event_type")
    data = event.get("data") or {}
    log.info("paddle.webhook", event_type=event_type, event_id=event_id)

    if not event_id:
        log.warning("paddle.webhook.no_event_id", event_type=event_type)
        return
    if not _record_processed_event(
        db, provider="paddle", event_id=event_id, event_type=event_type
    ):
        log.info("paddle.webhook.duplicate", event_id=event_id)
        return

    if event_type == "subscription.canceled":
        _on_paddle_subscription_canceled(db, data)
    elif event_type and event_type.startswith("subscription."):
        _on_paddle_subscription_changed(db, data)
    elif event_type in ("transaction.completed", "transaction.paid"):
        _on_paddle_transaction_completed(db, data)

    db.commit()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _paddle_workspace_id(data: dict[str, Any]) -> UUID | None:
    custom = data.get("custom_data") or {}
    raw = custom.get("workspace_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return None


def _get_or_create_paddle_sub(
    db: Session, *, workspace_id: UUID
) -> BillingSubscription:
    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    if sub is None:
        sub = BillingSubscription(
            workspace_id=workspace_id, plan_code="free", source=SubscriptionSource.PADDLE
        )
        db.add(sub)
        db.flush()
    return sub


def _on_paddle_subscription_changed(db: Session, data: dict[str, Any]) -> None:
    workspace_id = _paddle_workspace_id(data)
    if workspace_id is None:
        log.warning("paddle.webhook.no_workspace", subscription_id=data.get("id"))
        return

    sub = _get_or_create_paddle_sub(db, workspace_id=workspace_id)
    sub.source = SubscriptionSource.PADDLE
    sub.external_subscription_id = data.get("id")

    items = data.get("items") or []
    price_id = None
    if items:
        price_id = (items[0].get("price") or {}).get("id")
    sub.external_price_id = price_id

    custom = data.get("custom_data") or {}
    sub.plan_code = (
        paddle_billing.plan_for_price_id(price_id)
        or custom.get("plan_code")
        or sub.plan_code
        or "free"
    )

    sub.status = paddle_billing.map_status(data.get("status"))

    period = data.get("current_billing_period") or {}
    sub.current_period_start = _parse_iso(period.get("starts_at"))
    sub.current_period_end = _parse_iso(period.get("ends_at"))

    scheduled = data.get("scheduled_change") or {}
    sub.cancel_at_period_end = bool(scheduled.get("action") == "cancel")

    # Paddle's keys are `cancel` + `update_payment_method` (prefer the cancel
    # deep-link for the manage button). `update` is kept for forward-compat.
    # Often absent in webhooks — resolved on demand in paddle_management_url.
    mgmt = data.get("management_urls") or {}
    sub.management_url = (
        mgmt.get("cancel")
        or mgmt.get("update_payment_method")
        or mgmt.get("update")
        or sub.management_url
    )


def _on_paddle_subscription_canceled(db: Session, data: dict[str, Any]) -> None:
    workspace_id = _paddle_workspace_id(data)
    if workspace_id is None:
        return
    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    if sub is None:
        return
    sub.status = SubscriptionStatus.CANCELED
    sub.plan_code = "free"
    sub.cancel_at_period_end = False


def _on_paddle_transaction_completed(db: Session, data: dict[str, Any]) -> None:
    """A Paddle transaction settled. If it corresponds to one of our fee
    invoices (matched by the stored transaction id), confirm it paid. Recurring
    subscription transactions won't match a fee invoice and are a no-op here."""
    txn_id = data.get("id")
    if not txn_id:
        return
    from app.models.fee_invoice import FeeInvoice
    from app.services import fee_billing_service

    invoice = (
        db.query(FeeInvoice)
        .filter(FeeInvoice.external_id == txn_id, FeeInvoice.provider == "paddle")
        .first()
    )
    if invoice is not None:
        fee_billing_service.confirm_invoice_payment(
            db, invoice=invoice, confirmation_ref=txn_id
        )
