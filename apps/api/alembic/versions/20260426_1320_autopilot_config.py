"""autopilot config

Revision ID: a1b2c3d4e5f6
Revises: 9b3a4c5d6e7f
Create Date: 2026-04-26 13:20:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9b3a4c5d6e7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'autopilot_configs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column(
            'mode',
            sa.Enum(
                'off', 'advisor', 'approval', 'autopilot',
                name='autopilot_mode',
            ),
            nullable=False,
        ),
        sa.Column('max_daily_spend_increase_cents', sa.BigInteger(), nullable=True),
        sa.Column('max_daily_spend_total_cents', sa.BigInteger(), nullable=True),
        sa.Column('max_pct_increase_per_change', sa.Integer(), nullable=True),
        sa.Column('min_conversion_threshold', sa.Integer(), nullable=True),
        sa.Column('allowed_action_types', sa.JSON(), nullable=True),
        sa.Column(
            'risk_ceiling',
            postgresql.ENUM(
                'LOW', 'MEDIUM', 'HIGH',
                name='recommendation_risk_level',
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column('stop_loss_active', sa.Boolean(), nullable=False),
        sa.Column('stop_loss_reason', sa.Text(), nullable=True),
        sa.Column('last_disabled_reason', sa.String(length=512), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_autopilot_configs_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_autopilot_configs')),
        sa.UniqueConstraint(
            'workspace_id', name='uq_autopilot_configs_workspace'
        ),
    )
    op.create_index(
        op.f('ix_autopilot_configs_workspace_id'),
        'autopilot_configs', ['workspace_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_autopilot_configs_workspace_id'),
        table_name='autopilot_configs',
    )
    op.drop_table('autopilot_configs')
    op.execute('DROP TYPE IF EXISTS autopilot_mode')
