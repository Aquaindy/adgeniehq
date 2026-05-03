"""user google_subject column

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-26 15:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('google_subject', sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        op.f('uq_users_google_subject'), 'users', ['google_subject']
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('uq_users_google_subject'), 'users', type_='unique'
    )
    op.drop_column('users', 'google_subject')
