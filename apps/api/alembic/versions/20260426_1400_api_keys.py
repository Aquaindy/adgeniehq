"""api keys table

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-04-26 14:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_keys',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('prefix', sa.String(length=16), nullable=False),
        sa.Column('secret_hash', sa.String(length=128), nullable=False),
        sa.Column(
            'role',
            postgresql.ENUM(
                'OWNER', 'ADMIN', 'MARKETER', 'ANALYST', 'VIEWER',
                name='workspace_member_role',
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_api_keys_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name=op.f('fk_api_keys_created_by_users'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_api_keys')),
        sa.UniqueConstraint('prefix', name='uq_api_keys_prefix'),
        sa.UniqueConstraint('secret_hash', name='uq_api_keys_secret_hash'),
    )
    op.create_index(
        op.f('ix_api_keys_workspace_id'),
        'api_keys', ['workspace_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_api_keys_workspace_id'), table_name='api_keys')
    op.drop_table('api_keys')
