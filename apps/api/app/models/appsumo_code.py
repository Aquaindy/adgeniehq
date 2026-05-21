from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AppSumoCodeStatus(StrEnum):
    UNREDEEMED = "unredeemed"
    REDEEMED = "redeemed"
    # AppSumo refund / chargeback. Deactivating revokes the grant and
    # recomputes the workspace's tier (downgrades, or back to free at 0 codes).
    REFUNDED = "refunded"


class AppSumoCode(Base, TimestampMixin):
    """A single AppSumo lifetime-deal redemption code.

    Codes are generated in batches (then uploaded to AppSumo), uniform — no
    per-code tier — and redeemed on `/appsumo/redeem`. A workspace's tier is
    the count of its REDEEMED codes, capped at `APPSUMO_MAX_TIER`: codes stack
    (1 = Tier 1, 2 = Tier 2, 3 = Tier 3)."""

    __tablename__ = "appsumo_codes"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[AppSumoCodeStatus] = mapped_column(
        Enum(AppSumoCodeStatus, name="appsumo_code_status"),
        nullable=False,
        default=AppSumoCodeStatus.UNREDEEMED,
        index=True,
    )
    # Free-text label for the batch a code was generated in (e.g. "launch-2026").
    batch: Mapped[str | None] = mapped_column(String(64), index=True)

    # Set on redemption. SET NULL on workspace/user deletion so the code row
    # (and its redeemed history) survives, but can be re-evaluated.
    workspace_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        index=True,
    )
    redeemed_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AppSumoCode code={self.code} status={self.status} ws={self.workspace_id}>"
