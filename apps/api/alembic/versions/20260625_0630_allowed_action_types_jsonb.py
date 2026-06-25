"""autopilot_configs.allowed_action_types: json -> jsonb (match the model)

The model declares JSONB but the original migration created it as sa.JSON()
(Postgres `json`). Convert to `jsonb` for index/operator support and to stop
autogenerate from flagging a perpetual diff. Functionally interchangeable for
read/write, so this is a clean in-place cast.

Revision ID: e3c5a7b9d1f4
Revises: d2b4f6a8c0e1
Create Date: 2026-06-25 06:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e3c5a7b9d1f4'
down_revision: Union[str, None] = 'd2b4f6a8c0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'autopilot_configs',
        'allowed_action_types',
        type_=postgresql.JSONB(),
        postgresql_using='allowed_action_types::jsonb',
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'autopilot_configs',
        'allowed_action_types',
        type_=sa.JSON(),
        postgresql_using='allowed_action_types::json',
        existing_nullable=True,
    )
