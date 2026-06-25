from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class FeeType(StrEnum):
    LISTING = "listing"  # one-time, per campaign launch
    RUN_FLAT = "run_flat"  # flat per period
    RUN_PCT = "run_pct"  # percentage of spend per period


class FeeAccrualStatus(StrEnum):
    ACCRUED = "accrued"  # owed, not yet billed
    INVOICED = "invoiced"  # rolled into an invoice
    VOID = "void"  # reversed / cancelled


class FeeAccrual(Base, TimestampMixin):
    """A single ledger entry for a platform fee owed by a workspace.

    Provider-agnostic by design: this records what is *owed*. The collection
    layer (Stripe / Paddle / PayPal) later reads ACCRUED rows for a period and
    bills them, flipping them to INVOICED — so swapping payment processors never
    touches this ledger.
    """

    __tablename__ = "fee_accruals"
    __table_args__ = (
        # DB-level no-double-bill guarantee (the app-level check is a fast path
        # only; this is what makes a concurrent/retried accrual safe). Run fees
        # are unique per (campaign, type, period); listing fees are once per
        # (campaign, type) ever. Both ignore VOID rows so a reversed accrual can
        # be re-created.
        Index(
            "uq_fee_accrual_run_period",
            "campaign_id",
            "fee_type",
            "period",
            unique=True,
            postgresql_where=text("status <> 'void' AND period IS NOT NULL"),
        ),
        Index(
            "uq_fee_accrual_listing",
            "campaign_id",
            "fee_type",
            unique=True,
            postgresql_where=text("status <> 'void' AND period IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        index=True,
    )

    fee_type: Mapped[FeeType] = mapped_column(
        Enum(FeeType, name="fee_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    provider: Mapped[str | None] = mapped_column(String(64))
    campaign_type: Mapped[str | None] = mapped_column(String(64))

    # Billing period "YYYY-MM" for run fees; NULL for one-time listing fees.
    period: Mapped[str | None] = mapped_column(String(7), index=True)

    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # For percentage fees: the spend the percentage was applied to. BigInteger:
    # aggregate spend at agency scale can exceed the int32 cents ceiling (~$21M).
    basis_spend_cents: Mapped[int | None] = mapped_column(BigInteger)

    status: Mapped[FeeAccrualStatus] = mapped_column(
        Enum(
            FeeAccrualStatus,
            name="fee_accrual_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=FeeAccrualStatus.ACCRUED,
        index=True,
    )

    rule_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("fee_rules.id", ondelete="SET NULL")
    )
    # Set when this accrual is rolled into an invoice by the collection layer.
    invoice_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("fee_invoices.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)

    invoice = relationship("FeeInvoice", back_populates="accruals")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<FeeAccrual ws={self.workspace_id} type={self.fee_type} "
            f"amount={self.amount_cents} status={self.status}>"
        )
