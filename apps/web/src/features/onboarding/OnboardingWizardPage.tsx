import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  generateGrowthDna,
  getOnboarding,
  updateOnboarding,
} from "@/lib/onboarding";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  AdPlatform,
  AnalyticsStatus,
  CompetitorEntry,
  OnboardingUpdate,
} from "@/types/api";

const PLATFORMS: { value: AdPlatform; label: string }[] = [
  { value: "google_ads", label: "Google Ads" },
  { value: "meta_ads", label: "Meta Ads" },
  { value: "linkedin_ads", label: "LinkedIn Ads" },
  { value: "tiktok_ads", label: "TikTok Ads" },
  { value: "microsoft_ads", label: "Microsoft Ads" },
  { value: "x_ads", label: "X Ads" },
  { value: "pinterest_ads", label: "Pinterest Ads" },
  { value: "other", label: "Other" },
];

const ANALYTICS_OPTIONS: { value: AnalyticsStatus; label: string; description: string }[] = [
  { value: "configured", label: "Fully configured", description: "GA4 set up, conversion events firing." },
  { value: "partial", label: "Partial", description: "Something is in place but quality is unclear." },
  { value: "none", label: "Nothing yet", description: "No analytics or conversion tracking yet." },
  { value: "unknown", label: "Not sure", description: "Need help auditing what's there." },
];

const STEPS = [
  "Business",
  "Audience & offer",
  "Goals & budget",
  "Channels & analytics",
  "Brand voice",
] as const;

type FormState = {
  business_name: string;
  website_url: string;
  industry: string;
  target_audience: string;
  offer_description: string;
  pain_points: string;
  primary_conversion_goal: string;
  monthly_ad_budget_min_usd: string;
  monthly_ad_budget_max_usd: string;
  geographic_target: string;
  current_ad_platforms: AdPlatform[];
  landing_page_urls: string;
  analytics_status: AnalyticsStatus | "";
  competitors: CompetitorEntry[];
  brand_voice: string;
};

const EMPTY: FormState = {
  business_name: "",
  website_url: "",
  industry: "",
  target_audience: "",
  offer_description: "",
  pain_points: "",
  primary_conversion_goal: "",
  monthly_ad_budget_min_usd: "",
  monthly_ad_budget_max_usd: "",
  geographic_target: "",
  current_ad_platforms: [],
  landing_page_urls: "",
  analytics_status: "",
  competitors: [],
  brand_voice: "",
};


/**
 * FastAPI's RequestValidationError comes back as `details: [{loc:[...],
 * msg, type, input}, ...]`. The default `err.message` is the generic
 * "Request validation failed." which is useless to the user. This
 * helper turns the structured details into "Primary conversion goal —
 * String should have at most 500 characters." so the user can fix it.
 */
function formatApiError(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  if (err.code === "validation_error" && Array.isArray(err.details)) {
    const issues = err.details
      .map((d) => {
        const obj = d as { loc?: unknown[]; msg?: string };
        const loc = (obj.loc ?? []).filter(
          (segment): segment is string => typeof segment === "string" && segment !== "body",
        );
        const fieldName = loc[loc.length - 1] ?? "field";
        const label = FIELD_LABELS[fieldName] ?? fieldName.replace(/_/g, " ");
        return `${label} — ${obj.msg ?? "invalid"}`;
      })
      .filter(Boolean);
    if (issues.length > 0) return issues.join("\n");
  }
  return err.message || fallback;
}

const FIELD_LABELS: Record<string, string> = {
  business_name: "Business name",
  website_url: "Website URL",
  industry: "Industry",
  target_audience: "Target audience",
  offer_description: "Offer description",
  pain_points: "Pain points",
  primary_conversion_goal: "Primary conversion goal",
  monthly_ad_budget_min_usd: "Monthly ad budget — minimum",
  monthly_ad_budget_max_usd: "Monthly ad budget — maximum",
  geographic_target: "Geographic targets",
  current_ad_platforms: "Current ad platforms",
  landing_page_urls: "Landing page URLs",
  analytics_status: "Analytics status",
  competitors: "Competitors",
  brand_voice: "Brand voice",
};


