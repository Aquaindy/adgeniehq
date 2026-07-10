"""image_generation usage event type

Revision ID: a1c3e5b7d9f2
Revises: f6a4d2b8c1e3
Create Date: 2026-07-10 02:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c3e5b7d9f2'
down_revision: Union[str, None] = 'f6a4d2b8c1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `usage_event_type` was created WITH `values_callable`, so it stores the
    # lowercase enum *values* — add the value form, not the member name.
    op.execute(
        "ALTER TYPE usage_event_type ADD VALUE IF NOT EXISTS 'image_generation'"
    )


def downgrade() -> None:
    # Postgres can't drop an ENUM value without recreating the type. Harmless
    # once no rows reference it.
    pass
