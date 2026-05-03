"""ad hierarchy: ad_groups, ads, creatives

Revision ID: 9b3a4c5d6e7f
Revises: c8e1f4a9b2d3
Create Date: 2026-04-26 13:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9b3a4c5d6e7f'
down_revision: Union[str, None] = 'c2ac56e76c41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # creatives
    op.create_table(
        'creatives',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column(
            'type',
            sa.Enum(
                'search_ad', 'responsive_display', 'single_image', 'video',
                'carousel', 'ugc', 'other',
                name='creative_type',
            ),
            nullable=False,
        ),
        sa.Column(
            'source',
            sa.Enum(
                'platform_synced', 'ai_generated', 'user_uploaded',
                name='creative_source',
            ),
            nullable=False,
        ),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('primary_text', sa.Text(), nullable=True),
        sa.Column('headline', sa.String(length=512), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('cta', sa.String(length=120), nullable=True),
        sa.Column('image_url', sa.String(length=2048), nullable=True),
        sa.Column('video_url', sa.String(length=2048), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_creatives_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_creatives')),
    )
    op.create_index(
        op.f('ix_creatives_workspace_id'),
        'creatives', ['workspace_id'], unique=False,
    )

    # ad_groups
    op.create_table(
        'ad_groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('external_id', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=512), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'active', 'paused', 'ended', 'archived',
                name='ad_group_status',
            ),
            nullable=False,
        ),
        sa.Column('daily_budget_cents', sa.BigInteger(), nullable=True),
        sa.Column('targeting', sa.JSON(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_payload', sa.JSON(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_ad_groups_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['campaign_id'], ['campaigns.id'],
            name=op.f('fk_ad_groups_campaign_id_campaigns'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ad_groups')),
        sa.UniqueConstraint(
            'campaign_id', 'external_id',
            name='uq_ad_groups_campaign_external',
        ),
    )
    op.create_index(
        op.f('ix_ad_groups_workspace_id'),
        'ad_groups', ['workspace_id'], unique=False,
    )
    op.create_index(
        op.f('ix_ad_groups_campaign_id'),
        'ad_groups', ['campaign_id'], unique=False,
    )

    # ads
    op.create_table(
        'ads',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('ad_group_id', sa.UUID(), nullable=False),
        sa.Column('creative_id', sa.UUID(), nullable=True),
        sa.Column('external_id', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=512), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'active', 'paused', 'ended', 'rejected', 'archived',
                name='ad_status',
            ),
            nullable=False,
        ),
        sa.Column('landing_page_url', sa.String(length=2048), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_payload', sa.JSON(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_ads_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['campaign_id'], ['campaigns.id'],
            name=op.f('fk_ads_campaign_id_campaigns'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['ad_group_id'], ['ad_groups.id'],
            name=op.f('fk_ads_ad_group_id_ad_groups'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['creative_id'], ['creatives.id'],
            name=op.f('fk_ads_creative_id_creatives'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ads')),
        sa.UniqueConstraint(
            'ad_group_id', 'external_id',
            name='uq_ads_group_external',
        ),
    )
    op.create_index(
        op.f('ix_ads_workspace_id'),
        'ads', ['workspace_id'], unique=False,
    )
    op.create_index(
        op.f('ix_ads_campaign_id'),
        'ads', ['campaign_id'], unique=False,
    )
    op.create_index(
        op.f('ix_ads_ad_group_id'),
        'ads', ['ad_group_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_ads_ad_group_id'), table_name='ads')
    op.drop_index(op.f('ix_ads_campaign_id'), table_name='ads')
    op.drop_index(op.f('ix_ads_workspace_id'), table_name='ads')
    op.drop_table('ads')
    op.execute('DROP TYPE IF EXISTS ad_status')

    op.drop_index(op.f('ix_ad_groups_campaign_id'), table_name='ad_groups')
    op.drop_index(op.f('ix_ad_groups_workspace_id'), table_name='ad_groups')
    op.drop_table('ad_groups')
    op.execute('DROP TYPE IF EXISTS ad_group_status')

    op.drop_index(op.f('ix_creatives_workspace_id'), table_name='creatives')
    op.drop_table('creatives')
    op.execute('DROP TYPE IF EXISTS creative_source')
    op.execute('DROP TYPE IF EXISTS creative_type')
