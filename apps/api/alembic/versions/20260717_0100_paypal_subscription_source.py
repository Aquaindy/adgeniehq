"""Add PAYPAL to the subscription_source enum

Recurring plan billing moved from Paddle (which never approved the domain) to
**PayPal**. Adds a `PAYPAL` label to the `subscription_source` enum
(member-name casing, matching the existing STRIPE/APPSUMO/PADDLE convention).
`PADDLE` is left in place as an inert tombstone — Postgres can't easily drop an
enum value, and no new rows are written with it.

Revision ID: e7b2c4d6f8a0
Revises: d4f6b8c0a2e3
Create Date: 2026-07-17 01:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e7b2c4d6f8a0'
down_revision: Union[str, None] = 'd4f6b8c0a2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block; use the
    # Alembic autocommit escape hatch. IF NOT EXISTS keeps it idempotent.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE subscription_source ADD VALUE IF NOT EXISTS 'PAYPAL'")


def downgrade() -> None:
    # Postgres can't drop a single enum value without recreating the type;
    # 'PAYPAL' is left in place on downgrade (harmless once no rows reference it).
    pass
