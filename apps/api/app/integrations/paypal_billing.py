"""PayPal Subscriptions wiring for *recurring subscriptions* (the AdGenieHQ plans).

PayPal is the sole recurring-subscription processor (Paddle was removed — it
never approved the domain). Unlike Paddle's client-side overlay, PayPal uses a
**server-created subscription + redirect**: we call `POST /v1/billing/subscriptions`
with the plan id, get back an approval URL, redirect the buyer there, and PayPal
sends webhooks (`BILLING.SUBSCRIPTION.*`) once they approve.

This is separate from `app.payments.paypal`, which bills one-off fee *invoices*
via the Invoicing API. Both share the same OAuth client-credentials app, so the
`PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` / `PAYPAL_API_BASE` env vars are
reused here.

Config (all via env):
  PAYPAL_CLIENT_ID          OAuth client id (shared with the fee adapter)
  PAYPAL_CLIENT_SECRET      OAuth client secret
  PAYPAL_API_BASE           override; else derived from PAYPAL_ENVIRONMENT
  PAYPAL_ENVIRONMENT        "sandbox" | "live" (default live)
  PAYPAL_WEBHOOK_ID         the webhook id from the PayPal dashboard (used to
                            verify inbound event signatures)
  PAYPAL_PLAN_ID_STARTER    monthly PayPal Billing Plan id per paid plan; the
  PAYPAL_PLAN_ID_PRO        yearly plan for each is PAYPAL_PLAN_ID_<PLAN>_ANNUAL
  PAYPAL_PLAN_ID_AGENCY     (e.g. PAYPAL_PLAN_ID_STARTER_ANNUAL)

Without CLIENT_ID + CLIENT_SECRET + WEBHOOK_ID the subscription endpoints report
not-configured (503) — nothing is ever silently accepted."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.billing.plans import BillingNotConfiguredError, PLANS
from app.core.exceptions import AdGenieError
from app.models.billing_subscription import SubscriptionStatus

# PayPal's own management page — there is no per-customer hosted portal like
# Paddle's, so "Manage billing" points the buyer at their PayPal autopay list.
PAYPAL_AUTOPAY_URL = "https://www.paypal.com/myaccount/autopay/"


class PayPalSignatureError(AdGenieError):
    status_code = 400
    code = "invalid_webhook_signature"


class PayPalApiError(AdGenieError):
    status_code = 502
    code = "paypal_api_error"


# Plan code -> env var holding its PayPal Billing Plan id. Only paid, public plans.
_PLAN_PLAN_ENV: dict[str, str] = {
    "starter": "PAYPAL_PLAN_ID_STARTER",
    "pro": "PAYPAL_PLAN_ID_PRO",
    "agency": "PAYPAL_PLAN_ID_AGENCY",
}

# PayPal subscription status -> our SubscriptionStatus.
_STATUS_MAP: dict[str, SubscriptionStatus] = {
    "APPROVAL_PENDING": SubscriptionStatus.INCOMPLETE,
    "APPROVED": SubscriptionStatus.INCOMPLETE,
    "ACTIVE": SubscriptionStatus.ACTIVE,
    "SUSPENDED": SubscriptionStatus.PAST_DUE,
    "CANCELLED": SubscriptionStatus.CANCELED,
    "EXPIRED": SubscriptionStatus.CANCELED,
}


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def is_configured() -> bool:
    """PayPal subscriptions are usable only with OAuth creds (server calls) and a
    webhook id (so inbound events can be verified)."""
    return bool(
        _env("PAYPAL_CLIENT_ID")
        and _env("PAYPAL_CLIENT_SECRET")
        and _env("PAYPAL_WEBHOOK_ID")
    )


def environment() -> str:
    return _env("PAYPAL_ENVIRONMENT") or "live"


def _api_base() -> str:
    """Server API base. Honor an explicit PAYPAL_API_BASE override (shared with
    the fee adapter); otherwise derive it from PAYPAL_ENVIRONMENT."""
    override = _env("PAYPAL_API_BASE")
    if override:
        return override.rstrip("/")
    return (
        "https://api-m.sandbox.paypal.com"
        if environment() == "sandbox"
        else "https://api-m.paypal.com"
    )


def _creds() -> tuple[str, str]:
    cid = _env("PAYPAL_CLIENT_ID")
    secret = _env("PAYPAL_CLIENT_SECRET")
    if not cid or not secret:
        raise BillingNotConfiguredError(
            "PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are not configured."
        )
    return cid, secret


def _access_token() -> str:
    cid, secret = _creds()
    try:
        resp = httpx.post(
            f"{_api_base()}/v1/oauth2/token",
            auth=(cid, secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise PayPalApiError(f"Could not reach PayPal: {exc}") from exc
    if resp.status_code >= 400:
        raise PayPalApiError(f"PayPal auth failed: HTTP {resp.status_code}.")
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Plan <-> PayPal Billing Plan id mapping
# ---------------------------------------------------------------------------


def _plan_env_name(plan_code: str, interval: str) -> str | None:
    """Env var holding the PayPal Plan id for (plan, interval). Annual plans live
    under the `_ANNUAL` suffix."""
    base = _PLAN_PLAN_ENV.get(plan_code)
    if base is None:
        return None
    return base if interval == "month" else f"{base}_ANNUAL"


def plan_id_for_plan(plan_code: str, interval: str = "month") -> str:
    """Resolve the PayPal Billing Plan id for a plan + billing interval
    (`"month"` | `"year"`)."""
    env_name = _plan_env_name(plan_code, interval)
    if env_name is None:
        raise BillingNotConfiguredError(f"Plan `{plan_code}` is not a paid PayPal plan.")
    value = _env(env_name)
    if not value:
        raise BillingNotConfiguredError(
            f"{env_name} is not configured. Set it to the matching PayPal Plan id."
        )
    return value


def plan_for_plan_id(plan_id: str | None) -> str | None:
    """Map a PayPal Plan id (monthly OR annual) back to its plan code."""
    if not plan_id:
        return None
    for plan_code, base in _PLAN_PLAN_ENV.items():
        if _env(base) == plan_id or _env(f"{base}_ANNUAL") == plan_id:
            return plan_code
    return None


def map_status(paypal_status: str | None) -> SubscriptionStatus:
    return _STATUS_MAP.get((paypal_status or "").upper(), SubscriptionStatus.INCOMPLETE)


# ---------------------------------------------------------------------------
# Subscription lifecycle
# ---------------------------------------------------------------------------


def create_subscription(
    *,
    plan_id: str,
    subscriber_email: str,
    custom_id: str,
    return_url: str,
    cancel_url: str,
) -> dict[str, str]:
    """Create a PayPal subscription and return `{id, approval_url}`. The buyer
    must be redirected to `approval_url` to approve; activation is confirmed via
    the BILLING.SUBSCRIPTION.ACTIVATED webhook."""
    token = _access_token()
    body: dict[str, Any] = {
        "plan_id": plan_id,
        "custom_id": custom_id,
        "subscriber": {"email_address": subscriber_email},
        "application_context": {
            "brand_name": "AdGenieHQ",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "SUBSCRIBE_NOW",
            "payment_method": {
                "payer_selected": "PAYPAL",
                "payee_preferred": "IMMEDIATE_PAYMENT_REQUIRED",
            },
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }
    try:
        resp = httpx.post(
            f"{_api_base()}/v1/billing/subscriptions",
            headers=_auth_headers(token),
            json=body,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise PayPalApiError(f"Could not reach PayPal: {exc}") from exc
    if resp.status_code >= 400:
        raise PayPalApiError(
            f"PayPal subscription create failed: HTTP {resp.status_code} {resp.text[:200]}"
        )
    data = resp.json() if resp.content else {}
    approval_url = None
    for link in data.get("links") or []:
        if link.get("rel") == "approve":
            approval_url = link.get("href")
            break
    if not data.get("id") or not approval_url:
        raise PayPalApiError("PayPal did not return a subscription approval link.")
    return {"id": data["id"], "approval_url": approval_url}


def get_subscription(subscription_id: str) -> dict[str, Any] | None:
    """Fetch a subscription resource on demand (status, plan, billing_info).
    Returns None on any problem so callers can degrade gracefully."""
    if not subscription_id:
        return None
    try:
        token = _access_token()
        resp = httpx.get(
            f"{_api_base()}/v1/billing/subscriptions/{subscription_id}",
            headers=_auth_headers(token),
            timeout=20.0,
        )
    except (httpx.HTTPError, AdGenieError):
        return None
    if resp.status_code >= 400:
        return None
    return resp.json() if resp.content else None


def cancel_subscription(subscription_id: str, *, reason: str = "Cancelled by customer") -> bool:
    """Cancel an active PayPal subscription. Returns True on success (HTTP 204)."""
    if not subscription_id:
        return False
    try:
        token = _access_token()
        resp = httpx.post(
            f"{_api_base()}/v1/billing/subscriptions/{subscription_id}/cancel",
            headers=_auth_headers(token),
            json={"reason": reason[:127]},
            timeout=20.0,
        )
    except (httpx.HTTPError, AdGenieError):
        return False
    return resp.status_code < 400


def management_url() -> str:
    """PayPal has no per-customer hosted portal; point buyers at their autopay
    list where they can view and cancel subscriptions."""
    return PAYPAL_AUTOPAY_URL


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

# Request headers PayPal signs each webhook with.
_SIG_HEADERS = {
    "auth_algo": "paypal-auth-algo",
    "cert_url": "paypal-cert-url",
    "transmission_id": "paypal-transmission-id",
    "transmission_sig": "paypal-transmission-sig",
    "transmission_time": "paypal-transmission-time",
}


def _webhook_id() -> str:
    wid = _env("PAYPAL_WEBHOOK_ID")
    if not wid:
        raise BillingNotConfiguredError("PAYPAL_WEBHOOK_ID is not configured.")
    return wid


def verify_webhook(headers: dict[str, str], event: dict[str, Any]) -> None:
    """Verify an inbound webhook against PayPal's verification API using the
    configured webhook id. `headers` is a case-insensitive-lowercased mapping of
    the request headers; `event` is the parsed JSON body. Raises
    PayPalSignatureError on any missing header or non-SUCCESS status."""
    webhook_id = _webhook_id()
    lowered = {k.lower(): v for k, v in headers.items()}
    sig = {field: lowered.get(hdr) for field, hdr in _SIG_HEADERS.items()}
    if not all(sig.values()):
        missing = [f for f, v in sig.items() if not v]
        raise PayPalSignatureError(f"Missing PayPal signature headers: {missing}.")

    payload = {**sig, "webhook_id": webhook_id, "webhook_event": event}
    try:
        token = _access_token()
        resp = httpx.post(
            f"{_api_base()}/v1/notifications/verify-webhook-signature",
            headers=_auth_headers(token),
            json=payload,
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise PayPalSignatureError(f"Could not reach PayPal to verify: {exc}") from exc
    if resp.status_code >= 400:
        raise PayPalSignatureError(
            f"PayPal signature verification failed: HTTP {resp.status_code}."
        )
    status = (resp.json() or {}).get("verification_status")
    if status != "SUCCESS":
        raise PayPalSignatureError(f"PayPal webhook not verified (status={status}).")


# Plans offered for PayPal checkout (paid + public only).
def public_paid_plan_codes() -> list[str]:
    return [code for code, plan in PLANS.items() if plan.is_public and plan.paid]
