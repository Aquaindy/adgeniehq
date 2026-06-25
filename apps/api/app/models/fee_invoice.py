from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class FeeInvoiceStatus(StrEnum):
    DRAFT = "draft"        # row created, not yet sent to a processor
    OPEN = "open"          # issued, awaiting payment
    PAID = "paid"          # collected
    VOID = "void"          # cancelled
    FAILED = "failed"      # processor rejected creation


class FeeInvoice(Base, TimestampMixin):
    """A bill for a set of accrued platform fees.

    Created by the collection layer: it rolls a workspace's ACCRUED FeeAccrual
    rows into one invoice through a pluggable PaymentProvider (manual / Stripe /
    Paddle / …), then flips those accruals to INVOICED and links them here. The
    fee ledger stays processor-agnostic; only this row knows which processor
    issued the bill."""

    __tablename__ = "fee_invoices"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Payment processor that issued the bill: "manual" | "stripe" | "paddle" | …
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[FeeInvoiceStatus] = mapped_column(
        Enum(
            FeeInvoiceStatus,
            name="fee_invoice_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=FeeInvoiceStatus.DRAFT,
        index=True,
    )

    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # Billing period "YYYY-MM" when the invoice targets a single run period; NULL
    # for ad-hoc / mixed invoices (e.g. a listing fee + this month's run fees).
    period: Mapped[str | None] = mapped_column(String(7))
    accrual_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Processor references (NULL for manual invoices).
    external_id: Mapped[str | None] = mapped_column(String(255))
    hosted_url: Mapped[str | None] = mapped_column(String(1024))

    # Snapshot of the billed lines so the invoice is self-describing even if an
    # accrual is later edited/voided.
    line_items: Mapped[list | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    accruals = relationship("FeeAccrual", back_populates="invoice")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<FeeInvoice ws={self.workspace_id} provider={self.provider} "
            f"amount={self.amount_cents} status={self.status}>"
        )
