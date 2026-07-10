"""social content types: short-form video scripts + platform/hashtags columns

Also extends `suggested_copy_type` so the Growth Content Studio can emit
organic short-form video scripts alongside its posts.

Revision ID: f6a4d2b8c1e3
Revises: e5c3f9a2b7d1
Create Date: 2026-07-10 01:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f6a4d2b8c1e3'
down_revision: Union[str, None] = 'e5c3f9a2b7d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `content_draft_type` was created from a SQLAlchemy Enum without
    # `values_callable`, so Postgres stores the *member names* (BLOG_POST),
    # not the lowercase values (blog_post). New members must be added in that
    # same uppercase form or SQLAlchemy can't round-trip the column.
    #
    # ADD VALUE runs inside the migration's transaction (Postgres 12+); we do
    # not reference the new value in this migration, which is the one thing
    # that would require it to be committed first.
    op.execute(
        "ALTER TYPE content_draft_type ADD VALUE IF NOT EXISTS 'SHORT_VIDEO_SCRIPT'"
    )
    # `suggested_copy_type`, unlike `content_draft_type`, was created WITH
    # `values_callable`, so it stores the lowercase enum *values*. Match that.
    op.execute(
        "ALTER TYPE suggested_copy_type ADD VALUE IF NOT EXISTS 'short_video_script'"
    )

    op.add_column(
        'content_drafts',
        sa.Column('platform', sa.String(length=32), nullable=True),
    )
    op.create_index(
        op.f('ix_content_drafts_platform'),
        'content_drafts',
        ['platform'],
        unique=False,
    )
    op.add_column(
        'content_drafts',
        sa.Column(
            'hashtags',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('content_drafts', 'hashtags')
    op.drop_index(op.f('ix_content_drafts_platform'), table_name='content_drafts')
    op.drop_column('content_drafts', 'platform')
    # Postgres can't drop an ENUM value without recreating the type. Leaving
    # SHORT_VIDEO_SCRIPT in place is harmless once no rows reference it.
