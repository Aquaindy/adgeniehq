"""workspace publish webhook

Revision ID: 7e3a02aaf89b
Revises: 9a45468e5465
Create Date: 2026-04-26 09:20:56.790240+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e3a02aaf89b'
down_revision: Union[str, None] = '9a45468e5465'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'workspaces',
        sa.Column('publish_webhook_url', sa.String(length=1024), nullable=True),
    )
    op.add_column(
        'workspaces',
        sa.Column('encrypted_publish_webhook_secret', sa.Text(), nullable=True),
    )
    # NOTE: alembic doesn't see the partial WHERE clause on the
    # idempotency-key index; leave it alone.


def downgrade() -> None:
    op.drop_column('workspaces', 'encrypted_publish_webhook_secret')
    op.drop_column('workspaces', 'publish_webhook_url')
