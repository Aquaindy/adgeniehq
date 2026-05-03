"""outreach reply token

Revision ID: aa984f99299f
Revises: 1f7b282221e6
Create Date: 2026-04-26 03:15:58.022702+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa984f99299f'
down_revision: Union[str, None] = '1f7b282221e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'outreach_emails',
        sa.Column('reply_token', sa.String(length=32), nullable=True),
    )
    op.create_unique_constraint(
        op.f('uq_outreach_emails_reply_token'), 'outreach_emails', ['reply_token']
    )
    # NOTE: alembic autogenerate doesn't see the partial-index WHERE clause on
    # `uq_rec_executions_workspace_idempotency_key`, so it tries to drop and
    # recreate it here. Leave the partial index alone.


def downgrade() -> None:
    op.drop_constraint(
        op.f('uq_outreach_emails_reply_token'), 'outreach_emails', type_='unique'
    )
    op.drop_column('outreach_emails', 'reply_token')
