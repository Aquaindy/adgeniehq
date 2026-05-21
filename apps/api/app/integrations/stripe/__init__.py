"""Stripe billing wiring.

Plan catalog is hard-coded; price IDs come from env (STRIPE_PRICE_ID_*) so the
same code runs against test and live Stripe accounts. Without STRIPE_SECRET_KEY
configured, billing endpoints return `503 billing_not_configured`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

import stripe

from app.core.exceptions import AdVantaError


class BillingNotConfiguredError(AdVantaError):
    status_code = 503
    code = "billing_not_configured"


class UnknownPlanError(AdVantaError):
    status_code = 404
    code = "unknown_plan"


@dataclass(frozen=True)
class PlanLimits:
    agent_runs_per_month: int | None
    landing_pages: int | None
    members: int | None
    # Phase A-D + LLM. `None` = unlimited. Defaults preserve existing behaviour
    # for any caller that constructs a PlanLimits without the new fields.
    content_drafts_per_month: int | None = None
    outreach_emails_per_month: int | None = None
    ab_tests_per_month: int | None = None
    outbound_writes_per_month: int | None = None
    llm_tokens_per_month: int | None = None


@dataclass(frozen=True)
class Plan:
    code: str
    display_name: str
    description: str
    price_id_env: str | None
    monthly_price_usd: int | None  # display only; Stripe is source of truth
    limits: PlanLimits
    # Marketing flag — when False, the plan is hidden from the public pricing
    # page and the workspace billing UI's "available plans" list. We still keep
    # the row in PLANS so it's reachable as a technical default (e.g. a brand
    # new workspace has no subscription yet but still needs limit lookups).
    is_public: bool = True


# `None` limit = unlimited.
PLANS: Final[dict[str, Plan]] = {
    "free": Plan(
        code="free",
        display_name="Free",
        description=(
            "Internal fallback for workspaces without an active subscription. "
            "Hidden from public pricing — not a marketed tier."
        ),
        price_id_env=None,
        monthly_price_usd=0,
        is_public=False,
        limits=PlanLimits(
            agent_runs_per_month=10,
            landing_pages=1,
            members=2,
            content_drafts_per_month=5,
            outreach_emails_per_month=10,
            ab_tests_per_month=1,
            outbound_writes_per_month=20,
            llm_tokens_per_month=20_000,
        ),
    ),
    "starter": Plan(
        code="starter",
        display_name="Starter",
        description="For small teams running their first paid + SEO programs.",
        price_id_env="STRIPE_PRICE_ID_STARTER",
        monthly_price_usd=99,
        limits=PlanLimits(
            agent_runs_per_month=100,
            landing_pages=10,
            members=5,
            content_drafts_per_month=50,
            outreach_emails_per_month=200,
            ab_tests_per_month=10,
            outbound_writes_per_month=200,
            llm_tokens_per_month=200_000,
        ),
    ),
    "pro": Plan(
        code="pro",
        display_name="Pro",
        description="Full agent suite with budget guardrails for serious operators.",
        price_id_env="STRIPE_PRICE_ID_PRO",
        monthly_price_usd=299,
        limits=PlanLimits(
            agent_runs_per_month=500,
            landing_pages=50,
            members=15,
            content_drafts_per_month=300,
            outreach_emails_per_month=2000,
            ab_tests_per_month=50,
            outbound_writes_per_month=1000,
            llm_tokens_per_month=1_500_000,
        ),
    ),
    "agency": Plan(
        code="agency",
        display_name="Agency",
        description="Unlimited agent runs and landing pages, multi-team workspace support.",
        price_id_env="STRIPE_PRICE_ID_AGENCY",
        monthly_price_usd=899,
        limits=PlanLimits(
            agent_runs_per_month=None,
            landing_pages=None,
            members=100,
            content_drafts_per_month=None,
            outreach_emails_per_month=None,
            ab_tests_per_month=None,
            outbound_writes_per_month=None,
            llm_tokens_per_month=None,
        ),
    ),
    # AppSumo lifetime tiers. Granted by redeeming codes (see appsumo_service),
    # never sold through Stripe — so `price_id_env=None` and `is_public=False`
    # (hidden from the pricing page + the billing UI's plan list). Codes stack:
    # N redeemed codes = Tier N, capping at tier 3. Limits mirror the matching
    # Stripe tier so plan-limit enforcement is identical; only the source and
    # the lack of a recurring charge differ.
    "appsumo_tier1": Plan(
        code="appsumo_tier1",
        display_name="AppSumo Lifetime — Tier 1",
        description="Lifetime deal, Tier 1 (Starter-equivalent limits).",
        price_id_env=None,
        monthly_price_usd=None,
        is_public=False,
        limits=PlanLimits(
            agent_runs_per_month=100,
            landing_pages=10,
            members=5,
            content_drafts_per_month=50,
            outreach_emails_per_month=200,
            ab_tests_per_month=10,
            outbound_writes_per_month=200,
            llm_tokens_per_month=200_000,
        ),
    ),
    "appsumo_tier2": Plan(
        code="appsumo_tier2",
        display_name="AppSumo Lifetime — Tier 2",
        description="Lifetime deal, Tier 2 (Pro-equivalent limits).",
        price_id_env=None,
        monthly_price_usd=None,
        is_public=False,
        limits=PlanLimits(
            agent_runs_per_month=500,
            landing_pages=50,
            members=15,
            content_drafts_per_month=300,
            outreach_emails_per_month=2000,
            ab_tests_per_month=50,
            outbound_writes_per_month=1000,
            llm_tokens_per_month=1_500_000,
        ),
    ),
    "appsumo_tier3": Plan(
        code="appsumo_tier3",
        display_name="AppSumo Lifetime — Tier 3",
        description="Lifetime deal, Tier 3 (Agency-equivalent, unlimited).",
        price_id_env=None,
        monthly_price_usd=None,
        is_public=False,
        limits=PlanLimits(
            agent_runs_per_month=None,
            landing_pages=None,
            members=100,
            content_drafts_per_month=None,
            outreach_emails_per_month=None,
            ab_tests_per_month=None,
            outbound_writes_per_month=None,
            llm_tokens_per_month=None,
        ),
    ),
}

# AppSumo stacking ladder: number of redeemed codes -> plan code. Capping at
# `APPSUMO_MAX_TIER` codes per workspace. Defined here so the plan limits and
# the tier mapping stay in one place.
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


def resolve_price_id(plan: Plan) -> str:
    """Return the configured Stripe price ID for a paid plan."""
    if plan.price_id_env is None:
        raise UnknownPlanError(f"Plan `{plan.code}` is not a paid plan.")
    value = os.getenv(plan.price_id_env, "").strip()
    if not value:
        raise BillingNotConfiguredError(
            f"{plan.price_id_env} is not configured. Set it to the matching Stripe price ID.",
        )
    return value


def stripe_client() -> stripe:
    """Return the Stripe SDK module with `api_key` set, or raise if missing."""
    secret = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not secret:
        raise BillingNotConfiguredError(
            "STRIPE_SECRET_KEY is not configured."
        )
    stripe.api_key = secret
    return stripe


def webhook_secret() -> str:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise BillingNotConfiguredError("STRIPE_WEBHOOK_SECRET is not configured.")
    return secret
