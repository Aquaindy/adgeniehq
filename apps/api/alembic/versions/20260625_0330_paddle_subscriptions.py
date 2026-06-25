"""Paddle recurring subscriptions + webhook idempotency ledger

Moves recurring plan billing to Paddle (Merchant of Record). Adds:
  * a `PADDLE` label to the `subscription_source` enum (member-name casing,
    matching the existing convention);
  * provider-neutral columns on `billing_subscriptions`
    (`external_subscription_id` unique, `external_price_id`, `management_url`)
    so Paddle rows don't disturb the Stripe/AppSumo `stripe_*` columns;
  * `processed_webhook_events` — an idempotency ledger keyed on
    (provider, event_id) so re-delivered/out-of-order processor webhooks are
    no-ops.

Revision ID: b9f1a3c5d7e2
Revises: a7c9e1b3d5f7
Create Date: 2026-06-25 03:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9f1a3c5d7e2'
down_revision: Union[str, None] = 'a7c9e1b3d5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block; use the
    # Alembic autocommit escape hatch. IF NOT EXISTS keeps it idempotent.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE subscription_source ADD VALUE IF NOT EXISTS 'PADDLE'")

    # --- billing_subscriptions: provider-neutral identifiers --------------
    op.add_column(
        'billing_subscriptions',
        sa.Column('external_subscription_id', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'billing_subscriptions',
        sa.Column('external_price_id', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'billing_subscriptions',
        sa.Column('management_url', sa.String(length=1024), nullable=True),
    )
    op.create_unique_constraint(
        'uq_billing_subscriptions_external_subscription_id',
        'billing_subscriptions',
        ['external_subscription_id'],
    )

    # --- processed_webhook_events -----------------------------------------
    op.create_table(
        'processed_webhook_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('event_id', sa.String(length=128), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'event_id', name='uq_processed_webhook_provider_event'),
    )
    op.create_index(
        op.f('ix_processed_webhook_events_provider'),
        'processed_webhook_events',
        ['provider'],
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_processed_webhook_events_provider'),
        table_name='processed_webhook_events',
    )
    op.drop_table('processed_webhook_events')

    op.drop_constraint(
        'uq_billing_subscriptions_external_subscription_id',
        'billing_subscriptions',
        type_='unique',
    )
    op.drop_column('billing_subscriptions', 'management_url')
    op.drop_column('billing_subscriptions', 'external_price_id')
    op.drop_column('billing_subscriptions', 'external_subscription_id')
    # Note: Postgres can't easily drop a single enum value; 'PADDLE' is left in
    # place on downgrade (harmless — no rows reference it after the column drop).
