from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.billing.plans import PLANS
from app.db.session import get_db
from app.integrations import paypal_billing
from app.models.usage_event import UsageEventType
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.billing import (
    BillingStatus,
    CheckoutRequest,
    CheckoutResponse,
    PayPalCheckout,
    PlanLimitsPublic,
    PlanPublic,
    PortalResponse,
    UsagePublic,
)
from app.security.dependencies import get_current_member, require_owner
from app.services import billing_service

# Workspace-scoped routes (auth required)
workspace_router = APIRouter()

# Public webhook router (PayPal-signed, no auth)
public_router = APIRouter()


def _plan_to_public(plan) -> PlanPublic:
    return PlanPublic(
        code=plan.code,
        display_name=plan.display_name,
        description=plan.description,
        monthly_price_usd=plan.monthly_price_usd,
        annual_price_usd=plan.annual_price_usd,
        is_paid=plan.paid,
        limits=PlanLimitsPublic(
            landing_pages=plan.limits.landing_pages,
            members=plan.limits.members,
            outbound_writes_per_month=plan.limits.outbound_writes_per_month,
            monthly_credits=plan.limits.monthly_credits,
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
            credits_used_last_30d=billing_service.credits_used_last_30d(
                db, workspace_id=workspace_id
            ),
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
        # Show "Manage billing" for any real PayPal subscription.
        has_billing_customer=bool(sub and sub.external_subscription_id),
        paypal_configured=paypal_billing.is_configured(),
        subscription_provider=billing_service.subscription_provider(),
        subscription_source=(sub.source.value if sub else "paypal"),
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
    cfg = billing_service.create_paypal_checkout(
        db,
        workspace=workspace,
        user=member.user,
        plan_code=payload.plan_code,
        interval=payload.interval,
    )
    return CheckoutResponse(provider="paypal", paypal=PayPalCheckout(**cfg))


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
    url = billing_service.paypal_management_url(db, workspace_id=workspace_id)
    return PortalResponse(url=url)


# ---------------------------------------------------------------------------
# Public processor webhook (signature-verified, no auth)
# ---------------------------------------------------------------------------


@public_router.post("/paypal/webhook")
async def paypal_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    import json

    payload = await request.body()
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return JSONResponse({"received": False}, status_code=400)
    # Verify the transmission signature against PayPal before acting on it.
    paypal_billing.verify_webhook(dict(request.headers), event)
    billing_service.process_paypal_webhook(db, event)
    return JSONResponse({"received": True})