export function OnboardingWizardPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);

  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const onboarding = useQuery({
    queryKey: ["onboarding", workspaceId],
    queryFn: () => getOnboarding(workspaceId!),
    enabled: !!workspaceId,
  });

  // Hydrate form state from server
  useEffect(() => {
    const data = onboarding.data;
    if (!data) return;
    setForm({
      business_name: data.business_name ?? "",
      website_url: data.website_url ?? "",
      industry: data.industry ?? "",
      target_audience: data.target_audience ?? "",
      offer_description: data.offer_description ?? "",
      pain_points: data.pain_points ?? "",
      primary_conversion_goal: data.primary_conversion_goal ?? "",
      monthly_ad_budget_min_usd:
        data.monthly_ad_budget_min_usd != null
          ? String(data.monthly_ad_budget_min_usd)
          : "",
      monthly_ad_budget_max_usd:
        data.monthly_ad_budget_max_usd != null
          ? String(data.monthly_ad_budget_max_usd)
          : "",
      geographic_target: data.geographic_target ?? "",
      current_ad_platforms: data.current_ad_platforms ?? [],
      landing_page_urls: (data.landing_page_urls ?? []).join("\n"),
      analytics_status: data.analytics_status ?? "",
      competitors: data.competitors ?? [],
      brand_voice: data.brand_voice ?? "",
    });
    if (data.step_completed && data.completed_at == null) {
      setStep(Math.min(data.step_completed, STEPS.length - 1));
    }
  }, [onboarding.data]);

  const update = useMutation({
    mutationFn: (payload: OnboardingUpdate) => updateOnboarding(workspaceId!, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["onboarding", workspaceId] }),
  });

  const generate = useMutation({
    mutationFn: () => generateGrowthDna(workspaceId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["growth-dna", workspaceId] });
      navigate("/growth-dna", { replace: true });
    },
  });

  function setField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function buildPayloadForStep(currentStep: number): OnboardingUpdate {
    const payload: OnboardingUpdate = { step_completed: currentStep + 1 };
    if (currentStep === 0) {
      payload.business_name = form.business_name.trim() || undefined;
      payload.website_url = form.website_url.trim() || undefined;
      payload.industry = form.industry.trim() || undefined;
    }
    if (currentStep === 1) {
      payload.target_audience = form.target_audience.trim() || undefined;
      payload.offer_description = form.offer_description.trim() || undefined;
      payload.pain_points = form.pain_points.trim() || undefined;
    }
    if (currentStep === 2) {
      payload.primary_conversion_goal = form.primary_conversion_goal.trim() || undefined;
      const minRaw = form.monthly_ad_budget_min_usd.trim();
      const maxRaw = form.monthly_ad_budget_max_usd.trim();
      if (minRaw !== "") {
        payload.monthly_ad_budget_min_usd = Math.max(0, Math.floor(Number(minRaw)));
      }
      if (maxRaw !== "") {
        payload.monthly_ad_budget_max_usd = Math.max(0, Math.floor(Number(maxRaw)));
      }
      payload.geographic_target = form.geographic_target.trim() || undefined;
    }
    if (currentStep === 3) {
      payload.current_ad_platforms = form.current_ad_platforms;
      payload.landing_page_urls =
        form.landing_page_urls
          .split("\n")
          .map((v) => v.trim())
          .filter(Boolean) || undefined;
      if (form.analytics_status) payload.analytics_status = form.analytics_status;
      payload.competitors = form.competitors.filter((c) => c.name.trim().length > 0);
    }
    if (currentStep === 4) {
      payload.brand_voice = form.brand_voice.trim() || undefined;
      payload.mark_completed = true;
    }
    return payload;
  }

  async function onAdvance(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    try {
      await update.mutateAsync(buildPayloadForStep(step));
    } catch (err) {
      setError(formatApiError(err, "Could not save your answers."));
      return;
    }

    if (step < STEPS.length - 1) {
      setStep(step + 1);
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }

    // Final step → generate Growth DNA
    try {
      await generate.mutateAsync();
    } catch (err) {
      setError(formatApiError(err, "Could not generate Growth DNA Profile."));
    }
  }

  if (!workspaceId || onboarding.isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-sm text-slate-400">
        Loading onboarding…
      </div>
    );
  }

  const submitting = update.isPending || generate.isPending;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Onboarding</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          Tell us about your business
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          AdVanta uses these answers to generate your Growth DNA Profile — readiness scores,
          recommended first campaigns, and a 30-day plan. You can refine answers later.
        </p>
      </header>

      <ProgressBar step={step} />

      <form onSubmit={onAdvance} className="flex flex-col gap-4" noValidate>
        {step === 0 && <BusinessStep form={form} setField={setField} />}
        {step === 1 && <AudienceStep form={form} setField={setField} />}
        {step === 2 && <GoalsStep form={form} setField={setField} />}
        {step === 3 && <ChannelsStep form={form} setField={setField} />}
        {step === 4 && <BrandStep form={form} setField={setField} />}

        {error ? (
          <div
            className="whitespace-pre-line rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"
            role="alert"
          >
            {error}
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-3">
          <Button
            type="button"
            variant="ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0 || submitting}
          >
            Back
          </Button>
          <Button type="submit" disabled={submitting}>
            {step < STEPS.length - 1
              ? submitting
                ? "Saving…"
                : "Continue"
              : submitting
                ? "Generating Growth DNA…"
                : "Generate Growth DNA Profile"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function ProgressBar({ step }: { step: number }) {
  return (
    <ol className="flex items-center gap-2">
      {STEPS.map((label, idx) => (
        <li key={label} className="flex flex-1 flex-col gap-1">
          <span
            className={cn(
              "h-1.5 rounded-full",
              idx <= step ? "bg-grape" : "bg-slate-200",
            )}
          />
          <span
            className={cn(
              "text-[11px] font-medium uppercase tracking-wider",
              idx <= step ? "text-grape-700" : "text-slate-400",
            )}
          >
            {label}
          </span>
        </li>
      ))}
    </ol>
  );
}

type StepProps = {
  form: FormState;
  setField: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
};

function BusinessStep({ form, setField }: StepProps) {
  return (
    <Card>
      <CardHeader title="Business basics" />
      <div className="mt-4 flex flex-col gap-4">
        <TextField
          id="business_name"
          label="Business name"
          required
          value={form.business_name}
          onChange={(v) => setField("business_name", v)}
        />
        <TextField
          id="website_url"
          label="Website URL"
          type="url"
          placeholder="https://"
          required
          value={form.website_url}
          onChange={(v) => setField("website_url", v)}
        />
        <TextField
          id="industry"
          label="Industry"
          placeholder="e.g. B2B SaaS"
          value={form.industry}
          onChange={(v) => setField("industry", v)}
        />
      </div>
    </Card>
  );
}

function AudienceStep({ form, setField }: StepProps) {
  return (
    <Card>
      <CardHeader title="Audience & offer" subtitle="The clearer this is, the sharper the targeting." />
      <div className="mt-4 flex flex-col gap-4">
        <TextArea
          id="target_audience"
          label="Target audience"
          rows={3}
          required
          placeholder="Who buys from you? Roles, company size, traits…"
          value={form.target_audience}
          onChange={(v) => setField("target_audience", v)}
        />
        <TextArea
          id="offer_description"
          label="Offer / product description"
          rows={4}
          required
          placeholder="What do you sell, what outcome does it produce, why is it different?"
          value={form.offer_description}
          onChange={(v) => setField("offer_description", v)}
        />
        <TextArea
          id="pain_points"
          label="Top pain points"
          rows={3}
          placeholder="What makes someone start looking for a solution like yours?"
          value={form.pain_points}
          onChange={(v) => setField("pain_points", v)}
        />
      </div>
    </Card>
  );
}

function GoalsStep({ form, setField }: StepProps) {
  return (
    <Card>
      <CardHeader title="Goals & budget" />
      <div className="mt-4 flex flex-col gap-4">
        <TextField
          id="primary_conversion_goal"
          label="Primary conversion goal"
          required
          placeholder="e.g. Demo bookings, signups, lead form fills"
          value={form.primary_conversion_goal}
          onChange={(v) => setField("primary_conversion_goal", v)}
        />
        <fieldset className="flex flex-col gap-1.5">
          <legend className="text-sm font-medium text-slate-text">
            Monthly ad budget range (USD)
          </legend>
          <p className="text-xs text-slate-500">
            Floor and ceiling for the agents to plan against. Set both
            equal if your budget is fixed.
          </p>
          <div className="mt-1 grid gap-3 sm:grid-cols-2">
            <TextField
              id="monthly_ad_budget_min_usd"
              label="Minimum"
              type="number"
              inputMode="numeric"
              placeholder="e.g. 5000"
              value={form.monthly_ad_budget_min_usd}
              onChange={(v) => setField("monthly_ad_budget_min_usd", v)}
            />
            <TextField
              id="monthly_ad_budget_max_usd"
              label="Maximum"
              type="number"
              inputMode="numeric"
              placeholder="e.g. 8000"
              value={form.monthly_ad_budget_max_usd}
              onChange={(v) => setField("monthly_ad_budget_max_usd", v)}
            />
          </div>
        </fieldset>
        <TextArea
          id="geographic_target"
          label="Geographic targets"
          rows={2}
          placeholder="e.g. United States, Canada, English-speaking EU"
          value={form.geographic_target}
          onChange={(v) => setField("geographic_target", v)}
        />
      </div>
    </Card>
  );
}

function ChannelsStep({ form, setField }: StepProps) {
  function togglePlatform(value: AdPlatform) {
    setField(
      "current_ad_platforms",
      form.current_ad_platforms.includes(value)
        ? form.current_ad_platforms.filter((p) => p !== value)
        : [...form.current_ad_platforms, value],
    );
  }

  function setCompetitor(idx: number, patch: Partial<CompetitorEntry>) {
    const next = [...form.competitors];
    const current = next[idx] ?? { name: "" };
    next[idx] = { ...current, ...patch };
    setField("competitors", next);
  }

  function addCompetitor() {
    setField("competitors", [...form.competitors, { name: "", url: "" }]);
  }

  function removeCompetitor(idx: number) {
    setField(
      "competitors",
      form.competitors.filter((_, i) => i !== idx),
    );
  }

  return (
    <Card>
      <CardHeader
        title="Channels & analytics"
        subtitle="Where you advertise today and how well you can measure it."
      />
      <div className="mt-4 flex flex-col gap-4">
        <fieldset>
          <legend className="text-sm font-medium text-slate-text">Ad platforms in use</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {PLATFORMS.map((p) => {
              const active = form.current_ad_platforms.includes(p.value);
              return (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => togglePlatform(p.value)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm font-medium transition",
                    active
                      ? "border-grape bg-grape-100 text-grape-700"
                      : "border-slate-200 bg-white text-slate-700 hover:border-grape-200",
                  )}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <TextArea
          id="landing_page_urls"
          label="Landing page URLs"
          rows={3}
          placeholder={"One URL per line\nhttps://example.com/pricing"}
          value={form.landing_page_urls}
          onChange={(v) => setField("landing_page_urls", v)}
        />

        <fieldset>
          <legend className="text-sm font-medium text-slate-text">Analytics status</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {ANALYTICS_OPTIONS.map((opt) => {
              const active = form.analytics_status === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setField("analytics_status", opt.value)}
                  className={cn(
                    "rounded-xl border p-3 text-left text-sm transition",
                    active
                      ? "border-grape bg-grape-50"
                      : "border-slate-200 bg-white hover:border-grape-200",
                  )}
                >
                  <div className="font-medium text-ink">{opt.label}</div>
                  <div className="mt-0.5 text-xs text-slate-500">{opt.description}</div>
                </button>
              );
            })}
          </div>
        </fieldset>

        <fieldset>
          <div className="flex items-center justify-between">
            <legend className="text-sm font-medium text-slate-text">Competitors</legend>
            <button
              type="button"
              onClick={addCompetitor}
              className="text-sm font-medium text-grape-700 hover:text-grape-800"
            >
              + Add
            </button>
          </div>
          <div className="mt-2 flex flex-col gap-2">
            {form.competitors.length === 0 ? (
              <p className="text-xs text-slate-400">
                Optional — list 1–3 competitors so the Market Intelligence Agent has a starting set.
              </p>
            ) : null}
            {form.competitors.map((c, idx) => (
              <div key={idx} className="flex flex-col gap-2 sm:flex-row">
                <input
                  type="text"
                  placeholder="Competitor name"
                  value={c.name}
                  onChange={(e) => setCompetitor(idx, { name: e.target.value })}
                  className="flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
                />
                <input
                  type="url"
                  placeholder="https://"
                  value={c.url ?? ""}
                  onChange={(e) => setCompetitor(idx, { url: e.target.value })}
                  className="flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
                />
                <button
                  type="button"
                  onClick={() => removeCompetitor(idx)}
                  className="self-start text-xs text-slate-400 hover:text-red-700"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </fieldset>
      </div>
    </Card>
  );
}

function BrandStep({ form, setField }: StepProps) {
  return (
    <Card>
      <CardHeader
        title="Brand voice"
        subtitle="How should generated copy sound? One short paragraph is plenty."
      />
      <div className="mt-4 flex flex-col gap-4">
        <TextArea
          id="brand_voice"
          label="Brand voice"
          rows={4}
          placeholder="e.g. Confident, executive, calm. Short sentences. No hype."
          value={form.brand_voice}
          onChange={(v) => setField("brand_voice", v)}
        />
        <p className="text-xs text-slate-500">
          When you click <span className="font-medium text-grape-700">Generate Growth DNA Profile</span>,
          AdVanta will compute readiness scores, recommended first campaigns, and your 30-day plan
          from these answers — all derived from your inputs, no fabricated metrics.
        </p>
      </div>
    </Card>
  );
}

function TextField({
  id,
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  required,
  inputMode,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  required?: boolean;
  inputMode?: "numeric" | "text" | "url";
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm" htmlFor={id}>
      <span className="font-medium text-slate-text">
        {label}
        {required ? <span className="ml-1 text-grape-700">*</span> : null}
      </span>
      <input
        id={id}
        type={type}
        inputMode={inputMode}
        value={value}
        placeholder={placeholder}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
      />
    </label>
  );
}

function TextArea({
  id,
  label,
  value,
  onChange,
  rows = 3,
  placeholder,
  required,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm" htmlFor={id}>
      <span className="font-medium text-slate-text">
        {label}
        {required ? <span className="ml-1 text-grape-700">*</span> : null}
      </span>
      <textarea
        id={id}
        rows={rows}
        value={value}
        placeholder={placeholder}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
      />
    </label>
  );
}
