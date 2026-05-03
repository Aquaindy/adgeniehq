"""provider credentials (BYOK)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-26 17:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    provider_enum = sa.Enum(
        'openai',
        'anthropic',
        'google_ai',
        name='provider_credential_provider',
    )
    test_status_enum = sa.Enum(
        'ok',
        'failed',
        name='provider_credential_test_status',
    )

    op.create_table(
        'provider_credentials',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'workspace_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('workspaces.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'created_by',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('provider', provider_enum, nullable=False),
        sa.Column('label', sa.String(length=120), nullable=True),
        sa.Column('encrypted_secret', sa.Text(), nullable=False),
        sa.Column('last_four', sa.String(length=8), nullable=False),
        sa.Column('last_tested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_test_status', test_status_enum, nullable=True),
        sa.Column('last_test_error', sa.Text(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'revoked_by',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_provider_credentials_workspace_id',
        'provider_credentials',
        ['workspace_id'],
    )
    # One active credential per (workspace, provider). Re-adding for the same
    # provider revokes the prior row first.
    op.create_index(
        'uq_provider_credentials_workspace_provider_active',
        'provider_credentials',
        ['workspace_id', 'provider'],
        unique=True,
        postgresql_where=sa.text('revoked_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_provider_credentials_workspace_provider_active',
        table_name='provider_credentials',
    )
    op.drop_index(
        'ix_provider_credentials_workspace_id',
        table_name='provider_credentials',
    )
    op.drop_table('provider_credentials')
    sa.Enum(name='provider_credential_test_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='provider_credential_provider').drop(op.get_bind(), checkfirst=True)
