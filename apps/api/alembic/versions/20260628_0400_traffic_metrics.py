"""traffic_metrics (per campaign/source/day results)

Phase 6 — Advanced Analytics. Operator-logged or imported traffic performance
that powers source/campaign comparison, the quality score, and profitability.

Revision ID: e5c3f9a2b7d1
Revises: d4b2e8c1a9f6
Create Date: 2026-06-28 04:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e5c3f9a2b7d1'
down_revision: Union[str, None] = 'd4b2e8c1a9f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'traffic_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('traffic_campaign_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_slug', sa.String(length=64), nullable=False),
        sa.Column('medium', sa.String(length=64), nullable=True),
        sa.Column('date', sa.Date(), nullable=True),
        sa.Column('visitors', sa.Integer(), server_default='0', nullable=False),
        sa.Column('sessions', sa.Integer(), server_default='0', nullable=False),
        sa.Column('clicks', sa.Integer(), server_default='0', nullable=False),
        sa.Column('unique_clicks', sa.Integer(), server_default='0', nullable=False),
        sa.Column('leads', sa.Integer(), server_default='0', nullable=False),
        sa.Column('sales', sa.Integer(), server_default='0', nullable=False),
        sa.Column('revenue_cents', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('cost_cents', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('bounce_rate', sa.Float(), nullable=True),
        sa.Column('avg_session_duration_sec', sa.Integer(), nullable=True),
        sa.Column('email_opens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('email_clicks', sa.Integer(), server_default='0', nullable=False),
        sa.Column('unsubscribes', sa.Integer(), server_default='0', nullable=False),
        sa.Column('spam_complaints', sa.Integer(), server_default='0', nullable=False),
        sa.Column('refunds', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['traffic_campaign_id'], ['traffic_campaigns.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_traffic_metrics_workspace_id', 'traffic_metrics', ['workspace_id'])
    op.create_index('ix_traffic_metrics_traffic_campaign_id', 'traffic_metrics', ['traffic_campaign_id'])
    op.create_index('ix_traffic_metrics_source_slug', 'traffic_metrics', ['source_slug'])
    op.create_index('ix_traffic_metrics_date', 'traffic_metrics', ['date'])


def downgrade() -> None:
    op.drop_index('ix_traffic_metrics_date', table_name='traffic_metrics')
    op.drop_index('ix_traffic_metrics_source_slug', table_name='traffic_metrics')
    op.drop_index('ix_traffic_metrics_traffic_campaign_id', table_name='traffic_metrics')
    op.drop_index('ix_traffic_metrics_workspace_id', table_name='traffic_metrics')
    op.drop_table('traffic_metrics')
