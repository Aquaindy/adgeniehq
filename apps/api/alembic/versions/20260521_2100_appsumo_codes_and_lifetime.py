"""AppSumo codes + lifetime subscription source

Adds the `appsumo_codes` table (redeemable lifetime-deal codes) and extends
`billing_subscriptions` with a `source` discriminator (stripe | appsumo) plus a
nullable `billing_customer_id` — AppSumo lifetime grants have no Stripe customer.

Enum labels follow the existing convention (SQLAlchemy stores enum *member
names*, uppercase).

Revision ID: a1c2e3f40516
Revises: 3e4f5a6b7c8d
Create Date: 2026-05-21 21:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1c2e3f40516'
down_revision: Union[str, None] = '3e4f5a6b7c8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- billing_subscriptions.source -------------------------------------
    source_enum = postgresql.ENUM('STRIPE', 'APPSUMO', name='subscription_source')
    source_enum.create(bind, checkfirst=True)
    op.add_column(
        'billing_subscriptions',
        sa.Column(
            'source',
            sa.Enum('STRIPE', 'APPSUMO', name='subscription_source', create_type=False),
            nullable=False,
            server_default='STRIPE',
        ),
    )

    # AppSumo lifetime rows have no Stripe customer.
    op.alter_column(
        'billing_subscriptions',
        'billing_customer_id',
        existing_type=sa.UUID(),
        nullable=True,
    )

    # --- appsumo_codes -----------------------------------------------------
    op.create_table(
        'appsumo_codes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column(
            'status',
            sa.Enum('UNREDEEMED', 'REDEEMED', 'REFUNDED', name='appsumo_code_status'),
            nullable=False,
        ),
        sa.Column('batch', sa.String(length=64), nullable=True),
        sa.Column('workspace_id', sa.UUID(), nullable=True),
        sa.Column('redeemed_by_user_id', sa.UUID(), nullable=True),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_appsumo_codes_workspace_id_workspaces'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['redeemed_by_user_id'], ['users.id'],
            name=op.f('fk_appsumo_codes_redeemed_by_user_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_appsumo_codes')),
        sa.UniqueConstraint('code', name=op.f('uq_appsumo_codes_code')),
    )
    op.create_index(op.f('ix_appsumo_codes_code'), 'appsumo_codes', ['code'], unique=True)
    op.create_index(op.f('ix_appsumo_codes_status'), 'appsumo_codes', ['status'], unique=False)
    op.create_index(op.f('ix_appsumo_codes_batch'), 'appsumo_codes', ['batch'], unique=False)
    op.create_index(op.f('ix_appsumo_codes_workspace_id'), 'appsumo_codes', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_appsumo_codes_workspace_id'), table_name='appsumo_codes')
    op.drop_index(op.f('ix_appsumo_codes_batch'), table_name='appsumo_codes')
    op.drop_index(op.f('ix_appsumo_codes_status'), table_name='appsumo_codes')
    op.drop_index(op.f('ix_appsumo_codes_code'), table_name='appsumo_codes')
    op.drop_table('appsumo_codes')
    sa.Enum(name='appsumo_code_status').drop(op.get_bind(), checkfirst=True)

    op.alter_column(
        'billing_subscriptions',
        'billing_customer_id',
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.drop_column('billing_subscriptions', 'source')
    sa.Enum(name='subscription_source').drop(op.get_bind(), checkfirst=True)
