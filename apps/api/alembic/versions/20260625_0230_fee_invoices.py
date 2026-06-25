"""Fee collection layer: fee_invoices + accrual link

Adds the `fee_invoices` table (a bill issued through a pluggable payment
provider) and an `invoice_id` link on `fee_accruals` so accruals know which
invoice billed them.

Revision ID: a7c9e1b3d5f7
Revises: f6b8d0c2e4a7
Create Date: 2026-06-25 02:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a7c9e1b3d5f7'
down_revision: Union[str, None] = 'f6b8d0c2e4a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fee_invoices',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column(
            'status',
            sa.Enum('draft', 'open', 'paid', 'void', 'failed', name='fee_invoice_status'),
            nullable=False,
        ),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('period', sa.String(length=7), nullable=True),
        sa.Column('accrual_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('external_id', sa.String(length=255), nullable=True),
        sa.Column('hosted_url', sa.String(length=1024), nullable=True),
        sa.Column('line_items', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fee_invoices_workspace_id', 'fee_invoices', ['workspace_id'])
    op.create_index('ix_fee_invoices_status', 'fee_invoices', ['status'])

    op.add_column(
        'fee_accruals',
        sa.Column('invoice_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index('ix_fee_accruals_invoice_id', 'fee_accruals', ['invoice_id'])
    op.create_foreign_key(
        'fk_fee_accruals_invoice_id_fee_invoices',
        'fee_accruals',
        'fee_invoices',
        ['invoice_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_fee_accruals_invoice_id_fee_invoices', 'fee_accruals', type_='foreignkey'
    )
    op.drop_index('ix_fee_accruals_invoice_id', table_name='fee_accruals')
    op.drop_column('fee_accruals', 'invoice_id')
    op.drop_index('ix_fee_invoices_status', table_name='fee_invoices')
    op.drop_index('ix_fee_invoices_workspace_id', table_name='fee_invoices')
    op.drop_table('fee_invoices')
    sa.Enum(name='fee_invoice_status').drop(op.get_bind(), checkfirst=True)
