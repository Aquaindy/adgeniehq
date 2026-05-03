"""A/B test significance — z-test for two proportions, Wilson-style CIs,
sample-size guidance.

We deliberately use the standard library only (`statistics.NormalDist`) so
the runtime stays scipy-free. The math follows the standard textbook
two-proportion z-test:

    z = (p_a - p_b) / sqrt( p_pool * (1 - p_pool) * (1/n_a + 1/n_b) )

where p_pool = (c_a + c_b) / (n_a + n_b). Two-sided p-value comes from the
normal CDF on |z|.

Confidence intervals around each variant's conversion rate use the standard
normal approximation (Wald) rather than Wilson — sufficient for surfacing
"are these overlapping?" in the dashboard."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from uuid import UUID


# Default z-test confidence level + minimum sample threshold. Surfaced as
# constants so tests + frontend can reference the same numbers.
DEFAULT_CONFIDENCE = 0.95
DEFAULT_MIN_SAMPLE_PER_VARIANT = 100


@dataclass
class VariantStats:
    variant_id: UUID
    name: str
    visits: int
    conversions: int
    conversion_rate: float
    ci_low: float
    ci_high: float


@dataclass
class TestStatistics:
    """Snapshot of a two-variant test's statistical posture.

    `winner_variant_id` is set only when the test reaches
    significance AND each variant has met `min_sample_per_variant`."""

    variants: list[VariantStats]
    p_value: float | None
    z_score: float | None
    relative_lift: float | None
    significant: bool
    confidence: float
    min_sample_per_variant: int
    underpowered: bool
    winner_variant_id: UUID | None


def _wald_interval(visits: int, conversions: int, z: float) -> tuple[float, float]:
    if visits <= 0:
        return (0.0, 0.0)
    p = conversions / visits
    se = math.sqrt(max(p * (1 - p) / visits, 0.0))
    return (max(0.0, p - z * se), min(1.0, p + z * se))


def _two_proportion_z_test(
    visits_a: int, conv_a: int, visits_b: int, conv_b: int
) -> tuple[float | None, float | None]:
    """Return (z, two-sided p_value). Returns (None, None) if either group
    has zero visits or both rates are zero (test is undefined)."""

    if visits_a <= 0 or visits_b <= 0:
        return (None, None)
    p_a = conv_a / visits_a
    p_b = conv_b / visits_b
    pooled = (conv_a + conv_b) / (visits_a + visits_b)
    if pooled in (0.0, 1.0):
        # Degenerate: every visit converted, or none did. No signal to detect.
        return (None, None)
    se = math.sqrt(pooled * (1 - pooled) * (1 / visits_a + 1 / visits_b))
    if se == 0:
        return (None, None)
    z = (p_a - p_b) / se
    nd = NormalDist()
    p = 2 * (1 - nd.cdf(abs(z)))
    return (z, p)


def compute_test_statistics(
    *,
    variants: list[dict],
    confidence: float = DEFAULT_CONFIDENCE,
    min_sample_per_variant: int = DEFAULT_MIN_SAMPLE_PER_VARIANT,
) -> TestStatistics:
    """Compute significance + per-variant CIs.

    `variants` is a list of dicts shaped like:
      { id: UUID, name: str, visits: int, conversions: int, is_control: bool }

    Tests with more than 2 variants get pairwise comparisons against the
    control. The headline `significant`/`p_value` use the best non-control
    challenger (highest conversion rate) vs. the control."""

    z_score_for_alpha = NormalDist().inv_cdf(0.5 + confidence / 2)

    variant_stats: list[VariantStats] = []
    for v in variants:
        visits = int(v.get("visits") or 0)
        conv = int(v.get("conversions") or 0)
        rate = (conv / visits) if visits > 0 else 0.0
        ci_low, ci_high = _wald_interval(visits, conv, z_score_for_alpha)
        variant_stats.append(
            VariantStats(
                variant_id=v["id"],
                name=v.get("name", ""),
                visits=visits,
                conversions=conv,
                conversion_rate=rate,
                ci_low=ci_low,
                ci_high=ci_high,
            )
        )

    if len(variant_stats) < 2:
        return TestStatistics(
            variants=variant_stats,
            p_value=None,
            z_score=None,
            relative_lift=None,
            significant=False,
            confidence=confidence,
            min_sample_per_variant=min_sample_per_variant,
            underpowered=True,
            winner_variant_id=None,
        )

    # Pick control: explicit `is_control`, else first variant.
    control = next(
        (
            (vs, raw)
            for vs, raw in zip(variant_stats, variants)
            if raw.get("is_control")
        ),
        None,
    )
    if control is None:
        control = (variant_stats[0], variants[0])
    control_stats, _ = control

    # Best challenger = highest conversion rate among non-control variants.
    challengers = [vs for vs in variant_stats if vs.variant_id != control_stats.variant_id]
    if not challengers:
        return TestStatistics(
            variants=variant_stats,
            p_value=None,
            z_score=None,
            relative_lift=None,
            significant=False,
            confidence=confidence,
            min_sample_per_variant=min_sample_per_variant,
            underpowered=True,
            winner_variant_id=None,
        )

    challenger = max(challengers, key=lambda vs: vs.conversion_rate)

    z, p = _two_proportion_z_test(
        challenger.visits, challenger.conversions,
        control_stats.visits, control_stats.conversions,
    )

    underpowered = any(
        vs.visits < min_sample_per_variant for vs in variant_stats
    )
    significant = (
        p is not None
        and p < (1 - confidence)
        and not underpowered
    )

    relative_lift: float | None = None
    if control_stats.conversion_rate > 0:
        relative_lift = (
            (challenger.conversion_rate - control_stats.conversion_rate)
            / control_stats.conversion_rate
        )

    winner_id: UUID | None = None
    if significant:
        winner_id = (
            challenger.variant_id
            if challenger.conversion_rate > control_stats.conversion_rate
            else control_stats.variant_id
        )

    return TestStatistics(
        variants=variant_stats,
        p_value=p,
        z_score=z,
        relative_lift=relative_lift,
        significant=significant,
        confidence=confidence,
        min_sample_per_variant=min_sample_per_variant,
        underpowered=underpowered,
        winner_variant_id=winner_id,
    )


def required_sample_size(
    *,
    baseline_rate: float,
    minimum_detectable_effect: float,
    confidence: float = DEFAULT_CONFIDENCE,
    power: float = 0.8,
) -> int:
    """Per-variant sample size needed to detect `minimum_detectable_effect`
    (relative — e.g. 0.10 means a 10% relative improvement) with the given
    power and confidence. Standard textbook formula:

        n = ((z_alpha + z_beta)^2 * (p1*(1-p1) + p2*(1-p2))) / (p2 - p1)^2
    """

    if baseline_rate <= 0 or baseline_rate >= 1:
        return 0
    p1 = baseline_rate
    p2 = baseline_rate * (1 + minimum_detectable_effect)
    if p2 <= 0 or p2 >= 1 or p2 == p1:
        return 0
    nd = NormalDist()
    z_alpha = nd.inv_cdf(0.5 + confidence / 2)
    z_beta = nd.inv_cdf(power)
    numerator = ((z_alpha + z_beta) ** 2) * (p1 * (1 - p1) + p2 * (1 - p2))
    denominator = (p2 - p1) ** 2
    return max(0, math.ceil(numerator / denominator))
