"""Fee engine: fee_rules (schedule) + fee_accruals (ledger)

Adds the provider-agnostic platform-fee foundation:
  * `fee_rules` — admin-configurable fee schedule keyed by (provider, campaign_type),
    NULL = wildcard. listing_fee_cents (one-time per launch), run_flat_fee_cents
    (flat per period), run_pct_basis_points (% of spend).
  * `fee_accruals` — ledger of fees owed by a workspace. The payment processor
    (Stripe/Paddle/PayPal) later bills ACCRUED rows, so this stays processor-agnostic.

Revision ID: c3e5f7a9b1d4
Revises: b2d4f6a8c1e3
Create Date: 2026-06-24 23:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3e5f7a9b1d4'
down_revision: Union[str, None] = 'b2d4f6a8c1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fee_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=True),
        sa.Column('campaign_type', sa.String(length=64), nullable=True),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('listing_fee_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('run_flat_fee_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('run_pct_basis_points', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fee_rules_provider', 'fee_rules', ['provider'])
    op.create_index('ix_fee_rules_campaign_type', 'fee_rules', ['campaign_type'])

    fee_type = postgresql.ENUM('listing', 'run_flat', 'run_pct', name='fee_type')
    fee_type.create(op.get_bind(), checkfirst=True)
    accrual_status = postgresql.ENUM('accrued', 'invoiced', 'void', name='fee_accrual_status')
    accrual_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'fee_accruals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('fee_type', postgresql.ENUM('listing', 'run_flat', 'run_pct', name='fee_type', create_type=False), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=True),
        sa.Column('campaign_type', sa.String(length=64), nullable=True),
        sa.Column('period', sa.String(length=7), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('basis_spend_cents', sa.Integer(), nullable=True),
        sa.Column('status', postgresql.ENUM('accrued', 'invoiced', 'void', name='fee_accrual_status', create_type=False), nullable=False, server_default='accrued'),
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rule_id'], ['fee_rules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fee_accruals_workspace_id', 'fee_accruals', ['workspace_id'])
    op.create_index('ix_fee_accruals_campaign_id', 'fee_accruals', ['campaign_id'])
    op.create_index('ix_fee_accruals_fee_type', 'fee_accruals', ['fee_type'])
    op.create_index('ix_fee_accruals_period', 'fee_accruals', ['period'])
    op.create_index('ix_fee_accruals_status', 'fee_accruals', ['status'])


def downgrade() -> None:
    op.drop_table('fee_accruals')
    op.drop_table('fee_rules')
    postgresql.ENUM(name='fee_accrual_status').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='fee_type').drop(op.get_bind(), checkfirst=True)
