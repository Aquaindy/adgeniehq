"""onboarding_profiles: replace single monthly_ad_budget_usd with min/max range

Customers consistently asked for a budget *range* rather than a single
number — e.g. "we plan to spend somewhere between $5k and $8k per month
depending on Q-end pacing." The Growth DNA agent and Campaign Builder
take both bounds into account: min for readiness scoring, max for plan
ceilings.

Existing rows are backfilled with min = max = old value so historical
profiles keep working. The old column is dropped at the end.

Revision ID: 3e4f5a6b7c8d
Revises: 2d3e4f5a6b7c
Create Date: 2026-04-27 02:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3e4f5a6b7c8d'
down_revision: Union[str, None] = '2d3e4f5a6b7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'onboarding_profiles',
        sa.Column('monthly_ad_budget_min_usd', sa.Integer(), nullable=True),
    )
    op.add_column(
        'onboarding_profiles',
        sa.Column('monthly_ad_budget_max_usd', sa.Integer(), nullable=True),
    )

    # Backfill: existing single value becomes both bounds. Rows without a
    # value stay null on both sides.
    op.execute(
        "UPDATE onboarding_profiles "
        "SET monthly_ad_budget_min_usd = monthly_ad_budget_usd, "
        "    monthly_ad_budget_max_usd = monthly_ad_budget_usd "
        "WHERE monthly_ad_budget_usd IS NOT NULL"
    )

    op.drop_column('onboarding_profiles', 'monthly_ad_budget_usd')


def downgrade() -> None:
    op.add_column(
        'onboarding_profiles',
        sa.Column('monthly_ad_budget_usd', sa.Integer(), nullable=True),
    )
    # Reverse backfill: take the max as the single value (most permissive).
    op.execute(
        "UPDATE onboarding_profiles "
        "SET monthly_ad_budget_usd = COALESCE("
        "  monthly_ad_budget_max_usd, monthly_ad_budget_min_usd"
        ") "
        "WHERE monthly_ad_budget_max_usd IS NOT NULL "
        "OR monthly_ad_budget_min_usd IS NOT NULL"
    )
    op.drop_column('onboarding_profiles', 'monthly_ad_budget_max_usd')
    op.drop_column('onboarding_profiles', 'monthly_ad_budget_min_usd')
