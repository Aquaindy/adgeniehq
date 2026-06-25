"""Fee-accrual no-double-bill unique indexes + BigInteger cents + autopilot DB defaults

- Partial unique indexes on fee_accruals so a concurrent/retried accrual can't
  double-bill (run fees: campaign+type+period; listing fees: campaign+type once).
- Widen fee_accruals cents columns to BigInteger (int32 cents caps ~$21.4M).
- Server-default autopilot_configs.mode='off' / stop_loss_active=false so a
  config row defaults to a safe, OFF state at the database level.

Revision ID: d2b4f6a8c0e1
Revises: c1a3e5b7d9f2
Create Date: 2026-06-25 05:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2b4f6a8c0e1'
down_revision: Union[str, None] = 'c1a3e5b7d9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- fee_accruals: widen money columns --------------------------------
    op.alter_column('fee_accruals', 'amount_cents', type_=sa.BigInteger(), existing_nullable=False)
    op.alter_column('fee_accruals', 'basis_spend_cents', type_=sa.BigInteger(), existing_nullable=True)

    # --- fee_accruals: no-double-bill partial unique indexes --------------
    op.create_index(
        'uq_fee_accrual_run_period',
        'fee_accruals',
        ['campaign_id', 'fee_type', 'period'],
        unique=True,
        postgresql_where=sa.text("status <> 'void' AND period IS NOT NULL"),
    )
    op.create_index(
        'uq_fee_accrual_listing',
        'fee_accruals',
        ['campaign_id', 'fee_type'],
        unique=True,
        postgresql_where=sa.text("status <> 'void' AND period IS NULL"),
    )

    # --- autopilot_configs: safe DB-level defaults ------------------------
    op.alter_column('autopilot_configs', 'mode', server_default='off', existing_nullable=False)
    op.alter_column(
        'autopilot_configs', 'stop_loss_active',
        server_default=sa.text('false'), existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column('autopilot_configs', 'stop_loss_active', server_default=None, existing_nullable=False)
    op.alter_column('autopilot_configs', 'mode', server_default=None, existing_nullable=False)
    op.drop_index('uq_fee_accrual_listing', table_name='fee_accruals')
    op.drop_index('uq_fee_accrual_run_period', table_name='fee_accruals')
    op.alter_column('fee_accruals', 'basis_spend_cents', type_=sa.Integer(), existing_nullable=True)
    op.alter_column('fee_accruals', 'amount_cents', type_=sa.Integer(), existing_nullable=False)
