"""ab test bandit strategy

Revision ID: fc6e8fdf174d
Revises: 8ca81bce88da
Create Date: 2026-04-26 10:57:24.759268+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc6e8fdf174d'
down_revision: Union[str, None] = '8ca81bce88da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bandit_enum = sa.Enum(
        'STATIC', 'THOMPSON_SAMPLING',
        name='ab_test_bandit_strategy',
        create_type=False,
    )
    op.execute("CREATE TYPE ab_test_bandit_strategy AS ENUM ('STATIC', 'THOMPSON_SAMPLING')")
    op.add_column(
        'ab_tests',
        sa.Column(
            'bandit_strategy',
            bandit_enum,
            nullable=False,
            server_default='STATIC',
        ),
    )
    op.alter_column('ab_tests', 'bandit_strategy', server_default=None)


def downgrade() -> None:
    op.drop_column('ab_tests', 'bandit_strategy')
    op.execute('DROP TYPE IF EXISTS ab_test_bandit_strategy')
