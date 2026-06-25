"""Paddle Billing wiring for *recurring subscriptions* (the AdVanta plans).

This is separate from `app.payments.paddle`, which bills one-off fee invoices.
Here we map our plan catalog to Paddle Price IDs, expose the client-side
checkout config (Paddle.js opens an overlay — there is no server redirect URL
like Stripe), and verify inbound webhook signatures.

Config (all via env, mirroring the Stripe integration so the same code runs
against sandbox + live):
  PADDLE_API_KEY            server API key (shared with the fee adapter)
  PADDLE_CLIENT_TOKEN       publishable client-side token for Paddle.js
  PADDLE_WEBHOOK_SECRET     notification-destination secret (HMAC key)
  PADDLE_ENVIRONMENT        "sandbox" | "production" (default production)
  PADDLE_PRICE_ID_STARTER   Paddle Price ID for each paid plan
  PADDLE_PRICE_ID_PRO
  PADDLE_PRICE_ID_AGENCY

Without PADDLE_API_KEY + PADDLE_WEBHOOK_SECRET the subscription endpoints
report not-configured (503) — nothing is ever silently accepted."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from app.core.exceptions import AdVantaError
from app.integrations.stripe import BillingNotConfiguredError, PLANS
from app.models.billing_subscription import SubscriptionStatus


class PaddleSignatureError(AdVantaError):
    status_code = 400
    code = "invalid_webhook_signature"


# Plan code -> env var holding its Paddle Price ID. Only paid, public plans.
_PLAN_PRICE_ENV: dict[str, str] = {
    "starter": "PADDLE_PRICE_ID_STARTER",
    "pro": "PADDLE_PRICE_ID_PRO",
    "agency": "PADDLE_PRICE_ID_AGENCY",
}

# Paddle subscription status -> our SubscriptionStatus.
_STATUS_MAP: dict[str, SubscriptionStatus] = {
    "active": SubscriptionStatus.ACTIVE,
    "trialing": SubscriptionStatus.TRIALING,
    "past_due": SubscriptionStatus.PAST_DUE,
    "paused": SubscriptionStatus.PAUSED,
    "canceled": SubscriptionStatus.CANCELED,
}


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def is_configured() -> bool:
    """Paddle subscriptions are usable only with both an API key (server) and a
    webhook secret (so inbound events can be trusted)."""
    return bool(_env("PADDLE_API_KEY") and _env("PADDLE_WEBHOOK_SECRET"))


def environment() -> str:
    return _env("PADDLE_ENVIRONMENT") or "production"


def client_token() -> str:
    token = _env("PADDLE_CLIENT_TOKEN")
    if not token:
        raise BillingNotConfiguredError("PADDLE_CLIENT_TOKEN is not configured.")
    return token


def price_id_for_plan(plan_code: str) -> str:
    env_name = _PLAN_PRICE_ENV.get(plan_code)
    if env_name is None:
        raise BillingNotConfiguredError(f"Plan `{plan_code}` is not a paid Paddle plan.")
    value = _env(env_name)
    if not value:
        raise BillingNotConfiguredError(
            f"{env_name} is not configured. Set it to the matching Paddle Price ID."
        )
    return value


def plan_for_price_id(price_id: str | None) -> str | None:
    if not price_id:
        return None
    for plan_code, env_name in _PLAN_PRICE_ENV.items():
        if _env(env_name) == price_id:
            return plan_code
    return None


def map_status(paddle_status: str | None) -> SubscriptionStatus:
    return _STATUS_MAP.get((paddle_status or "").lower(), SubscriptionStatus.ACTIVE)


def _webhook_secret() -> str:
    secret = _env("PADDLE_WEBHOOK_SECRET")
    if not secret:
        raise BillingNotConfiguredError("PADDLE_WEBHOOK_SECRET is not configured.")
    return secret


def verify_webhook(payload: bytes, signature: str | None) -> dict[str, Any]:
    """Verify the `Paddle-Signature: ts=..;h1=..` header against the raw body
    and return the parsed event. Raises PaddleSignatureError on any mismatch."""
    secret = _webhook_secret()
    if not signature:
        raise PaddleSignatureError("Missing Paddle-Signature header.")

    parts = dict(p.split("=", 1) for p in signature.split(";") if "=" in p)
    ts = parts.get("ts")
    h1 = parts.get("h1")
    if not ts or not h1:
        raise PaddleSignatureError("Malformed Paddle-Signature header.")

    signed = ts.encode("utf-8") + b":" + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, h1):
        raise PaddleSignatureError("Paddle signature verification failed.")

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PaddleSignatureError("Invalid Paddle webhook body.") from exc


# Plans offered for Paddle checkout (paid + public only).
def public_paid_plan_codes() -> list[str]:
    return [code for code, plan in PLANS.items() if plan.is_public and plan.price_id_env]
