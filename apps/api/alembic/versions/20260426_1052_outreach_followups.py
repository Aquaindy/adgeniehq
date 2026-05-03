"""outreach followups

Revision ID: 8ca81bce88da
Revises: 7e3a02aaf89b
Create Date: 2026-04-26 10:52:44.309395+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ca81bce88da'
down_revision: Union[str, None] = '7e3a02aaf89b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('outreach_emails', sa.Column('parent_email_id', sa.UUID(), nullable=True))
    op.add_column(
        'outreach_emails',
        sa.Column('step_index', sa.Integer(), nullable=False, server_default='1'),
    )
    op.alter_column('outreach_emails', 'step_index', server_default=None)
    op.alter_column(
        'outreach_emails', 'reply_token',
        existing_type=sa.VARCHAR(length=32),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.create_index(
        op.f('ix_outreach_emails_parent_email_id'),
        'outreach_emails', ['parent_email_id'], unique=False,
    )
    op.create_foreign_key(
        op.f('fk_outreach_emails_parent_email_id_outreach_emails'),
        'outreach_emails', 'outreach_emails',
        ['parent_email_id'], ['id'], ondelete='SET NULL',
    )
    # NOTE: idempotency_key partial index is left alone (alembic doesn't see
    # the WHERE clause).


def downgrade() -> None:
    op.drop_constraint(
        op.f('fk_outreach_emails_parent_email_id_outreach_emails'),
        'outreach_emails', type_='foreignkey',
    )
    op.drop_index(
        op.f('ix_outreach_emails_parent_email_id'), table_name='outreach_emails'
    )
    op.alter_column(
        'outreach_emails', 'reply_token',
        existing_type=sa.String(length=64),
        type_=sa.VARCHAR(length=32),
        existing_nullable=True,
    )
    op.drop_column('outreach_emails', 'step_index')
    op.drop_column('outreach_emails', 'parent_email_id')
