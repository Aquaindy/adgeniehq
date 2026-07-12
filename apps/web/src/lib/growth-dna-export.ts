import type { GrowthDna } from "@/types/api";

/** Render the full Growth DNA Profile as a portable Markdown document. */
export function growthDnaToMarkdown(dna: GrowthDna): string {
  const out: string[] = [];
  const push = (s = "") => out.push(s);

  push("# Growth DNA Profile");
  push();
  push(`_Generated ${new Date(dna.created_at).toLocaleString()} · engine ${dna.engine_version}_`);
  push();

  push("## Business summary");
  push(dna.business_summary);
  push();
  push("## ICP summary");
  push(dna.icp_summary);
  push();
  push("## Offer positioning");
  push(dna.offer_positioning);
  push();

  push("## Readiness scores");
  push(`- Funnel readiness: **${dna.funnel_readiness_score}/100**`);
  push(`- Paid ads readiness: **${dna.paid_ads_readiness_score}/100**`);
  push();

  push("## SEO / GEO opportunity");
  push(dna.seo_geo_opportunity_summary);
  push();

  if (dna.website_conversion_risks.length) {
    push("## Website conversion risks");
    dna.website_conversion_risks.forEach((r) => push(`- ${r}`));
    push();
  }

  push("## Tracking readiness");
  push(dna.tracking_readiness);
  push();

  if (dna.recommended_first_campaigns.length) {
    push("## Recommended first campaigns");
    dna.recommended_first_campaigns.forEach((c) =>
      push(`- **${c.platform}** · ${c.objective} · ${c.budget_share_pct}% — ${c.rationale}`),
    );
    push();
  }

  if (dna.thirty_day_growth_plan.length) {
    push("## 30-day growth plan");
    dna.thirty_day_growth_plan.forEach((w) => {
      push(`### Week ${w.week}: ${w.focus}`);
      w.deliverables.forEach((d) => push(`- ${d}`));
      push();
    });
  }

  const ms = dna.marketing_strategy;
  if (ms) {
    push("## Marketing strategy");
    if (ms.overview?.thesis) {
      push(`**Thesis:** ${ms.overview.thesis}`);
      push();
    }
    if (ms.overview?.priorities?.length) {
      push(`**Priorities:** ${ms.overview.priorities.join(", ")}`);
      push();
    }
    if (ms.overview?.budget_allocation?.length) {
      push("### Budget allocation");
      ms.overview.budget_allocation.forEach((b) =>
        push(`- ${b.channel}: ${b.pct}%${b.rationale ? ` — ${b.rationale}` : ""}`),
      );
      push();
    }

    if (ms.channels?.length) {
      push("### Channels");
      ms.channels.forEach((c) => {
        push(`#### ${c.channel} (${c.category} · ${c.priority})`);
        if (c.summary) push(c.summary);
        (c.tactics ?? []).forEach((t) => push(`- ${t}`));
        if (c.kpis?.length) push(`KPIs: ${c.kpis.join(", ")}`);
        if (c.first_step) push(`First step: ${c.first_step}`);
        push();
      });
    }

    if (ms.content_pillars?.length) {
      push("### Content pillars");
      ms.content_pillars.forEach((p) => {
        push(`- **${p.name}** (${p.allocation_pct}%)${p.description ? ` — ${p.description}` : ""}`);
        (p.example_hooks ?? []).forEach((h) => push(`  - "${h}"`));
      });
      push();
    }

    if (ms.platform_strategy?.length) {
      push("### Platform strategy");
      ms.platform_strategy.forEach((p) =>
        push(
          `- **${p.platform}** · ${p.cadence} · ${p.focus}${p.best_for ? ` · best for ${p.best_for}` : ""}`,
        ),
      );
      push();
    }

    if (ms.email_strategy) {
      push("### Email strategy");
      if (ms.email_strategy.summary) push(ms.email_strategy.summary);
      if (ms.email_strategy.newsletter_cadence)
        push(`Newsletter cadence: ${ms.email_strategy.newsletter_cadence}`);
      (ms.email_strategy.flows ?? []).forEach((f) =>
        push(`- **${f.name}** · trigger: ${f.trigger} · goal: ${f.goal}`),
      );
      push();
    }

    if (ms.content_calendar?.length) {
      push("### Content calendar");
      ms.content_calendar.forEach((e) =>
        push(
          `- Day ${e.day} · ${e.channel} · ${e.format} · ${e.pillar} — ${e.hook}${e.caption_direction ? ` (${e.caption_direction})` : ""}`,
        ),
      );
      push();
    }
  }

  return out.join("\n");
}

export function growthDnaFilename(dna: GrowthDna, ext: string): string {
  const base =
    (dna.label || dna.business_summary || "growth-dna")
      .slice(0, 48)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "growth-dna";
  return `${base}-growth-dna.${ext}`;
}

/** Trigger a client-side file download. */
export function downloadTextFile(filename: string, content: string, mime = "text/plain"): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
