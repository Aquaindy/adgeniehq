import { Card, CardHeader } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { EmailMarketingReport, EmailSegment } from "@/types/api";

function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function scoreTone(score: number): string {
  if (score >= 85) return "text-success";
  if (score >= 70) return "text-grape-700";
  if (score >= 50) return "text-warning";
  return "text-danger";
}

const SUBSCORE_LABELS: Record<string, string> = {
  engagement_open: "Open engagement",
  engagement_click: "Click engagement",
  deliverability_bounce: "Bounce health",
  deliverability_complaint: "Complaint health",
  list_health_unsub: "List health (unsub)",
};

export function EmailReportView({ report }: { report: EmailMarketingReport }) {
  if (report.skipped) {
    return (
      <Card>
        <CardHeader
          title="No data to audit yet"
          subtitle="The audit ran but found no email campaigns with send/open data."
        />
        <p className="mt-3 text-sm text-slate-600">
          Connect Omnisend from Autoresponders, then click <strong>Sync now</strong> above so the
          agent has real campaigns to analyze.
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {report.executive_summary ? (
        <Card className="border-grape-200 bg-grape-50/40">
          <CardHeader title="Executive summary" />
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
            {report.executive_summary}
          </p>
          {report.scope ? (
            <p className="mt-3 text-xs text-slate-500">
              {report.scope.campaigns_analyzed ?? 0} campaigns ·{" "}
              {(report.scope.total_sent ?? 0).toLocaleString()} emails ·{" "}
              {report.scope.provider ?? "omnisend"}
              {report.generated_at
                ? ` · generated ${new Date(report.generated_at).toLocaleString()}`
                : ""}
            </p>
          ) : null}
        </Card>
      ) : null}

      <Section1Audit report={report} />
      <Section2Segments report={report} />
      <Section3BlackFriday report={report} />
      <Section4Trend report={report} />
      <Section5SendDay report={report} />
      <Section6Subjects report={report} />
      <Section7Deliverability report={report} />

      {report.data_caveats && report.data_caveats.length > 0 ? (
        <Card className="bg-slate-50">
          <CardHeader title="Data honesty" subtitle="What this report can and can't see." />
          <ul className="mt-3 flex list-disc flex-col gap-1.5 pl-5 text-xs text-slate-500">
            {report.data_caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

function Section1Audit({ report }: { report: EmailMarketingReport }) {
  const audit = report.section_1_audit;
  if (!audit) return null;
  return (
    <Card>
      <CardHeader
        title="1 · Audit & score"
        subtitle="Composite of engagement, deliverability and list health vs benchmarks."
      />
      <div className="mt-4 flex flex-wrap items-center gap-6">
        <div className="flex items-baseline gap-2">
          <span className={cn("text-5xl font-bold", scoreTone(audit.score))}>{audit.score}</span>
          <span className="text-lg text-slate-400">/100</span>
        </div>
        <span
          className={cn(
            "pill",
            audit.score >= 70 ? "pill-success" : audit.score >= 50 ? "pill-warning" : "pill-danger",
          )}
        >
          {audit.grade}
        </span>
      </div>
      {audit.subscores ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(audit.subscores).map(([key, val]) => (
            <div key={key}>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">{SUBSCORE_LABELS[key] ?? key}</span>
                <span className="font-medium text-ink">{val}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className={cn(
                    "h-full rounded-full",
                    val >= 70 ? "bg-success" : val >= 50 ? "bg-warning" : "bg-danger",
                  )}
                  style={{ width: `${Math.max(0, Math.min(100, val))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {audit.weighted_rates ? (
        <dl className="mt-5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
          <RateStat label="Open" value={audit.weighted_rates.open_rate} />
          <RateStat label="Click" value={audit.weighted_rates.click_rate} />
          <RateStat label="Bounce" value={audit.weighted_rates.bounce_rate} digits={2} invert />
          <RateStat
            label="Complaint"
            value={audit.weighted_rates.complaint_rate}
            digits={3}
            invert
          />
          <RateStat label="Unsub" value={audit.weighted_rates.unsubscribe_rate} digits={2} invert />
        </dl>
      ) : null}
    </Card>
  );
}

function RateStat({
  label,
  value,
  digits = 1,
  invert = false,
}: {
  label: string;
  value: number | undefined;
  digits?: number;
  invert?: boolean;
}) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2">
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className={cn("mt-0.5 text-base font-semibold", invert ? "text-slate-700" : "text-ink")}>
        {pct(value, digits)}
      </dd>
    </div>
  );
}

function SegmentList({ items }: { items: EmailSegment[] }) {
  return (
    <ul className="mt-3 flex flex-col gap-3">
      {items.map((seg, i) => (
        <li key={i} className="rounded-xl border border-slate-100 px-4 py-3">
          <div className="text-sm font-semibold text-ink">{seg.segment}</div>
          <p className="mt-1 text-sm text-slate-600">{seg.why}</p>
        </li>
      ))}
    </ul>
  );
}

function Section2Segments({ report }: { report: EmailMarketingReport }) {
  const seg = report.section_2_segments;
  if (!seg) return null;
  return (
    <Card>
      <CardHeader title="2 · Segments with untapped potential" subtitle={seg.note} />
      {seg.recommended_segments && seg.recommended_segments.length > 0 ? (
        <SegmentList items={seg.recommended_segments} />
      ) : null}
      {seg.ai_suggestions && seg.ai_suggestions.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-grape-700">
            AI suggestions
          </p>
          <SegmentList items={seg.ai_suggestions} />
        </div>
      ) : null}
    </Card>
  );
}

function Section3BlackFriday({ report }: { report: EmailMarketingReport }) {
  const bf = report.section_3_black_friday;
  if (!bf) return null;
  return (
    <Card>
      <CardHeader
        title="3 · Black Friday campaign draft"
        subtitle={bf.angle}
        action={
          bf.note ? <span className="pill bg-slate-100 text-slate-600">Edit before sending</span> : null
        }
      />
      {bf.segment ? (
        <div className="mt-3 text-sm">
          <span className="text-slate-400">Target segment: </span>
          <span className="font-medium text-ink">{bf.segment}</span>
        </div>
      ) : null}
      {bf.subject_lines && bf.subject_lines.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Subject lines
          </p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {bf.subject_lines.map((s, i) => (
              <li
                key={i}
                className="rounded-lg bg-grape-50 px-3 py-1.5 text-sm text-grape-800"
              >
                {s}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {bf.template_draft ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Template draft
          </p>
          <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm leading-relaxed text-slate-700">
            {bf.template_draft}
          </pre>
        </div>
      ) : null}
    </Card>
  );
}

function Section4Trend({ report }: { report: EmailMarketingReport }) {
  const t = report.section_4_open_rate_trend;
  if (!t) return null;
  const monthly = t.monthly ?? [];
  const maxRate = Math.max(0.0001, ...monthly.map((m) => m.open_rate ?? 0));
  return (
    <Card>
      <CardHeader
        title="4 · Open-rate trend"
        subtitle={t.note ?? "Weighted open rate by month."}
        action={
          t.direction ? (
            <span
              className={cn(
                "pill",
                t.direction === "down" && "pill-danger",
                t.direction === "up" && "pill-success",
                t.direction === "flat" && "bg-slate-100 text-slate-600",
              )}
            >
              {t.direction === "down" ? "▼" : t.direction === "up" ? "▲" : "▶"}{" "}
              {t.relative_change !== undefined ? pct(Math.abs(t.relative_change), 0) : ""} MoM
            </span>
          ) : null
        }
      />
      {monthly.length > 0 ? (
        <div className="mt-4 flex items-end gap-3 overflow-x-auto pb-2">
          {monthly.map((m) => (
            <div key={m.month} className="flex min-w-[44px] flex-1 flex-col items-center gap-1">
              <div className="flex h-28 w-full items-end">
                <div
                  className={cn(
                    "w-full rounded-t-md",
                    m.month === t.latest_month ? "bg-grape" : "bg-grape-200",
                  )}
                  style={{
                    height: `${Math.max(4, ((m.open_rate ?? 0) / maxRate) * 100)}%`,
                  }}
                  title={`${pct(m.open_rate)} · ${m.sent.toLocaleString()} sent`}
                />
              </div>
              <span className="text-[10px] font-medium text-slate-500">{pct(m.open_rate, 0)}</span>
              <span className="text-[10px] text-slate-400">{m.month.slice(2)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </Card>
  );
}

function Section5SendDay({ report }: { report: EmailMarketingReport }) {
  const s = report.section_5_best_send_day;
  if (!s) return null;
  const rows = s.by_day_of_week ?? [];
  const maxRate = Math.max(0.0001, ...rows.map((r) => r.open_rate ?? 0));
  return (
    <Card>
      <CardHeader
        title="5 · Best send day"
        subtitle={s.caveat}
        action={
          s.best_day ? (
            <span className="pill pill-success">Best: {s.best_day}</span>
          ) : null
        }
      />
      {rows.length > 0 ? (
        <ul className="mt-4 flex flex-col gap-2">
          {rows.map((r) => (
            <li key={r.day} className="flex items-center gap-3 text-sm">
              <span className="w-20 shrink-0 text-slate-500">{r.day}</span>
              <div className="h-3 flex-1 overflow-hidden rounded-full bg-slate-100">
                <div
                  className={cn(
                    "h-full rounded-full",
                    r.day === s.best_day ? "bg-grape" : "bg-grape-200",
                  )}
                  style={{ width: `${((r.open_rate ?? 0) / maxRate) * 100}%` }}
                />
              </div>
              <span className="w-12 shrink-0 text-right font-medium text-ink">
                {pct(r.open_rate)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-slate-500">Not enough dated sends to rank days yet.</p>
      )}
    </Card>
  );
}

function Section6Subjects({ report }: { report: EmailMarketingReport }) {
  const s = report.section_6_subject_patterns;
  if (!s) return null;
  return (
    <Card>
      <CardHeader
        title="6 · Subject-line patterns"
        subtitle={
          s.note ?? `What lifts opens across the last ${s.window_days ?? 183} days.`
        }
      />
      {s.patterns && s.patterns.length > 0 ? (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[440px] text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-slate-400">
                <th className="pb-2 font-medium">Pattern</th>
                <th className="pb-2 text-right font-medium">With</th>
                <th className="pb-2 text-right font-medium">Without</th>
                <th className="pb-2 text-right font-medium">Lift</th>
                <th className="pb-2 text-right font-medium">#</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {s.patterns.map((p) => (
                <tr key={p.pattern}>
                  <td className="py-2 font-medium text-ink">{p.pattern}</td>
                  <td className="py-2 text-right text-slate-600">{pct(p.open_rate_with)}</td>
                  <td className="py-2 text-right text-slate-600">{pct(p.open_rate_without)}</td>
                  <td
                    className={cn(
                      "py-2 text-right font-semibold",
                      p.lift > 0 ? "text-success" : p.lift < 0 ? "text-danger" : "text-slate-500",
                    )}
                  >
                    {p.lift > 0 ? "+" : ""}
                    {pct(p.lift)}
                  </td>
                  <td className="py-2 text-right text-slate-400">{p.campaigns_with}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {s.top_subjects && s.top_subjects.length > 0 ? (
        <div className="mt-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Top subjects by open rate
          </p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {s.top_subjects.map((t, i) => (
              <li
                key={i}
                className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-1.5 text-sm"
              >
                <span className="truncate text-slate-700">{t.subject}</span>
                <span className="shrink-0 font-medium text-grape-700">{pct(t.open_rate)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}

function Section7Deliverability({ report }: { report: EmailMarketingReport }) {
  const d = report.section_7_deliverability;
  if (!d) return null;
  const atRisk = d.verdict === "at_risk";
  return (
    <Card className={cn(atRisk && "border-red-200 bg-red-50/40")}>
      <CardHeader
        title="7 · Deliverability & spam risk"
        subtitle={d.not_covered}
        action={
          <span className={cn("pill", atRisk ? "pill-danger" : "pill-success")}>
            {atRisk ? "At risk" : "Healthy"}
          </span>
        }
      />
      {d.flags && d.flags.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-2">
          {d.flags.map((f, i) => (
            <li
              key={i}
              className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"
              role="alert"
            >
              {f}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-slate-600">
          No complaint, bounce or unsubscribe thresholds are being breached.
        </p>
      )}
      <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <RateStat label="Complaint" value={d.complaint_rate} digits={3} invert />
        <RateStat label="Bounce" value={d.bounce_rate} digits={2} invert />
        <RateStat label="Unsub" value={d.unsubscribe_rate} digits={2} invert />
      </dl>
    </Card>
  );
}
