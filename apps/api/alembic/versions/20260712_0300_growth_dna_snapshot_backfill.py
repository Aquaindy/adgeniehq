"""backfill snapshot + label onto each workspace's newest growth dna

Profiles generated before onboarding snapshots existed can't offer
"Reuse answers". For the NEWEST profile per workspace this is safely
recoverable: the workspace's single onboarding profile still holds the
answers that produced it (or a strictly newer edit of them, which is
what a restore would surface anyway). Older siblings stay snapshot-less
— their generating answers are genuinely gone.

Revision ID: d4f6b8c0a2e3
Revises: c3e5a7b9d1f4
Create Date: 2026-07-12 03:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4f6b8c0a2e3'
down_revision: Union[str, None] = 'c3e5a7b9d1f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE growth_dna_profiles g
        SET onboarding_snapshot = jsonb_build_object(
                'business_name', o.business_name,
                'website_url', o.website_url,
                'industry', o.industry,
                'target_audience', o.target_audience,
                'offer_description', o.offer_description,
                'pain_points', o.pain_points,
                'primary_conversion_goal', o.primary_conversion_goal,
                'monthly_ad_budget_min_usd', o.monthly_ad_budget_min_usd,
                'monthly_ad_budget_max_usd', o.monthly_ad_budget_max_usd,
                'geographic_target', o.geographic_target,
                'current_ad_platforms', o.current_ad_platforms,
                'landing_page_urls', o.landing_page_urls,
                'analytics_status', o.analytics_status,
                'competitors', o.competitors,
                'brand_voice', o.brand_voice
            ),
            label = COALESCE(g.label, NULLIF(LEFT(o.business_name, 160), ''))
        FROM onboarding_profiles o
        WHERE o.id = g.onboarding_profile_id
          AND g.onboarding_snapshot IS NULL
          AND g.id = (
              SELECT g2.id
              FROM growth_dna_profiles g2
              WHERE g2.workspace_id = g.workspace_id
              ORDER BY g2.created_at DESC
              LIMIT 1
          )
        """
    )


def downgrade() -> None:
    # Backfilled data is indistinguishable from organic data; nothing to undo.
    pass
