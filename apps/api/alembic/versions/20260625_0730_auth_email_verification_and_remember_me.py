"""auth: email-verification cols + refresh_tokens.persistent (remember-me)

Adds:
  * users.email_verification_hash (unique) + users.email_verification_expires_at
    — single-use email-verification token, same storage pattern as password
    reset (only the SHA-256 hash is stored).
  * refresh_tokens.persistent (bool, default true) — carries the "remember me"
    choice across token rotation so a non-remembered session never silently
    becomes a persistent one.

Revision ID: f4d6b8a0c2e5
Revises: e3c5a7b9d1f4
Create Date: 2026-06-25 07:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4d6b8a0c2e5'
down_revision: Union[str, None] = 'e3c5a7b9d1f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('email_verification_hash', sa.String(length=128), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column(
            'email_verification_expires_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        op.f('uq_users_email_verification_hash'),
        'users',
        ['email_verification_hash'],
    )
    op.add_column(
        'refresh_tokens',
        sa.Column(
            'persistent',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true'),
        ),
    )


def downgrade() -> None:
    op.drop_column('refresh_tokens', 'persistent')
    op.drop_constraint(
        op.f('uq_users_email_verification_hash'), 'users', type_='unique'
    )
    op.drop_column('users', 'email_verification_expires_at')
    op.drop_column('users', 'email_verification_hash')
