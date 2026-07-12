"""growth dna profile label

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5b7d9f2
Create Date: 2026-07-12 01:00:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, None] = 'a1c3e5b7d9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "growth_dna_profiles",
        sa.Column("label", sa.String(length=160), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("growth_dna_profiles", "label")
