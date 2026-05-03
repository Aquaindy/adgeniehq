"""widen onboarding_profiles.primary_conversion_goal to 500

The column was sized at 120 chars but real customers paste multi-clause
goals or AI-suggested goal-bullets that frequently exceed that. Bump to
500 — still bounded, no longer punishing.

Revision ID: 2d3e4f5a6b7c
Revises: 1c2d3e4f5a6b
Create Date: 2026-04-27 02:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2d3e4f5a6b7c'
down_revision: Union[str, None] = '1c2d3e4f5a6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'onboarding_profiles',
        'primary_conversion_goal',
        existing_type=sa.String(length=120),
        type_=sa.String(length=500),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Truncate any rows that exceed 120 chars before shrinking the column.
    op.execute(
        "UPDATE onboarding_profiles "
        "SET primary_conversion_goal = LEFT(primary_conversion_goal, 120) "
        "WHERE primary_conversion_goal IS NOT NULL "
        "AND CHAR_LENGTH(primary_conversion_goal) > 120"
    )
    op.alter_column(
        'onboarding_profiles',
        'primary_conversion_goal',
        existing_type=sa.String(length=500),
        type_=sa.String(length=120),
        existing_nullable=True,
    )
