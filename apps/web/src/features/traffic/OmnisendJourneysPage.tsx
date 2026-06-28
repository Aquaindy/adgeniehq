import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import { generateJourney, listJourneyTypes, syncLeadSource } from "@/lib/omnisend";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { JourneyEmail, OmnisendJourney } from "@/types/api";

export function OmnisendJourneysPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const [params] = useSearchParams();

  const types = useQuery({
    queryKey: ["omnisend", "journey-types", workspaceId],
    queryFn: () => listJourneyTypes(workspaceId!),
    enabled: !!workspaceId,
  });

  const [journeyType, setJourneyType] = useState(params.get("type") ?? "welcome");
  const [channel, setChannel] = useState("email");
  const [offerName, setOfferName] = useState("");
  const [offerUrl, setOfferUrl] = useState("");
  const [audience, setAudience] = useState("");
  const [tag, setTag] = useState(params.get("tag") ?? "");
  const [journey, setJourney] = useState<OmnisendJourney | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedType = useMemo(
    () => types.data?.find((t) => t.slug === journeyType),
    [types.data, journeyType],
  );

  // Default the channel to the selected journey's default when it changes.
  useEffect(() => {
    if (selectedType) setChannel(selectedType.default_channel);
  }, [selectedType]);

  const generate = useMutation({
    mutationFn: () =>
      generateJourney(workspaceId!, {
        journey_type: journeyType,
        channel,
        offer_name: offerName || undefined,
        offer_url: offerUrl || undefined,
        audience: audience || undefined,
        tag: tag || undefined,
      }),
    onSuccess: (data) => {
      setJourney(data);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not generate the journey."),
  });

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Traffic Genie · Omnisend</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">Omnisend journeys</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-500">
          Generate a complete Omnisend automation blueprint — trigger, segmentation, the full email
          (and SMS) sequence with delays, subjects and copy, exit conditions and the conversion goal —
          then build it once in Omnisend, triggered by your campaign tag.
        </p>
      </header>

      <Card>
        <CardHeader title="Build a journey" subtitle="Pick a flow, add your offer, and generate the blueprint." />
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-slate-500">Journey type</span>
            <select
              value={journeyType}
              onChange={(e) => setJourneyType(e.target.value)}
              className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
            >
              {types.data?.map((t) => <option key={t.slug} value={t.slug}>{t.name}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-slate-500">Channel</span>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
            >
              <option value="email">Email only</option>
              <option value="email_sms">Email + SMS</option>
            </select>
          </label>
          <Input label="Offer name" value={offerName} onChange={setOfferName} placeholder="Free SEO checklist" />
          <Input label="Offer URL" value={offerUrl} onChange={setOfferUrl} placeholder="https://…" />
          <Input label="Audience" value={audience} onChange={setAudience} placeholder="Bloggers, SaaS founders…" />
          <Input label="Trigger tag (optional)" value={tag} onChange={setTag} placeholder="solo_ads_vendorx_q3" />
        </div>
        {selectedType ? (
          <p className="mt-3 text-xs text-slate-500">
            <span className="font-medium text-slate-600">Trigger:</span> {selectedType.trigger} ·{" "}
            <span className="font-medium text-slate-600">Default steps:</span> {selectedType.default_steps.length}
          </p>
        ) : null}
        {error ? <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</div> : null}
        <div className="mt-5">
          <Button onClick={() => generate.mutate()} disabled={generate.isPending || !workspaceId}>
            {generate.isPending ? "Generating…" : "Generate journey"}
          </Button>
        </div>
      </Card>

      {journey ? <JourneyView journey={journey} /> : null}

      {workspaceId ? <TagOptinsPanel workspaceId={workspaceId} defaultTag={tag} /> : null}
    </div>
  );
}

function JourneyView({ journey }: { journey: OmnisendJourney }) {
  return (
    <div className="flex flex-col gap-4">
      <Card className="border-grape-200 bg-grape-50/40">
        <CardHeader title={journey.flow_name ?? journey.journey_name ?? "Journey"} subtitle={journey.segmentation_rules} />
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
          <Meta label="Trigger" value={journey.trigger} />
          <Meta label="Channel" value={journey.channel === "email_sms" ? "Email + SMS" : "Email"} />
          <Meta label="Conversion goal" value={journey.conversion_goal} />
        </dl>
      </Card>

      <Card>
        <CardHeader title="Email sequence" subtitle={`${journey.email_sequence?.length ?? 0} steps`} />
        <ol className="mt-3 flex flex-col gap-3">
          {journey.email_sequence?.map((e) => <EmailStep key={e.step} email={e} />)}
        </ol>
      </Card>

      {journey.sms_sequence && journey.sms_sequence.length > 0 ? (
        <Card>
          <CardHeader title="SMS sequence" subtitle={`${journey.sms_sequence.length} messages`} />
          <ul className="mt-3 flex flex-col gap-2">
            {journey.sms_sequence.map((s, i) => (
              <li key={i} className="flex items-start gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <span className="pill bg-grape-100 text-grape-700">{s.delay}</span>
                <span className="text-slate-700">{s.message}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        {journey.exit_conditions && journey.exit_conditions.length > 0 ? (
          <Card>
            <CardHeader title="Exit conditions" />
            <ul className="mt-3 flex list-disc flex-col gap-1.5 pl-5 text-sm text-slate-700">
              {journey.exit_conditions.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </Card>
        ) : null}
        {journey.implementation_notes && journey.implementation_notes.length > 0 ? (
          <Card className="bg-amber-50">
            <CardHeader title="How to build it in Omnisend" />
            <ul className="mt-3 flex list-disc flex-col gap-1.5 pl-5 text-xs text-amber-800">
              {journey.implementation_notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          </Card>
        ) : null}
      </div>
    </div>
  );
}

function EmailStep({ email }: { email: JourneyEmail }) {
  const [copied, setCopied] = useState(false);
  return (
    <li className="rounded-xl border border-slate-100 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded-full bg-grape-100 text-xs font-semibold text-grape-700">{email.step}</span>
          <span className="pill bg-slate-100 text-slate-600">{email.delay}</span>
        </div>
        <Button
          variant="ghost"
          className="text-xs"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(`Subject: ${email.subject}\n\n${email.body}`);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            } catch { /* clipboard unavailable */ }
          }}
        >
          {copied ? "Copied!" : "Copy"}
        </Button>
      </div>
      <div className="mt-2 text-sm font-semibold text-ink">{email.subject}</div>
      {email.preheader ? <div className="text-xs text-slate-400">{email.preheader}</div> : null}
      <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">{email.body}</pre>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        {email.cta ? <span className="pill pill-grape">{email.cta}</span> : null}
        {email.personalization_tokens?.map((t) => (
          <span key={t} className="pill bg-slate-100 text-slate-500">{t}</span>
        ))}
      </div>
    </li>
  );
}

function TagOptinsPanel({ workspaceId, defaultTag }: { workspaceId: string; defaultTag: string }) {
  const [tag, setTag] = useState(defaultTag);
  const [emails, setEmails] = useState("");
  const [notConnected, setNotConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (defaultTag) setTag(defaultTag); }, [defaultTag]);

  const sync = useMutation({
    mutationFn: () => {
      const contacts = emails
        .split(/[\s,;]+/)
        .map((e) => e.trim())
        .filter((e) => e.includes("@"))
        .map((email) => ({ email }));
      return syncLeadSource(workspaceId, { tag, source: "traffic_lead_source", contacts });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "autoresponder_not_connected") setNotConnected(true);
      setError(err instanceof ApiError ? err.message : "Could not tag contacts.");
    },
    onSuccess: () => { setError(null); setNotConnected(false); },
  });

  return (
    <Card>
      <CardHeader
        title="Tag opt-ins in Omnisend"
        subtitle="Push leads into Omnisend with this campaign's tag so they enter the journey. This makes a real Omnisend API call."
      />
      <div className="mt-4 flex flex-col gap-3">
        <Input label="Tag" value={tag} onChange={setTag} placeholder="solo_ads_vendorx_q3" />
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-500">Emails (one per line or comma-separated)</span>
          <textarea
            value={emails}
            onChange={(e) => setEmails(e.target.value)}
            rows={4}
            placeholder={"jane@example.com\njohn@example.com"}
            className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
      </div>
      {sync.data ? (
        <div className="mt-3 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">
          Tagged {sync.data.succeeded}/{sync.data.requested} contacts with “{sync.data.tag}”.
          {sync.data.failed > 0 ? ` ${sync.data.failed} failed.` : ""}
        </div>
      ) : null}
      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}{" "}
          {notConnected ? <Link className="underline" to="/autoresponders">Connect Omnisend →</Link> : null}
        </div>
      ) : null}
      <div className="mt-4">
        <Button onClick={() => sync.mutate()} disabled={sync.isPending || !tag.trim() || !emails.includes("@")}>
          {sync.isPending ? "Tagging…" : "Tag contacts in Omnisend"}
        </Button>
      </div>
    </Card>
  );
}

function Meta({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd className="text-slate-700">{value ?? "—"}</dd>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-slate-500">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn("rounded-xl border border-slate-200 bg-surface px-3 py-2 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200")}
      />
    </label>
  );
}
