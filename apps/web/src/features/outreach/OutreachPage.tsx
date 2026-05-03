import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { UsageMeter } from "@/components/UsageMeter";
import { ApiError } from "@/lib/api-client";
import { createProspect, listProspects } from "@/lib/outreach";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { ProspectStatus } from "@/types/api";

const STATUS_PILL: Record<ProspectStatus, string> = {
  new: "bg-slate-100 text-slate-600",
  queued: "bg-slate-100 text-slate-600",
  contacted: "pill-grape",
  replied: "bg-amber-100 text-amber-700",
  won: "pill-success",
  declined: "bg-slate-100 text-slate-500",
  bounced: "pill-danger",
  archived: "bg-slate-100 text-slate-400",
};

export function OutreachPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const prospects = useQuery({
    queryKey: ["backlink-prospects", workspaceId],
    queryFn: () => listProspects(workspaceId!),
    enabled: !!workspaceId,
  });

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Outreach</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          Backlink prospects
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Track sites we want backlinks from. Drafted outreach emails never
          auto-send — an Admin must approve, and the SMTP transport is the only
          path that actually reaches the recipient.
        </p>
      </header>

      <UsageMeter resource="outreach_emails" />

      <AddProspectForm />

      {prospects.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : prospects.error ? (
        <Card>
          <p className="text-sm text-red-700">
            {prospects.error instanceof Error
              ? prospects.error.message
              : "Could not load prospects."}
          </p>
        </Card>
      ) : prospects.data && prospects.data.length === 0 ? (
        <EmptyState
          title="No prospects yet"
          description="Add a domain above to start tracking link partners."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {prospects.data?.map((p) => (
            <li key={p.id}>
              <Link
                to={`/outreach/${p.id}`}
                className="card flex items-center justify-between gap-3 p-4 transition hover:bg-grape-50"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className={cn("pill", STATUS_PILL[p.status])}>
                      {p.status}
                    </span>
                    <h3 className="text-sm font-semibold text-ink">{p.domain}</h3>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {p.contact_name ? `${p.contact_name}` : "No contact yet"}
                    {p.contact_email ? ` · ${p.contact_email}` : ""}
                    {p.last_contacted_at
                      ? ` · last contacted ${new Date(p.last_contacted_at).toLocaleDateString()}`
                      : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  {p.relevance_score != null ? (
                    <span className="pill bg-grape-50 text-grape-700">
                      relevance {p.relevance_score}
                    </span>
                  ) : null}
                  {p.domain_authority != null ? (
                    <span className="pill bg-slate-50 text-slate-500">
                      DA {p.domain_authority}
                    </span>
                  ) : null}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AddProspectForm() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [domain, setDomain] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: () =>
      createProspect(workspaceId!, {
        domain,
        contact_name: contactName || null,
        contact_email: contactEmail || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["backlink-prospects", workspaceId],
      });
      setDomain("");
      setContactName("");
      setContactEmail("");
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not add."),
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!domain.trim()) {
      setError("Provide a domain to track.");
      return;
    }
    mut.mutate();
  }

  return (
    <Card>
      <CardHeader title="Add a prospect" />
      <form className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3" onSubmit={onSubmit}>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-text">Domain</span>
          <input
            type="text"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="techcrunch.com"
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-text">Contact name (optional)</span>
          <input
            type="text"
            value={contactName}
            onChange={(e) => setContactName(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-slate-text">Contact email (optional)</span>
          <input
            type="email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        {error ? (
          <div className="sm:col-span-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        ) : null}
        <div className="sm:col-span-3">
          <Button type="submit" disabled={mut.isPending}>
            {mut.isPending ? "Adding…" : "Add prospect"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
