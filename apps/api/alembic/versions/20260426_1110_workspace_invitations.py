"""workspace invitations

Revision ID: 35eef47a1408
Revises: 4d9c2b1e0a7f
Create Date: 2026-04-26 11:10:31.701850+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '35eef47a1408'
down_revision: Union[str, None] = '4d9c2b1e0a7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workspace_invitations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column(
            'role',
            postgresql.ENUM(
                'OWNER', 'ADMIN', 'MARKETER', 'ANALYST', 'VIEWER',
                name='workspace_member_role',
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'PENDING', 'ACCEPTED', 'REVOKED', 'EXPIRED',
                name='workspace_invitation_status',
            ),
            nullable=False,
        ),
        sa.Column('token_hash', sa.String(length=128), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('invited_by', sa.UUID(), nullable=True),
        sa.Column('accepted_by', sa.UUID(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['accepted_by'], ['users.id'],
            name=op.f('fk_workspace_invitations_accepted_by_users'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['invited_by'], ['users.id'],
            name=op.f('fk_workspace_invitations_invited_by_users'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_workspace_invitations_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_workspace_invitations')),
        sa.UniqueConstraint(
            'token_hash', name=op.f('uq_workspace_invitations_token_hash')
        ),
    )
    op.create_index(
        op.f('ix_workspace_invitations_email'),
        'workspace_invitations', ['email'], unique=False,
    )
    op.create_index(
        op.f('ix_workspace_invitations_workspace_id'),
        'workspace_invitations', ['workspace_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_workspace_invitations_workspace_id'),
        table_name='workspace_invitations',
    )
    op.drop_index(
        op.f('ix_workspace_invitations_email'),
        table_name='workspace_invitations',
    )
    op.drop_table('workspace_invitations')
    op.execute('DROP TYPE IF EXISTS workspace_invitation_status')
