"""PayPal collection provider (Invoicing API).

Creates and sends a PayPal invoice for the accrued fees, returning the payer's
hosted invoice link. Uses OAuth2 client-credentials for auth.

Config: ``PAYPAL_CLIENT_ID`` + ``PAYPAL_CLIENT_SECRET`` (required); ``PAYPAL_API_BASE``
to point at sandbox (``https://api-m.sandbox.paypal.com``). PayPal amounts are
decimal strings in major currency units (dollars)."""

from __future__ import annotations

import os
from typing import ClassVar

import httpx

from app.payments.base import (
    InvoiceCustomer,
    InvoiceLine,
    InvoiceResult,
    PaymentError,
    PaymentNotConfiguredError,
    PaymentProvider,
)


def _base() -> str:
    return os.getenv("PAYPAL_API_BASE", "https://api-m.paypal.com").rstrip("/")


def _creds() -> tuple[str, str]:
    cid = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise PaymentNotConfiguredError(
            "PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are not configured."
        )
    return cid, secret


def _access_token() -> str:
    cid, secret = _creds()
    resp = httpx.post(
        f"{_base()}/v1/oauth2/token",
        auth=(cid, secret),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json"},
        timeout=20.0,
    )
    if resp.status_code >= 400:
        raise PaymentError(f"PayPal auth failed: HTTP {resp.status_code}.")
    return resp.json()["access_token"]


class PayPalPaymentProvider(PaymentProvider):
    provider_id: ClassVar[str] = "paypal"
    display_name: ClassVar[str] = "PayPal"
    description: ClassVar[str] = (
        "Bills accrued fees as a PayPal invoice and emails the payer a hosted "
        "link. Configure PAYPAL_CLIENT_ID + PAYPAL_CLIENT_SECRET to enable."
    )

    @classmethod
    def is_configured(cls) -> bool:
        return bool(
            os.getenv("PAYPAL_CLIENT_ID", "").strip()
            and os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
        )

    @classmethod
    def create_invoice(
        cls,
        *,
        customer: InvoiceCustomer,
        currency: str,
        lines: list[InvoiceLine],
        period: str | None,
        metadata: dict,
    ) -> InvoiceResult:
        try:
            token = _access_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            cur = currency.upper()
            items = [
                {
                    "name": ln.description[:200],
                    "quantity": "1",
                    "unit_amount": {
                        "currency_code": cur,
                        "value": f"{ln.amount_cents / 100:.2f}",
                    },
                }
                for ln in lines
            ]
            body: dict = {"detail": {"currency_code": cur}, "items": items}
            if customer.email:
                body["primary_recipients"] = [
                    {"billing_info": {"email_address": customer.email}}
                ]
            resp = httpx.post(
                f"{_base()}/v2/invoicing/invoices", headers=headers, json=body, timeout=30.0
            )
            if resp.status_code >= 400:
                raise PaymentError(
                    f"PayPal invoice create failed: HTTP {resp.status_code} {resp.text[:200]}"
                )
            created = resp.json() if resp.content else {}
            # The create response references the new invoice by href.
            href = created.get("href", "")
            invoice_id = href.rstrip("/").split("/")[-1] if href else created.get("id")

            hosted_url = None
            if invoice_id:
                send = httpx.post(
                    f"{_base()}/v2/invoicing/invoices/{invoice_id}/send",
                    headers=headers,
                    json={"send_to_recipient": True},
                    timeout=30.0,
                )
                if send.status_code < 400 and send.content:
                    hosted_url = send.json().get("href")
        except httpx.HTTPError as exc:
            raise PaymentError(f"Could not reach PayPal: {exc}") from exc

        return InvoiceResult(
            external_id=invoice_id,
            hosted_url=hosted_url,
            issued=True,
            raw={"sent": hosted_url is not None},
        )
