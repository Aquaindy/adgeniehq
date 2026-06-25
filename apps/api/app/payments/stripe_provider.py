"""Stripe collection provider.

Bills a batch of accrued fees as a one-off Stripe invoice against the
workspace's existing Stripe customer (created by the subscription flow). Each
fee line becomes a Stripe invoice item; the invoice is finalized + sent so the
customer gets a hosted payment page. Requires STRIPE_SECRET_KEY."""

from __future__ import annotations

import os
from typing import ClassVar

from app.integrations.stripe import stripe_client
from app.payments.base import (
    InvoiceCustomer,
    InvoiceLine,
    InvoiceResult,
    PaymentError,
    PaymentProvider,
)


class StripePaymentProvider(PaymentProvider):
    provider_id: ClassVar[str] = "stripe"
    display_name: ClassVar[str] = "Stripe"
    description: ClassVar[str] = (
        "Bill accrued fees as a Stripe invoice against the workspace's Stripe "
        "customer. Sends a hosted payment page."
    )

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("STRIPE_SECRET_KEY", "").strip())

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
        if not customer.external_customer_id:
            raise PaymentError(
                "This workspace has no Stripe customer yet. Start a subscription "
                "or create the customer before billing fees through Stripe."
            )
        sdk = stripe_client()  # sets api_key / raises if STRIPE_SECRET_KEY missing
        cur = currency.lower()
        try:
            for line in lines:
                sdk.InvoiceItem.create(
                    customer=customer.external_customer_id,
                    amount=int(line.amount_cents),
                    currency=cur,
                    description=line.description,
                    metadata={"accrual_id": str(line.accrual_id)},
                )
            invoice = sdk.Invoice.create(
                customer=customer.external_customer_id,
                collection_method="send_invoice",
                days_until_due=14,
                auto_advance=True,
                metadata={k: str(v) for k, v in metadata.items()},
            )
            finalized = sdk.Invoice.finalize_invoice(invoice["id"])
        except Exception as exc:  # noqa: BLE001 — normalize SDK errors
            raise PaymentError(f"Stripe invoice creation failed: {exc}") from exc

        return InvoiceResult(
            external_id=finalized.get("id"),
            hosted_url=finalized.get("hosted_invoice_url"),
            issued=True,
            raw={"status": finalized.get("status")},
        )
