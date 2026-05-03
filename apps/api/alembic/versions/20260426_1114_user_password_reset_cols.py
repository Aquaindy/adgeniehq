"""user password reset cols

Revision ID: c2ac56e76c41
Revises: 35eef47a1408
Create Date: 2026-04-26 11:14:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2ac56e76c41'
down_revision: Union[str, None] = '35eef47a1408'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('password_reset_hash', sa.String(length=128), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column(
            'password_reset_expires_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        op.f('uq_users_password_reset_hash'),
        'users',
        ['password_reset_hash'],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('uq_users_password_reset_hash'), 'users', type_='unique'
    )
    op.drop_column('users', 'password_reset_expires_at')
    op.drop_column('users', 'password_reset_hash')
