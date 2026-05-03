"""user 2FA columns

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-04-26 13:40:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'two_factor_enabled', sa.Boolean(),
            nullable=False, server_default=sa.text('false'),
        ),
    )
    op.alter_column('users', 'two_factor_enabled', server_default=None)
    op.add_column(
        'users',
        sa.Column('two_factor_secret_encrypted', sa.String(length=512), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('two_factor_recovery_hashes', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'two_factor_recovery_hashes')
    op.drop_column('users', 'two_factor_secret_encrypted')
    op.drop_column('users', 'two_factor_enabled')
