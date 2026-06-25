"""Ad hierarchy: user-built drafts (source + nullable external_id)

Lets users build ad groups + ads inside AdVanta before they exist on a platform:
  * adds `source` (platform_synced | advanta_draft) to ad_groups and ads,
  * makes `external_id` nullable (drafts have no platform id yet).

Existing synced rows backfill to platform_synced via the server default.

Revision ID: d4f6a8c0e2b5
Revises: c3e5f7a9b1d4
Create Date: 2026-06-25 00:10:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd4f6a8c0e2b5'
down_revision: Union[str, None] = 'c3e5f7a9b1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ag_source = postgresql.ENUM('platform_synced', 'advanta_draft', name='ad_group_source')
    ag_source.create(op.get_bind(), checkfirst=True)
    ad_source = postgresql.ENUM('platform_synced', 'advanta_draft', name='ad_source')
    ad_source.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'ad_groups',
        sa.Column(
            'source',
            postgresql.ENUM('platform_synced', 'advanta_draft', name='ad_group_source', create_type=False),
            nullable=False,
            server_default='platform_synced',
        ),
    )
    op.add_column(
        'ads',
        sa.Column(
            'source',
            postgresql.ENUM('platform_synced', 'advanta_draft', name='ad_source', create_type=False),
            nullable=False,
            server_default='platform_synced',
        ),
    )
    op.alter_column('ad_groups', 'external_id', existing_type=sa.String(length=128), nullable=True)
    op.alter_column('ads', 'external_id', existing_type=sa.String(length=128), nullable=True)


def downgrade() -> None:
    op.alter_column('ads', 'external_id', existing_type=sa.String(length=128), nullable=False)
    op.alter_column('ad_groups', 'external_id', existing_type=sa.String(length=128), nullable=False)
    op.drop_column('ads', 'source')
    op.drop_column('ad_groups', 'source')
    postgresql.ENUM(name='ad_source').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='ad_group_source').drop(op.get_bind(), checkfirst=True)
