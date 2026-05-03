"""normalize usage_event_type enum to lowercase

The original migration created the `usage_event_type` PG enum with three
UPPERCASE values (`AGENT_RUN`, `LANDING_PAGE_AUDIT`, `REPORT_GENERATED`),
but the Python `StrEnum` exposes them as lowercase (e.g. `agent_run`).
SQLAlchemy historically wrote the *member name* — uppercase — so reads
and writes worked for those three. Subsequent values were added in
lowercase. The mismatch only surfaces when the column is also assigned
`values_callable=lambda enum: [m.value for m in enum]` (so we send
member values rather than names).

This migration adds lowercase variants of the original three and
back-fills existing rows so the Python model can switch to
`values_callable` cleanly. The uppercase variants are left as orphan
labels in the enum (Postgres can't drop enum values without recreating
the type, and they're harmless once unused).

Revision ID: 1c2d3e4f5a6b
Revises: f6a7b8c9d0e1
Create Date: 2026-04-27 00:30:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = '1c2d3e4f5a6b'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_LOWERCASE = (
    ("AGENT_RUN", "agent_run"),
    ("LANDING_PAGE_AUDIT", "landing_page_audit"),
    ("REPORT_GENERATED", "report_generated"),
)


def upgrade() -> None:
    # Step 1 — add the lowercase labels alongside the uppercase ones.
    # PG 12+ allows ADD VALUE within a transaction.
    for _, lower in _NEW_LOWERCASE:
        op.execute(
            f"ALTER TYPE usage_event_type ADD VALUE IF NOT EXISTS '{lower}'"
        )

    # Step 2 — commit the type change so the new label is usable in the
    # backfill below. Postgres 12 buffers new enum values until the
    # surrounding transaction commits, so we issue an explicit commit.
    bind = op.get_bind()
    bind.exec_driver_sql("COMMIT")
    bind.exec_driver_sql("BEGIN")

    # Step 3 — backfill existing rows from uppercase to lowercase.
    for upper, lower in _NEW_LOWERCASE:
        op.execute(
            "UPDATE usage_events "
            f"SET event_type = '{lower}'::usage_event_type "
            f"WHERE event_type::text = '{upper}'"
        )


def downgrade() -> None:
    # Reverse the backfill; leave the lowercase labels in the enum.
    for upper, lower in _NEW_LOWERCASE:
        op.execute(
            "UPDATE usage_events "
            f"SET event_type = '{upper}'::usage_event_type "
            f"WHERE event_type::text = '{lower}'"
        )
