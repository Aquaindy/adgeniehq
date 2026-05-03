"""content draft image url

Revision ID: 4d9c2b1e0a7f
Revises: fc6e8fdf174d
Create Date: 2026-04-26 11:04:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4d9c2b1e0a7f'
down_revision: Union[str, None] = 'fc6e8fdf174d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'content_drafts',
        sa.Column('image_url', sa.String(length=2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('content_drafts', 'image_url')
