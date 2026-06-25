"""Manual / off-platform invoice provider.

The zero-config default: it records the bill as an OPEN invoice without touching
a payment processor. Use it to collect fees by wire/ACH/manual Stripe link, or
as the always-available fallback so fees are billed even before a processor is
wired up. Reconcile by marking the invoice paid once funds arrive."""

from __future__ import annotations

from typing import ClassVar

from app.payments.base import (
    InvoiceCustomer,
    InvoiceLine,
    InvoiceResult,
    PaymentProvider,
)


class ManualPaymentProvider(PaymentProvider):
    provider_id: ClassVar[str] = "manual"
    display_name: ClassVar[str] = "Manual invoice"
    description: ClassVar[str] = (
        "Record the bill in AdVanta and collect off-platform (wire/ACH/manual). "
        "Always available — no processor configuration required."
    )

    @classmethod
    def is_configured(cls) -> bool:
        return True

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
        # Nothing to call — the local FeeInvoice row is the record of truth.
        return InvoiceResult(
            external_id=None,
            hosted_url=None,
            issued=True,
            raw={"mode": "manual", "line_count": len(lines)},
        )
