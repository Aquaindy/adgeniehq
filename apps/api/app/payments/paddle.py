"""Paddle collection provider (Merchant-of-Record).

Bills accrued fees as a Paddle Billing transaction with non-catalog items
(collection_mode=manual), so the customer receives a Paddle-hosted invoice.
Paddle acts as merchant of record, handling global sales tax / VAT.

Config: ``PADDLE_API_KEY`` (required); ``PADDLE_API_BASE`` to point at sandbox
(``https://sandbox-api.paddle.com``). Amounts are sent in the smallest currency
unit (cents) as Paddle expects."""

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
    return os.getenv("PADDLE_API_BASE", "https://api.paddle.com").rstrip("/")


def _headers() -> dict[str, str]:
    key = os.getenv("PADDLE_API_KEY", "").strip()
    if not key:
        raise PaymentNotConfiguredError("PADDLE_API_KEY is not configured.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


class PaddlePaymentProvider(PaymentProvider):
    provider_id: ClassVar[str] = "paddle"
    display_name: ClassVar[str] = "Paddle"
    description: ClassVar[str] = (
        "Merchant-of-Record billing (handles global sales tax/VAT). Bills fees as "
        "a Paddle invoice. Configure PADDLE_API_KEY to enable."
    )

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("PADDLE_API_KEY", "").strip())

    @classmethod
    def _resolve_customer_id(
        cls, headers: dict, customer: InvoiceCustomer
    ) -> str | None:
        if customer.external_customer_id:
            return customer.external_customer_id
        if not customer.email:
            return None
        # Create the customer; Paddle 409s if the email already exists, in which
        # case we look it up.
        resp = httpx.post(
            f"{_base()}/customers",
            headers=headers,
            json={"email": customer.email},
            timeout=20.0,
        )
        if resp.status_code == 409:
            listed = httpx.get(
                f"{_base()}/customers",
                headers=headers,
                params={"email": customer.email},
                timeout=20.0,
            )
            data = listed.json().get("data", []) if listed.status_code < 400 else []
            return data[0]["id"] if data else None
        if resp.status_code >= 400:
            raise PaymentError(
                f"Paddle customer create failed: HTTP {resp.status_code} {resp.text[:160]}"
            )
        return resp.json().get("data", {}).get("id")

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
        headers = _headers()
        try:
            customer_id = cls._resolve_customer_id(headers, customer)
            items = [
                {
                    "quantity": 1,
                    "price": {
                        "description": ln.description[:200],
                        "unit_price": {
                            "amount": str(int(ln.amount_cents)),
                            "currency_code": currency.upper(),
                        },
                        "product": {
                            "name": ln.description[:200],
                            "tax_category": "standard",
                        },
                    },
                }
                for ln in lines
            ]
            body: dict = {
                "items": items,
                "collection_mode": "manual",
                "custom_data": {k: str(v) for k, v in metadata.items()},
            }
            if customer_id:
                body["customer_id"] = customer_id
            resp = httpx.post(
                f"{_base()}/transactions", headers=headers, json=body, timeout=30.0
            )
        except httpx.HTTPError as exc:
            raise PaymentError(f"Could not reach Paddle: {exc}") from exc
        if resp.status_code >= 400:
            raise PaymentError(
                f"Paddle transaction create failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
        data = resp.json().get("data", {})
        checkout = data.get("checkout") or {}
        return InvoiceResult(
            external_id=data.get("id"),
            hosted_url=checkout.get("url"),
            issued=True,
            raw={"status": data.get("status")},
        )
