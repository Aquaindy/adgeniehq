"""Pluggable payment-processor abstraction for collecting platform fees.

The fee ledger (`fee_accruals`) is processor-agnostic — it records what's owed.
This layer turns a batch of accrued fees into an actual bill through whichever
processor a workspace/admin chooses. Adding Stripe, Paddle, PayPal, or a manual
off-platform invoice is one adapter file + a registry entry; the billing
service and ledger never change."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar
from uuid import UUID

from app.core.exceptions import AdVantaError


class PaymentError(AdVantaError):
    status_code = 502
    code = "payment_error"


class PaymentNotConfiguredError(AdVantaError):
    status_code = 503
    code = "payment_not_configured"


@dataclass
class InvoiceLine:
    description: str
    amount_cents: int
    accrual_id: UUID


@dataclass
class InvoiceCustomer:
    workspace_id: UUID
    email: str | None
    # Processor-native customer id, when one already exists (e.g. Stripe).
    external_customer_id: str | None = None


@dataclass
class InvoiceResult:
    # Processor's invoice id + hosted page, when applicable.
    external_id: str | None
    hosted_url: str | None
    # Whether the processor considers the bill issued/open (vs. just recorded).
    issued: bool
    raw: dict = field(default_factory=dict)


class PaymentProvider:
    """Collection-layer adapter. Subclasses create a real invoice for a batch
    of fee lines and report back enough to reconcile the local FeeInvoice row."""

    provider_id: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str]

    @classmethod
    def is_configured(cls) -> bool:
        """Whether this processor can be used (creds present). Manual is always
        available; Stripe/Paddle need env config."""
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
        raise PaymentNotConfiguredError(
            f"{cls.display_name} cannot create invoices in this environment."
        )

    @classmethod
    def catalog_entry(cls) -> dict:
        return {
            "provider": cls.provider_id,
            "display_name": cls.display_name,
            "description": cls.description,
            "configured": cls.is_configured(),
        }
