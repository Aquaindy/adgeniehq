"""Growth DNA: comprehensive marketing_strategy bundle

Adds a single JSONB column `marketing_strategy` to `growth_dna_profiles`. It holds
the full cross-channel marketing playbook (paid, organic social, email/lifecycle,
SEO, GEO, content, CRO, automation, referral, measurement) plus content pillars,
platform plan, and an optional LLM-generated content calendar.

Stored as one JSONB blob (rather than many columns) so the structure can evolve
without further migrations. Existing rows backfill to an empty object via the
server default; the app always writes a populated value on generate.

Revision ID: b2d4f6a8c1e3
Revises: a1c2e3f40516
Create Date: 2026-06-24 22:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b2d4f6a8c1e3'
down_revision: Union[str, None] = 'a1c2e3f40516'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'growth_dna_profiles',
        sa.Column(
            'marketing_strategy',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # The app always supplies a populated value going forward; drop the DB-side
    # default so it doesn't mask a missing write.
    op.alter_column('growth_dna_profiles', 'marketing_strategy', server_default=None)


def downgrade() -> None:
    op.drop_column('growth_dna_profiles', 'marketing_strategy')
