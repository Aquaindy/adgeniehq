"""Billing orchestration: customer creation, checkout + portal sessions,
webhook processing, plan-limit enforcement, and usage tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

import stripe

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.core.superuser_context import is_superuser_request
from app.integrations.stripe import (
    BillingNotConfiguredError,
    PLANS,
    Plan,
    UnknownPlanError,
    get_plan,
    resolve_price_id,
    stripe_client,
    webhook_secret,
)
from app.models.billing_customer import BillingCustomer
from app.models.billing_subscription import BillingSubscription, SubscriptionStatus
from app.models.usage_event import UsageEvent, UsageEventType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_invitation import InvitationStatus, WorkspaceInvitation
from app.models.workspace_member import WorkspaceMember
from app.security.permissions import MemberStatus

log = get_logger(__name__)


class PlanLimitExceededError(AdVantaError):
    status_code = 402
    code = "plan_limit_exceeded"


class WebhookSignatureError(AdVantaError):
    status_code = 400
    code = "invalid_webhook_signature"


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
    customer = (
        db.query(BillingCustomer)
        .filter(BillingCustomer.workspace_id == workspace_id)
        .first()
    )
    # We can't have a subscription without a customer row; create a placeholder
    # only when persisting one. For the no-billing-customer case, return an
    # un-persisted free record purely for limit lookups.
    if customer is None:
        placeholder = BillingSubscription(
            workspace_id=workspace_id,
            billing_customer_id=UUID(int=0),  # never used because we don't persist
            plan_code="free",
            status=SubscriptionStatus.NONE,
        )
        return placeholder
    sub = BillingSubscription(
        workspace_id=workspace_id,
        billing_customer_id=customer.id,
        plan_code="free",
        status=SubscriptionStatus.NONE,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


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


def assert_within_agent_run_limit(db: Session, *, workspace_id: UUID) -> None:
    if is_superuser_request():
        return
    plan = get_active_plan(db, workspace_id=workspace_id)
    cap = plan.limits.agent_runs_per_month
    if cap is None:
        return
    used = usage_in_last_30d(
        db, workspace_id=workspace_id, event_type=UsageEventType.AGENT_RUN
    )
    if used >= cap:
        raise PlanLimitExceededError(
            f"Plan `{plan.code}` allows {cap} agent runs per 30 days. "
            f"Upgrade to lift the limit (used {used})."
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
    plan = get_active_plan(db, workspace_id=workspace_id)
    _assert_event_under_cap(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.CONTENT_DRAFT,
        cap=plan.limits.content_drafts_per_month,
        resource_label="content drafts",
    )


def assert_within_outreach_email_limit(db: Session, *, workspace_id: UUID) -> None:
    plan = get_active_plan(db, workspace_id=workspace_id)
    _assert_event_under_cap(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.OUTREACH_EMAIL_SENT,
        cap=plan.limits.outreach_emails_per_month,
        resource_label="outreach emails",
    )


def assert_within_ab_test_limit(db: Session, *, workspace_id: UUID) -> None:
    plan = get_active_plan(db, workspace_id=workspace_id)
    _assert_event_under_cap(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.AB_TEST_CREATED,
        cap=plan.limits.ab_tests_per_month,
        resource_label="A/B tests",
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
    """Pre-flight check before an LLM call. We use the running total against
    a soft cap; the moment usage hits the cap, generation falls back to
    deterministic templates rather than blowing the bill."""

    plan = get_active_plan(db, workspace_id=workspace_id)
    _assert_event_under_cap(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.LLM_CALL,
        cap=plan.limits.llm_tokens_per_month,
        resource_label="LLM tokens",
    )


# ---------------------------------------------------------------------------
# Customer + checkout / portal
# ---------------------------------------------------------------------------


def _ensure_customer(
    db: Session, *, workspace: Workspace, user: User
) -> BillingCustomer:
    customer = (
        db.query(BillingCustomer)
        .filter(BillingCustomer.workspace_id == workspace.id)
        .first()
    )
    if customer is not None:
        return customer

    sdk = stripe_client()
    stripe_customer = sdk.Customer.create(
        email=user.email,
        name=workspace.name,
        metadata={"workspace_id": str(workspace.id), "workspace_slug": workspace.slug},
    )
    customer = BillingCustomer(
        workspace_id=workspace.id,
        stripe_customer_id=stripe_customer["id"],
        email=user.email,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    # Create a baseline subscription row in `none` status so future webhook
    # upserts have something to write into.
    if not customer.subscription:
        sub = BillingSubscription(
            workspace_id=workspace.id,
            billing_customer_id=customer.id,
            plan_code="free",
            status=SubscriptionStatus.NONE,
        )
        db.add(sub)
        db.commit()

    return customer


def create_checkout_session(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    plan_code: str,
) -> str:
    plan = get_plan(plan_code)
    price_id = resolve_price_id(plan)

    customer = _ensure_customer(db, workspace=workspace, user=user)
    sdk = stripe_client()

    session = sdk.checkout.Session.create(
        mode="subscription",
        customer=customer.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.frontend_url.rstrip('/')}/billing?stripe=success",
        cancel_url=f"{settings.frontend_url.rstrip('/')}/billing?stripe=canceled",
        client_reference_id=str(workspace.id),
        metadata={
            "workspace_id": str(workspace.id),
            "plan_code": plan.code,
        },
        allow_promotion_codes=True,
    )
    return session["url"]


def create_portal_session(db: Session, *, workspace: Workspace) -> str:
    customer = (
        db.query(BillingCustomer)
        .filter(BillingCustomer.workspace_id == workspace.id)
        .first()
    )
    if customer is None:
        raise PlanLimitExceededError(
            "Workspace doesn't have a billing customer yet. Upgrade to a paid plan first."
        )
    sdk = stripe_client()
    session = sdk.billing_portal.Session.create(
        customer=customer.stripe_customer_id,
        return_url=f"{settings.frontend_url.rstrip('/')}/billing",
    )
    return session["url"]


# ---------------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------------


def verify_and_parse_webhook(*, payload: bytes, signature: str | None) -> dict[str, Any]:
    secret = webhook_secret()
    if not signature:
        raise WebhookSignatureError("Missing Stripe-Signature header.")
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except stripe.error.SignatureVerificationError as exc:
        raise WebhookSignatureError(str(exc)) from exc
    return event


def process_webhook_event(db: Session, event: dict[str, Any]) -> None:
    event_type = event.get("type")
    data_object = (event.get("data") or {}).get("object") or {}
    log.info("billing.webhook", event_type=event_type, event_id=event.get("id"))

    if event_type == "checkout.session.completed":
        _on_checkout_completed(db, data_object)
    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
    ):
        _on_subscription_changed(db, data_object)
    elif event_type == "customer.subscription.deleted":
        _on_subscription_deleted(db, data_object)


def _on_checkout_completed(db: Session, session: dict[str, Any]) -> None:
    workspace_id_str = session.get("client_reference_id") or (
        session.get("metadata", {}) or {}
    ).get("workspace_id")
    if not workspace_id_str:
        return
    try:
        workspace_id = UUID(workspace_id_str)
    except ValueError:
        return

    stripe_customer_id = session.get("customer")
    stripe_subscription_id = session.get("subscription")
    plan_code = (session.get("metadata") or {}).get("plan_code") or "starter"

    customer = (
        db.query(BillingCustomer)
        .filter(BillingCustomer.workspace_id == workspace_id)
        .first()
    )
    if customer is None and stripe_customer_id:
        customer = BillingCustomer(
            workspace_id=workspace_id,
            stripe_customer_id=stripe_customer_id,
        )
        db.add(customer)
        db.flush()
    if customer is None:
        return

    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    if sub is None:
        sub = BillingSubscription(
            workspace_id=workspace_id,
            billing_customer_id=customer.id,
        )
        db.add(sub)

    sub.stripe_subscription_id = stripe_subscription_id
    sub.plan_code = plan_code
    sub.status = SubscriptionStatus.ACTIVE
    db.commit()


def _on_subscription_changed(db: Session, sub_payload: dict[str, Any]) -> None:
    stripe_customer_id = sub_payload.get("customer")
    if not stripe_customer_id:
        return
    customer = (
        db.query(BillingCustomer)
        .filter(BillingCustomer.stripe_customer_id == stripe_customer_id)
        .first()
    )
    if customer is None:
        return

    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == customer.workspace_id)
        .first()
    )
    if sub is None:
        sub = BillingSubscription(
            workspace_id=customer.workspace_id,
            billing_customer_id=customer.id,
            plan_code="free",
        )
        db.add(sub)
        db.flush()

    items = ((sub_payload.get("items") or {}).get("data") or [])
    price_id = items[0].get("price", {}).get("id") if items else None
    sub.stripe_subscription_id = sub_payload.get("id")
    sub.stripe_price_id = price_id
    sub.plan_code = _plan_code_for_price_id(price_id) or sub.plan_code or "free"

    raw_status = (sub_payload.get("status") or "").lower()
    try:
        sub.status = SubscriptionStatus(raw_status)
    except ValueError:
        sub.status = SubscriptionStatus.ACTIVE

    sub.cancel_at_period_end = bool(sub_payload.get("cancel_at_period_end"))
    sub.current_period_start = _to_dt(sub_payload.get("current_period_start"))
    sub.current_period_end = _to_dt(sub_payload.get("current_period_end"))
    sub.trial_end = _to_dt(sub_payload.get("trial_end"))
    db.commit()


def _on_subscription_deleted(db: Session, sub_payload: dict[str, Any]) -> None:
    stripe_customer_id = sub_payload.get("customer")
    if not stripe_customer_id:
        return
    customer = (
        db.query(BillingCustomer)
        .filter(BillingCustomer.stripe_customer_id == stripe_customer_id)
        .first()
    )
    if customer is None:
        return

    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == customer.workspace_id)
        .first()
    )
    if sub is None:
        return
    sub.status = SubscriptionStatus.CANCELED
    sub.plan_code = "free"
    sub.cancel_at_period_end = False
    db.commit()


def _plan_code_for_price_id(price_id: str | None) -> str | None:
    if not price_id:
        return None
    import os

    for plan in PLANS.values():
        if plan.price_id_env and os.getenv(plan.price_id_env, "").strip() == price_id:
            return plan.code
    return None


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
