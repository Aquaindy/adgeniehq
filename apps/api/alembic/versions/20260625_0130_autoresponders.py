"""Autoresponder connections + contact-sync ledger

Pluggable autoresponder integrations (Omnisend, GetResponse, generic webhook).
`autoresponder_connections` holds one API-key-based connection per
(workspace, provider) with the key encrypted at rest; `autoresponder_contact_syncs`
is the push/pull ledger.

Revision ID: f6b8d0c2e4a7
Revises: e5a7c9b1d3f6
Create Date: 2026-06-25 01:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f6b8d0c2e4a7'
down_revision: Union[str, None] = 'e5a7c9b1d3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'autoresponder_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('provider_account_id', sa.String(length=255), nullable=True),
        sa.Column(
            'status',
            sa.Enum('DISCONNECTED', 'CONNECTED', 'ERROR', name='autoresponder_status'),
            nullable=False,
        ),
        sa.Column('encrypted_api_key', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('connected_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connected_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'workspace_id', 'provider', name='uq_autoresponder_connections_workspace_provider'
        ),
    )
    op.create_index(
        'ix_autoresponder_connections_workspace_id',
        'autoresponder_connections',
        ['workspace_id'],
    )
    op.create_index(
        'ix_autoresponder_connections_provider',
        'autoresponder_connections',
        ['provider'],
    )

    op.create_table(
        'autoresponder_contact_syncs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'direction',
            sa.Enum('PUSH', 'PULL', name='autoresponder_sync_direction'),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED',
                name='autoresponder_sync_status',
            ),
            nullable=False,
        ),
        sa.Column('audience_external_id', sa.String(length=255), nullable=True),
        sa.Column('audience_name', sa.String(length=255), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=True),
        sa.Column('requested_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('succeeded_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['connection_id'], ['autoresponder_connections.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_autoresponder_contact_syncs_connection_id',
        'autoresponder_contact_syncs',
        ['connection_id'],
    )
    op.create_index(
        'ix_autoresponder_contact_syncs_workspace_id',
        'autoresponder_contact_syncs',
        ['workspace_id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_autoresponder_contact_syncs_workspace_id',
        table_name='autoresponder_contact_syncs',
    )
    op.drop_index(
        'ix_autoresponder_contact_syncs_connection_id',
        table_name='autoresponder_contact_syncs',
    )
    op.drop_table('autoresponder_contact_syncs')
    op.drop_index(
        'ix_autoresponder_connections_provider',
        table_name='autoresponder_connections',
    )
    op.drop_index(
        'ix_autoresponder_connections_workspace_id',
        table_name='autoresponder_connections',
    )
    op.drop_table('autoresponder_connections')
    sa.Enum(name='autoresponder_sync_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='autoresponder_sync_direction').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='autoresponder_status').drop(op.get_bind(), checkfirst=True)
