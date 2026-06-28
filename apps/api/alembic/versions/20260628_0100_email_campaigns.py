"""email_campaigns (ESP email-campaign analytics, e.g. Omnisend)

Stores email campaigns pulled from an autoresponder/ESP with their engagement +
deliverability metrics, optionally linked to a paid-ads campaign.

Revision ID: b8d0f2a4c6e9
Revises: a7f2c9d4e6b1
Create Date: 2026-06-28 01:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b8d0f2a4c6e9'
down_revision: Union[str, None] = 'a7f2c9d4e6b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'email_campaigns',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('external_id', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=512), nullable=True),
        sa.Column('subject', sa.String(length=998), nullable=True),
        sa.Column('from_name', sa.String(length=255), nullable=True),
        sa.Column('campaign_type', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('opened_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('clicked_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('bounced_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('complained_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('unsubscribed_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('open_rate', sa.Float(), nullable=True),
        sa.Column('click_rate', sa.Float(), nullable=True),
        sa.Column('bounce_rate', sa.Float(), nullable=True),
        sa.Column('complaint_rate', sa.Float(), nullable=True),
        sa.Column('unsubscribe_rate', sa.Float(), nullable=True),
        sa.Column('revenue_cents', sa.BigInteger(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('ad_campaign_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ad_campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'workspace_id', 'provider', 'external_id',
            name='uq_email_campaigns_workspace_provider_external',
        ),
    )
    op.create_index('ix_email_campaigns_workspace_id', 'email_campaigns', ['workspace_id'])
    op.create_index('ix_email_campaigns_provider', 'email_campaigns', ['provider'])
    op.create_index('ix_email_campaigns_sent_at', 'email_campaigns', ['sent_at'])
    op.create_index('ix_email_campaigns_ad_campaign_id', 'email_campaigns', ['ad_campaign_id'])


def downgrade() -> None:
    op.drop_index('ix_email_campaigns_ad_campaign_id', table_name='email_campaigns')
    op.drop_index('ix_email_campaigns_sent_at', table_name='email_campaigns')
    op.drop_index('ix_email_campaigns_provider', table_name='email_campaigns')
    op.drop_index('ix_email_campaigns_workspace_id', table_name='email_campaigns')
    op.drop_table('email_campaigns')
