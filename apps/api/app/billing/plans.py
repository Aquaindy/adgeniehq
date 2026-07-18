"""Subscription plan catalog — provider-neutral.

The catalog defines AdVanta's plans and their limits. Pricing is processed by
**PayPal**; the actual charged amount lives on the PayPal Billing Plan, and the
per-plan PayPal Plan IDs are resolved in `app.integrations.paypal_billing`
(monthly + annual). The `monthly_price_usd` / `annual_price_usd` here are
**display only**.

AI work is metered as a single monthly **AI-credit** pool (`monthly_credits`);
each AI action deducts credits per the cost table in `billing_service`
(`CREDIT_COST`). Non-AI caps — landing-page count, team seats, provider writes —
stay as their own limits. `None` = unlimited on any limit.

`paid=True` marks a sellable plan (resolvable to a PayPal Plan). `is_public`
controls whether it shows on the pricing page + billing UI. `free` is the
internal fallback for workspaces without an active subscription; the AppSumo
tiers are granted by redeeming lifetime codes, never sold through checkout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.core.exceptions import AdVantaError


class BillingNotConfiguredError(AdVantaError):
    status_code = 503
    code = "billing_not_configured"


class UnknownPlanError(AdVantaError):
    status_code = 404
    code = "unknown_plan"


@dataclass(frozen=True)
class PlanLimits:
    # Non-AI caps (kept separate from the AI-credit pool). `None` = unlimited.
    landing_pages: int | None
    members: int | None
    outbound_writes_per_month: int | None = None
    # AI work (agent runs, content drafts, outreach drafts, A/B variants, …) is
    # metered as a single monthly credit pool. `None` = unlimited.
    monthly_credits: int | None = None


@dataclass(frozen=True)
class Plan:
    code: str
    display_name: str
    description: str
    # Display only — PayPal's Billing Plan is the source of truth for the charge.
    monthly_price_usd: int | None
    limits: PlanLimits
    # True = a sellable plan with PayPal Plan IDs (PAYPAL_PLAN_ID_<CODE>[_ANNUAL]).
    paid: bool = False
    # Display only; annual checkout uses the PAYPAL_PLAN_ID_<CODE>_ANNUAL plan.
    annual_price_usd: int | None = None
    # When False, hidden from the public pricing page + the billing UI's
    # available-plans list (still reachable as a technical default).
    is_public: bool = True


PLANS: Final[dict[str, Plan]] = {
    "free": Plan(
        code="free",
        display_name="Free",
        description=(
            "Internal fallback for workspaces without an active subscription. "
            "Hidden from public pricing — not a marketed tier."
        ),
        monthly_price_usd=0,
        paid=False,
        is_public=False,
        limits=PlanLimits(
            landing_pages=10,
            members=5,
            outbound_writes_per_month=100,
            monthly_credits=200,
        ),
    ),
    "starter": Plan(
        code="starter",
        display_name="Starter",
        description="For small teams running their first paid + SEO programs.",
        paid=True,
        monthly_price_usd=67,
        annual_price_usd=670,
        limits=PlanLimits(
            landing_pages=50,
            members=15,
            outbound_writes_per_month=1000,
            monthly_credits=3000,
        ),
    ),
    "pro": Plan(
        code="pro",
        display_name="Pro",
        description="Full agent suite with budget guardrails for serious operators.",
        paid=True,
        monthly_price_usd=129,
        annual_price_usd=1290,
        limits=PlanLimits(
            landing_pages=200,
            members=50,
            outbound_writes_per_month=5000,
            monthly_credits=12000,
        ),
    ),
    "agency": Plan(
        code="agency",
        display_name="Agency",
        description="Unlimited AI credits and landing pages, multi-team workspace support.",
        paid=True,
        monthly_price_usd=299,
        annual_price_usd=2990,
        limits=PlanLimits(
            landing_pages=None,
            members=None,
            outbound_writes_per_month=None,
            monthly_credits=None,
        ),
    ),
    # AppSumo lifetime tiers. Granted by redeeming codes (see appsumo_service),
    # never sold through checkout — so `paid=False` and `is_public=False`. Codes
    # stack: N redeemed codes = Tier N, capping at tier 3. Limits mirror the
    # matching paid tier so enforcement is identical.
    "appsumo_tier1": Plan(
        code="appsumo_tier1",
        display_name="AppSumo Lifetime — Tier 1",
        description="Lifetime deal, Tier 1 (Starter-equivalent limits).",
        paid=False,
        monthly_price_usd=None,
        is_public=False,
        limits=PlanLimits(
            landing_pages=50,
            members=15,
            outbound_writes_per_month=1000,
            monthly_credits=3000,
        ),
    ),
    "appsumo_tier2": Plan(
        code="appsumo_tier2",
        display_name="AppSumo Lifetime — Tier 2",
        description="Lifetime deal, Tier 2 (Pro-equivalent limits).",
        paid=False,
        monthly_price_usd=None,
        is_public=False,
        limits=PlanLimits(
            landing_pages=200,
            members=50,
            outbound_writes_per_month=5000,
            monthly_credits=12000,
        ),
    ),
    "appsumo_tier3": Plan(
        code="appsumo_tier3",
        display_name="AppSumo Lifetime — Tier 3",
        description="Lifetime deal, Tier 3 (Agency-equivalent, unlimited).",
        paid=False,
        monthly_price_usd=None,
        is_public=False,
        limits=PlanLimits(
            landing_pages=None,
            members=None,
            outbound_writes_per_month=None,
            monthly_credits=None,
        ),
    ),
}

# AppSumo stacking ladder: number of redeemed codes -> plan code, capped at
# `APPSUMO_MAX_TIER` codes per workspace.
APPSUMO_MAX_TIER: Final[int] = 3
APPSUMO_TIER_PLAN: Final[dict[int, str]] = {
    1: "appsumo_tier1",
    2: "appsumo_tier2",
    3: "appsumo_tier3",
}


def get_plan(code: str) -> Plan:
    plan = PLANS.get(code)
    if plan is None:
        raise UnknownPlanError(f"Unknown plan: {code}.")
    return plan
