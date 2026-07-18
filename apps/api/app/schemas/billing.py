from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.billing_subscription import SubscriptionStatus


class PlanLimitsPublic(BaseModel):
    landing_pages: int | None
    members: int | None
    outbound_writes_per_month: int | None = None
    # AI work is metered as a single monthly credit pool.
    monthly_credits: int | None = None


class PlanPublic(BaseModel):
    code: str
    display_name: str
    description: str
    monthly_price_usd: int | None
    # Display only; annual checkout uses the plan's annual PayPal Billing Plan.
    annual_price_usd: int | None = None
    is_paid: bool
    limits: PlanLimitsPublic


class UsagePublic(BaseModel):
    # AI credits consumed this 30-day window (the headline meter).
    credits_used_last_30d: int = 0
    agent_runs_last_30d: int = 0
    content_drafts_last_30d: int = 0
    outreach_emails_last_30d: int = 0
    ab_tests_last_30d: int = 0
    outbound_writes_last_30d: int = 0
    llm_tokens_last_30d: int = 0
    # Estimated LLM dollar cost over the same 30-day window. Stored as cents
    # (integer) so the UI can render without float drift.
    llm_cost_cents_last_30d: int = 0


class BillingStatus(BaseModel):
    plan: PlanPublic
    available_plans: list[PlanPublic]
    subscription_status: SubscriptionStatus
    cancel_at_period_end: bool
    current_period_end: datetime | None
    trial_end: datetime | None
    usage: UsagePublic
    # True when there's a manageable PayPal subscription (a manage URL exists).
    has_billing_customer: bool
    paypal_configured: bool = False
    # Which processor handles recurring plans: "paypal" | "none".
    subscription_provider: str = "none"
    # "paypal" (recurring) | "appsumo" (lifetime). Lets the UI pick the right
    # badge / manage flow.
    subscription_source: str = "paypal"


class CheckoutRequest(BaseModel):
    plan_code: str
    interval: Literal["month", "year"] = "month"


class PayPalCheckout(BaseModel):
    """Server-created PayPal subscription. The client redirects to approval_url
    to complete approval; activation is confirmed by the webhook."""

    approval_url: str


class CheckoutResponse(BaseModel):
    provider: str = "paypal"
    paypal: PayPalCheckout | None = None


class PortalResponse(BaseModel):
    url: str
