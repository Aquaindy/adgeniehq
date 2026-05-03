"""execution idempotency keys

Revision ID: 4cadbe751543
Revises: ac766d21a2f2
Create Date: 2026-04-26 02:58:01.257463+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4cadbe751543'
down_revision: Union[str, None] = 'ac766d21a2f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'recommendation_executions',
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
    )
    # Partial unique index — only enforced when a key is provided. NULL keys
    # are allowed to repeat (retries that don't pass a key fall back to the
    # service-layer "no in-flight execution" guard).
    op.create_index(
        'uq_rec_executions_workspace_idempotency_key',
        'recommendation_executions',
        ['workspace_id', 'idempotency_key'],
        unique=True,
        postgresql_where=sa.text('idempotency_key IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_rec_executions_workspace_idempotency_key',
        table_name='recommendation_executions',
    )
    op.drop_column('recommendation_executions', 'idempotency_key')
