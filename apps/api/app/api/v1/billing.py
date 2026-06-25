import os
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.stripe import PLANS
from app.models.billing_customer import BillingCustomer
from app.models.usage_event import UsageEventType
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.integrations import paddle_billing
from app.schemas.billing import (
    BillingStatus,
    CheckoutRequest,
    CheckoutResponse,
    PaddleCheckout,
    PlanLimitsPublic,
    PlanPublic,
    PortalResponse,
    UsagePublic,
)
from app.security.dependencies import get_current_member, require_owner
from app.services import billing_service

# Workspace-scoped routes (auth required)
workspace_router = APIRouter()

# Public webhook router (Stripe-signed, no auth)
public_router = APIRouter()


def _plan_to_public(plan) -> PlanPublic:
    return PlanPublic(
        code=plan.code,
        display_name=plan.display_name,
        description=plan.description,
        monthly_price_usd=plan.monthly_price_usd,
        is_paid=plan.price_id_env is not None,
        limits=PlanLimitsPublic(
            agent_runs_per_month=plan.limits.agent_runs_per_month,
            landing_pages=plan.limits.landing_pages,
            members=plan.limits.members,
        ),
    )


@workspace_router.get(
    "/{workspace_id}/billing/status", response_model=BillingStatus
)
def get_billing_status(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> BillingStatus:
    plan = billing_service.get_active_plan(db, workspace_id=workspace_id)
    sub = (
        db.query(billing_service.BillingSubscription)
        .filter(billing_service.BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    customer = (
        db.query(BillingCustomer)
        .filter(BillingCustomer.workspace_id == workspace_id)
        .first()
    )
    def _u(t: UsageEventType) -> int:
        return billing_service.usage_in_last_30d(
            db, workspace_id=workspace_id, event_type=t
        )

    return BillingStatus(
        plan=_plan_to_public(plan),
        available_plans=[
            _plan_to_public(p) for p in PLANS.values() if p.is_public
        ],
        subscription_status=sub.status if sub else billing_service.SubscriptionStatus.NONE,
        cancel_at_period_end=bool(sub.cancel_at_period_end) if sub else False,
        current_period_end=sub.current_period_end if sub else None,
        trial_end=sub.trial_end if sub else None,
        usage=UsagePublic(
            agent_runs_last_30d=_u(UsageEventType.AGENT_RUN),
            content_drafts_last_30d=_u(UsageEventType.CONTENT_DRAFT),
            outreach_emails_last_30d=_u(UsageEventType.OUTREACH_EMAIL_SENT),
            ab_tests_last_30d=_u(UsageEventType.AB_TEST_CREATED),
            outbound_writes_last_30d=_u(UsageEventType.OUTBOUND_WRITE),
            llm_tokens_last_30d=_u(UsageEventType.LLM_CALL),
            llm_cost_cents_last_30d=billing_service.llm_cost_cents_last_30d(
                db, workspace_id=workspace_id
            ),
        ),
        has_billing_customer=customer is not None,
        stripe_configured=bool(os.getenv("STRIPE_SECRET_KEY", "").strip()),
        paddle_configured=paddle_billing.is_configured(),
        subscription_provider=billing_service.subscription_provider(),
        subscription_source=(
            sub.source.value if sub else billing_service.subscription_provider()
        ),
    )


@workspace_router.post(
    "/{workspace_id}/billing/checkout-session",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_checkout(
    workspace_id: UUID,
    payload: CheckoutRequest,
    member: WorkspaceMember = Depends(require_owner),
    db: Session = Depends(get_db),
) -> CheckoutResponse:
    workspace = db.get(Workspace, workspace_id)
    assert workspace is not None  # require_owner guarantees membership
    user = member.user

    provider = billing_service.subscription_provider()
    if provider == "paddle":
        cfg = billing_service.create_paddle_checkout(
            db, workspace=workspace, user=user, plan_code=payload.plan_code
        )
        return CheckoutResponse(provider="paddle", paddle=PaddleCheckout(**cfg))

    # Stripe (default / fallback).
    url = billing_service.create_checkout_session(
        db, workspace=workspace, user=user, plan_code=payload.plan_code
    )
    return CheckoutResponse(provider="stripe", url=url)


@workspace_router.post(
    "/{workspace_id}/billing/portal-session",
    response_model=PortalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_portal(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(require_owner),
    db: Session = Depends(get_db),
) -> PortalResponse:
    workspace = db.get(Workspace, workspace_id)
    assert workspace is not None
    if billing_service.subscription_provider() == "paddle":
        url = billing_service.paddle_management_url(db, workspace_id=workspace_id)
    else:
        url = billing_service.create_portal_session(db, workspace=workspace)
    return PortalResponse(url=url)


# ---------------------------------------------------------------------------
# Public processor webhooks (signature-verified, no auth)
# ---------------------------------------------------------------------------


@public_router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    payload = await request.body()
    event = billing_service.verify_and_parse_webhook(
        payload=payload, signature=stripe_signature
    )
    billing_service.process_webhook_event(db, event)
    return JSONResponse({"received": True})


@public_router.post("/paddle/webhook")
async def paddle_webhook(
    request: Request,
    paddle_signature: str | None = Header(default=None, alias="Paddle-Signature"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    payload = await request.body()
    # Verify the HMAC signature over the RAW body before doing anything else.
    event = paddle_billing.verify_webhook(payload, paddle_signature)
    billing_service.process_paddle_webhook(db, event)
    return JSONResponse({"received": True})
