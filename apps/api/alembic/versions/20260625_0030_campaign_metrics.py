"""Analytics: campaign_metrics daily performance time-series

One row per (campaign, date) holding raw counters (impressions, clicks, spend,
conversions, conversion value). Derived KPIs are computed on read. Populated by
the per-platform insights sync.

Revision ID: e5a7c9b1d3f6
Revises: d4f6a8c0e2b5
Create Date: 2026-06-25 00:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e5a7c9b1d3f6'
down_revision: Union[str, None] = 'd4f6a8c0e2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'campaign_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('impressions', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('clicks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('spend_cents', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('conversions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('conversion_value_cents', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'date', name='uq_campaign_metrics_campaign_date'),
    )
    op.create_index('ix_campaign_metrics_workspace_id', 'campaign_metrics', ['workspace_id'])
    op.create_index('ix_campaign_metrics_campaign_id', 'campaign_metrics', ['campaign_id'])
    op.create_index('ix_campaign_metrics_date', 'campaign_metrics', ['date'])


def downgrade() -> None:
    op.drop_table('campaign_metrics')
