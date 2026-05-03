"""extend usage event types

Revision ID: 9a45468e5465
Revises: aa984f99299f
Create Date: 2026-04-26 03:28:04.388962+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a45468e5465'
down_revision: Union[str, None] = 'aa984f99299f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_VALUES = (
    "outbound_write",
    "content_draft",
    "outreach_email_sent",
    "ab_test_created",
    "llm_call",
)


def upgrade() -> None:
    # Postgres requires a separate ALTER TYPE per ADD VALUE. IF NOT EXISTS
    # makes the migration idempotent in case of a partial run.
    for value in _NEW_VALUES:
        op.execute(
            f"ALTER TYPE usage_event_type ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    # Postgres can't drop ENUM values cleanly without recreating the type.
    # Leave the values in place on rollback — they're harmless if unused.
    pass
