"""content_draft slug + excerpt

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-26 16:20:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'content_drafts',
        sa.Column('slug', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'content_drafts',
        sa.Column('excerpt', sa.Text(), nullable=True),
    )
    # Slug must be unique per workspace — same slug across workspaces is fine
    # (each customer's blog lives under their own scope). Partial-unique
    # index because most drafts (non-blog types) won't have a slug.
    op.create_index(
        'uq_content_drafts_workspace_slug',
        'content_drafts',
        ['workspace_id', 'slug'],
        unique=True,
        postgresql_where=sa.text('slug IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_content_drafts_workspace_slug',
        table_name='content_drafts',
    )
    op.drop_column('content_drafts', 'excerpt')
    op.drop_column('content_drafts', 'slug')
