"""AppSumo lifetime-deal redemption + admin code management.

Codes are uniform (no per-code tier). A workspace's tier is the count of its
REDEEMED codes, capped at `APPSUMO_MAX_TIER` — codes stack. Redemption writes
the workspace's `billing_subscriptions` row with `source=APPSUMO`, the matching
lifetime plan, and `status=ACTIVE` (no Stripe customer, no recurring charge).
Plan-limit enforcement then works exactly as it does for Stripe plans.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.integrations.stripe import APPSUMO_MAX_TIER, APPSUMO_TIER_PLAN, PLANS
from app.models.appsumo_code import AppSumoCode, AppSumoCodeStatus
from app.models.audit_log import AuditActorType
from app.models.billing_subscription import (
    BillingSubscription,
    SubscriptionSource,
    SubscriptionStatus,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.services import audit_service

log = get_logger(__name__)


class AppSumoError(AdVantaError):
    status_code = 400
    code = "appsumo_error"


class CodeNotFoundError(AppSumoError):
    status_code = 404
    code = "appsumo_code_not_found"


class CodeAlreadyRedeemedError(AppSumoError):
    status_code = 409
    code = "appsumo_code_already_redeemed"


class MaxTierReachedError(AppSumoError):
    status_code = 409
    code = "appsumo_max_tier_reached"


# Unambiguous alphabet (no 0/O/1/I) for human-typed codes.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_PREFIX = "ADV"


def normalize_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "")


# ---------------------------------------------------------------------------
# Tier resolution
# ---------------------------------------------------------------------------


def _redeemed_count(db: Session, *, workspace_id: UUID) -> int:
    return (
        db.query(func.count(AppSumoCode.id))
        .filter(
            AppSumoCode.workspace_id == workspace_id,
            AppSumoCode.status == AppSumoCodeStatus.REDEEMED,
        )
        .scalar()
        or 0
    )


def _tier_for_count(count: int) -> int:
    return max(0, min(int(count), APPSUMO_MAX_TIER))


def _apply_tier(db: Session, *, workspace_id: UUID) -> BillingSubscription:
    """Sync the workspace's subscription row to its current AppSumo tier.

    Creates the row if missing. At tier 0 we only revert when the existing row
    is AppSumo-sourced — a Stripe subscription is never clobbered."""

    tier = _tier_for_count(_redeemed_count(db, workspace_id=workspace_id))
    sub = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    if sub is None:
        sub = BillingSubscription(workspace_id=workspace_id, billing_customer_id=None)
        db.add(sub)

    if tier <= 0:
        if sub.source == SubscriptionSource.APPSUMO:
            sub.plan_code = "free"
            sub.status = SubscriptionStatus.NONE
        # A Stripe sub keeps its plan/status untouched.
    else:
        sub.source = SubscriptionSource.APPSUMO
        sub.plan_code = APPSUMO_TIER_PLAN[tier]
        sub.status = SubscriptionStatus.ACTIVE
        sub.cancel_at_period_end = False
        sub.current_period_end = None
        sub.trial_end = None
    db.flush()
    return sub


def get_status(db: Session, *, workspace_id: UUID) -> dict:
    count = _redeemed_count(db, workspace_id=workspace_id)
    tier = _tier_for_count(count)
    plan_code = APPSUMO_TIER_PLAN.get(tier)
    plan = PLANS.get(plan_code) if plan_code else None
    codes = (
        db.query(AppSumoCode)
        .filter(
            AppSumoCode.workspace_id == workspace_id,
            AppSumoCode.status == AppSumoCodeStatus.REDEEMED,
        )
        .order_by(AppSumoCode.redeemed_at.asc())
        .all()
    )
    return {
        "tier": tier,
        "codes_redeemed": count,
        "max_tier": APPSUMO_MAX_TIER,
        "can_stack_more": count < APPSUMO_MAX_TIER,
        "plan_code": plan_code,
        "plan_display_name": plan.display_name if plan else None,
        "codes": codes,
    }


# ---------------------------------------------------------------------------
# Redemption
# ---------------------------------------------------------------------------


def redeem_code(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    code: str,
    request: Request | None = None,
) -> dict:
    norm = normalize_code(code)
    if not norm:
        raise AppSumoError("Enter your AppSumo code to redeem.")

    # Row-lock the code so two concurrent redemptions can't both succeed.
    row = (
        db.query(AppSumoCode)
        .filter(AppSumoCode.code == norm)
        .with_for_update()
        .first()
    )
    if row is None:
        raise CodeNotFoundError(
            "That code isn't valid. Double-check it and try again."
        )
    if row.status == AppSumoCodeStatus.REFUNDED:
        raise AppSumoError("That code was refunded and can no longer be redeemed.")
    if row.status == AppSumoCodeStatus.REDEEMED:
        if row.workspace_id == workspace.id:
            raise CodeAlreadyRedeemedError(
                "You've already redeemed this code on this workspace."
            )
        raise CodeAlreadyRedeemedError("That code has already been redeemed.")

    if _redeemed_count(db, workspace_id=workspace.id) >= APPSUMO_MAX_TIER:
        raise MaxTierReachedError(
            f"This workspace is already at the top tier "
            f"({APPSUMO_MAX_TIER} codes). Redeem additional codes on another "
            "workspace to stack them there."
        )

    row.status = AppSumoCodeStatus.REDEEMED
    row.workspace_id = workspace.id
    row.redeemed_by_user_id = user.id
    row.redeemed_at = datetime.now(timezone.utc)
    db.flush()

    sub = _apply_tier(db, workspace_id=workspace.id)
    status = get_status(db, workspace_id=workspace.id)

    audit_service.log_event(
        db,
        workspace_id=workspace.id,
        actor_type=AuditActorType.USER,
        actor_id=user.id,
        action="appsumo.redeem",
        resource_type="appsumo_code",
        resource_id=row.id,
        metadata={
            "code": row.code,
            "tier": status["tier"],
            "plan_code": sub.plan_code,
        },
        request=request,
    )
    db.commit()
    log.info(
        "appsumo.redeemed",
        workspace_id=str(workspace.id),
        tier=status["tier"],
        plan_code=sub.plan_code,
    )
    return get_status(db, workspace_id=workspace.id)


# ---------------------------------------------------------------------------
# Admin: code generation + lifecycle
# ---------------------------------------------------------------------------


def _random_code(prefix: str) -> str:
    body = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(12))
    grouped = f"{body[:4]}-{body[4:8]}-{body[8:12]}"
    return f"{prefix}-{grouped}" if prefix else grouped


def generate_codes(
    db: Session,
    *,
    count: int,
    batch: str | None = None,
    prefix: str = _CODE_PREFIX,
) -> list[AppSumoCode]:
    """Mint `count` unique unredeemed codes. Export the returned codes to a CSV
    and upload that to AppSumo. Capped at 10k per call."""

    count = max(1, min(int(count), 10_000))
    prefix = normalize_code(prefix)[:8]
    created: list[AppSumoCode] = []
    for _ in range(count):
        code = _random_code(prefix)
        # Extremely unlikely collision; retry a few times defensively.
        for _attempt in range(5):
            exists = db.query(AppSumoCode.id).filter(AppSumoCode.code == code).first()
            if not exists:
                break
            code = _random_code(prefix)
        row = AppSumoCode(
            code=code, status=AppSumoCodeStatus.UNREDEEMED, batch=batch or None
        )
        db.add(row)
        created.append(row)
    db.commit()
    for r in created:
        db.refresh(r)
    log.info("appsumo.codes_generated", count=len(created), batch=batch)
    return created


def deactivate_code(db: Session, *, code: str) -> dict | None:
    """Mark a code REFUNDED (AppSumo refund/chargeback) and downgrade the
    workspace that redeemed it. Returns the workspace's new status, or None if
    the code was never redeemed."""

    norm = normalize_code(code)
    row = db.query(AppSumoCode).filter(AppSumoCode.code == norm).first()
    if row is None:
        raise CodeNotFoundError("Code not found.")

    workspace_id = row.workspace_id
    row.status = AppSumoCodeStatus.REFUNDED
    db.flush()

    result: dict | None = None
    if workspace_id is not None:
        _apply_tier(db, workspace_id=workspace_id)
        result = get_status(db, workspace_id=workspace_id)
    db.commit()
    log.info("appsumo.code_deactivated", code=norm, workspace_id=str(workspace_id))
    return result


def code_stats(db: Session) -> dict:
    def _count(*filters) -> int:
        q = db.query(func.count(AppSumoCode.id))
        for f in filters:
            q = q.filter(f)
        return q.scalar() or 0

    total = _count()
    redeemed = _count(AppSumoCode.status == AppSumoCodeStatus.REDEEMED)
    refunded = _count(AppSumoCode.status == AppSumoCodeStatus.REFUNDED)
    return {
        "total": total,
        "redeemed": redeemed,
        "refunded": refunded,
        "unredeemed": total - redeemed - refunded,
    }
