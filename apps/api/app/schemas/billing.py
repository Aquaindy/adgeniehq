from datetime import datetime

from pydantic import BaseModel

from app.models.billing_subscription import SubscriptionStatus


class PlanLimitsPublic(BaseModel):
    agent_runs_per_month: int | None
    landing_pages: int | None
    members: int | None
    content_drafts_per_month: int | None = None
    outreach_emails_per_month: int | None = None
    ab_tests_per_month: int | None = None
    outbound_writes_per_month: int | None = None
    llm_tokens_per_month: int | None = None


class PlanPublic(BaseModel):
    code: str
    display_name: str
    description: str
    monthly_price_usd: int | None
    is_paid: bool
    limits: PlanLimitsPublic


class UsagePublic(BaseModel):
    agent_runs_last_30d: int
    content_drafts_last_30d: int = 0
    outreach_emails_last_30d: int = 0
    ab_tests_last_30d: int = 0
    outbound_writes_last_30d: int = 0
    llm_tokens_last_30d: int = 0
    # Estimated LLM dollar cost over the same 30-day window. Computed from
    # the per-call `estimated_cost_usd_micros` metadata recorded on each
    # LLM_CALL usage event. Stored as cents (integer) so the UI can render
    # without float drift.
    llm_cost_cents_last_30d: int = 0


class BillingStatus(BaseModel):
    plan: PlanPublic
    available_plans: list[PlanPublic]
    subscription_status: SubscriptionStatus
    cancel_at_period_end: bool
    current_period_end: datetime | None
    trial_end: datetime | None
    usage: UsagePublic
    has_billing_customer: bool
    stripe_configured: bool
    paddle_configured: bool = False
    # Which processor handles recurring plans: "paddle" | "stripe" | "none".
    subscription_provider: str = "none"
    # "stripe" (recurring) | "paddle" (recurring, MoR) | "appsumo" (lifetime).
    # Lets the UI pick the right checkout/portal flow and badge.
    subscription_source: str = "stripe"


class CheckoutRequest(BaseModel):
    plan_code: str


class PaddleCheckout(BaseModel):
    """Client-side overlay config for Paddle.js (there is no server redirect)."""

    client_token: str
    environment: str
    price_id: str
    customer_email: str
    custom_data: dict[str, str]


class CheckoutResponse(BaseModel):
    # "stripe" -> use `url` (redirect); "paddle" -> use `paddle` (overlay).
    provider: str = "stripe"
    url: str | None = None
    paddle: PaddleCheckout | None = None


class PortalResponse(BaseModel):
    url: str
