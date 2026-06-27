import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api-client";
import {
  connectAutoresponder,
  disconnectAutoresponder,
  getAutoresponderCatalog,
  listAudiences,
  listAutoresponderActivity,
  listAutoresponders,
  pullContacts,
  pushContacts,
} from "@/lib/autoresponders";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  AutoresponderConnection,
  AutoresponderProviderInfo,
  ConnectionStatus,
  ContactInput,
  ContactPublic,
  ContactSync,
} from "@/types/api";

const inputClass =
  "w-full rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200";

export function AutorespondersPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);

  const catalog = useQuery({
    queryKey: ["autoresponders", workspaceId, "catalog"],
    queryFn: () => getAutoresponderCatalog(workspaceId!),
    enabled: !!workspaceId,
  });

  const connections = useQuery({
    queryKey: ["autoresponders", workspaceId, "connections"],
    queryFn: () => listAutoresponders(workspaceId!),
    enabled: !!workspaceId,
  });

  const connByProvider = useMemo(() => {
    const map: Record<string, AutoresponderConnection> = {};
    for (const c of connections.data ?? []) map[c.provider] = c;
    return map;
  }, [connections.data]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-wider text-grape-700">Autoresponders</p>
        <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
          Email &amp; SMS audiences
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Connect your autoresponder, then sync contacts both ways — push ad leads into
          your lists and pull subscribers back into AdGenieHQ. API keys are encrypted at rest;
          connecting requires the workspace Admin role.
        </p>
      </header>

      {catalog.isLoading || connections.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {catalog.data?.map((provider) => (
            <ProviderCard
              key={provider.provider}
              provider={provider}
              connection={connByProvider[provider.provider] ?? null}
            />
          ))}
        </div>
      )}

      <ActivityFeed />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Provider card — connect form (disconnected) or sync panel (connected)
// ---------------------------------------------------------------------------

function ProviderCard({
  provider,
  connection,
}: {
  provider: AutoresponderProviderInfo;
  connection: AutoresponderConnection | null;
}) {
  const connected = connection?.status === "connected";
  return (
    <Card>
      <CardHeader
        title={provider.display_name}
        subtitle={provider.description}
        action={<StatusPill status={connection?.status ?? "disconnected"} />}
      />

      {connection?.last_error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
          {connection.last_error}
        </div>
      ) : null}

      {connected ? (
        <ConnectedPanel provider={provider} connection={connection!} />
      ) : (
        <ConnectForm provider={provider} />
      )}
    </Card>
  );
}

function ConnectForm({ provider }: { provider: AutoresponderProviderInfo }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const connect = useMutation({
    mutationFn: () =>
      connectAutoresponder(workspaceId!, provider.provider, {
        api_key: apiKey || null,
        config,
      }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["autoresponders", workspaceId] });
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not connect."),
  });

  return (
    <form
      className="mt-4 flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        connect.mutate();
      }}
    >
      {provider.requires_api_key || provider.provider === "custom" ? (
        <Field label={provider.api_key_label} help={provider.api_key_help}>
          <input
            type="password"
            className={inputClass}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="••••••••"
            autoComplete="off"
          />
        </Field>
      ) : null}

      {provider.config_fields.map((f) => (
        <Field key={f.key} label={f.label + (f.required ? "" : " (optional)")} help={f.help_text}>
          <input
            type={f.type === "password" ? "password" : "text"}
            className={inputClass}
            value={config[f.key] ?? ""}
            placeholder={f.placeholder ?? ""}
            onChange={(e) =>
              setConfig((prev) => ({ ...prev, [f.key]: e.target.value }))
            }
          />
        </Field>
      ))}

      {error ? (
        <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{error}</div>
      ) : null}

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={connect.isPending}>
          {connect.isPending ? "Connecting…" : "Connect"}
        </Button>
        {provider.docs_url ? (
          <a
            className="text-xs text-grape-700 underline"
            href={provider.docs_url}
            target="_blank"
            rel="noreferrer"
          >
            API docs →
          </a>
        ) : null}
      </div>
    </form>
  );
}

function ConnectedPanel({
  provider,
  connection,
}: {
  provider: AutoresponderProviderInfo;
  connection: AutoresponderConnection;
}) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();

  const disconnect = useMutation({
    mutationFn: () => disconnectAutoresponder(workspaceId!, provider.provider),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["autoresponders", workspaceId] }),
  });

  return (
    <div className="mt-3 flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <dt className="text-slate-400">Account</dt>
          <dd className="font-medium text-ink">{connection.display_name ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-slate-400">Last sync</dt>
          <dd className="font-medium text-ink">
            {connection.last_sync_at
              ? new Date(connection.last_sync_at).toLocaleString()
              : "—"}
          </dd>
        </div>
      </dl>

      <ContactSyncPanel provider={provider} />

      <div>
        <Button variant="ghost" onClick={() => disconnect.mutate()} disabled={disconnect.isPending}>
          {disconnect.isPending ? "Disconnecting…" : "Disconnect"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Contact sync — both directions
// ---------------------------------------------------------------------------

function parseContacts(raw: string): ContactInput[] {
  return raw
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      const [email, first, last] = line.split(",").map((s) => s.trim());
      return { email, first_name: first || null, last_name: last || null };
    })
    .filter((c) => c.email);
}

function ContactSyncPanel({ provider }: { provider: AutoresponderProviderInfo }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [audienceId, setAudienceId] = useState("");
  const [raw, setRaw] = useState("");
  const [pulled, setPulled] = useState<ContactPublic[] | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const audiences = useQuery({
    queryKey: ["autoresponders", workspaceId, provider.provider, "audiences"],
    queryFn: () => listAudiences(workspaceId!, provider.provider),
    enabled: !!workspaceId && provider.supports_audience_listing,
  });

  function afterSync() {
    queryClient.invalidateQueries({ queryKey: ["autoresponders", workspaceId, "activity"] });
    queryClient.invalidateQueries({ queryKey: ["autoresponders", workspaceId, "connections"] });
  }

  const push = useMutation({
    mutationFn: () => {
      const contacts = parseContacts(raw);
      if (contacts.length === 0) throw new ApiError("Add at least one email.", { status: 400 });
      return pushContacts(workspaceId!, provider.provider, {
        audience_id: audienceId || null,
        source: "manual",
        contacts,
      });
    },
    onSuccess: (sync: ContactSync) => {
      setNotice({
        kind: sync.status === "failed" ? "err" : "ok",
        text: `Pushed ${sync.succeeded_count}/${sync.requested_count} contacts (${sync.status}).`,
      });
      setRaw("");
      afterSync();
    },
    onError: (err) =>
      setNotice({ kind: "err", text: err instanceof ApiError ? err.message : "Push failed." }),
  });

  const pull = useMutation({
    mutationFn: () =>
      pullContacts(workspaceId!, provider.provider, {
        audience_id: audienceId || null,
        limit: 100,
      }),
    onSuccess: (resp) => {
      setPulled(resp.contacts);
      setNotice({ kind: "ok", text: `Pulled ${resp.contacts.length} contacts.` });
      afterSync();
    },
    onError: (err) =>
      setNotice({ kind: "err", text: err instanceof ApiError ? err.message : "Pull failed." }),
  });

  const audienceLabel = provider.freeform_audience
    ? provider.provider === "omnisend"
      ? "Tag"
      : "List / tag"
    : "List";

  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-4">
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        Sync contacts
      </div>

      <div className="mt-3">
        <Field
          label={audienceLabel}
          help={
            provider.freeform_audience
              ? "Free-text — contacts are tagged/assigned with this value."
              : undefined
          }
        >
          {provider.supports_audience_listing ? (
            <select
              className={inputClass}
              value={audienceId}
              onChange={(e) => setAudienceId(e.target.value)}
            >
              <option value="">Select a list…</option>
              {audiences.data?.audiences.map((a) => (
                <option key={a.external_id} value={a.external_id}>
                  {a.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              className={inputClass}
              value={audienceId}
              onChange={(e) => setAudienceId(e.target.value)}
              placeholder={provider.provider === "omnisend" ? "leads" : "list-id"}
            />
          )}
        </Field>
      </div>

      {/* Push */}
      <div className="mt-3">
        <Field
          label="Contacts to push"
          help="One per line — email[, first name[, last name]]."
        >
          <textarea
            className={cn(inputClass, "min-h-[72px] font-mono text-xs")}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder={"jane@acme.com, Jane, Doe\njohn@acme.com"}
          />
        </Field>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button onClick={() => push.mutate()} disabled={push.isPending}>
            {push.isPending ? "Pushing…" : "Push to list"}
          </Button>
          {provider.supports_contact_pull ? (
            <Button variant="secondary" onClick={() => pull.mutate()} disabled={pull.isPending}>
              {pull.isPending ? "Pulling…" : "Pull from list"}
            </Button>
          ) : null}
        </div>
      </div>

      {notice ? (
        <div
          className={cn(
            "mt-3 rounded-lg px-3 py-2 text-xs",
            notice.kind === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700",
          )}
        >
          {notice.text}
        </div>
      ) : null}

      {pulled && pulled.length > 0 ? (
        <details className="mt-3 text-xs text-slate-500" open>
          <summary className="cursor-pointer select-none font-medium text-slate-text">
            Pulled contacts · {pulled.length}
          </summary>
          <ul className="mt-2 flex max-h-48 flex-col gap-1 overflow-y-auto">
            {pulled.map((c, i) => (
              <li key={`${c.email}-${i}`} className="rounded-lg border border-slate-100 bg-surface px-3 py-1.5">
                <span className="font-medium text-ink">{c.email ?? c.phone ?? "—"}</span>
                {c.first_name || c.last_name ? (
                  <span className="ml-2 text-slate-500">
                    {[c.first_name, c.last_name].filter(Boolean).join(" ")}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Activity feed
// ---------------------------------------------------------------------------

function ActivityFeed() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const activity = useQuery({
    queryKey: ["autoresponders", workspaceId, "activity"],
    queryFn: () => listAutoresponderActivity(workspaceId!),
    enabled: !!workspaceId,
  });

  if (activity.isLoading) return null;
  const items = activity.data ?? [];

  return (
    <Card>
      <CardHeader title="Recent contact syncs" subtitle="Every push and pull is logged and audited." />
      {items.length === 0 ? (
        <EmptyState
          title="No syncs yet"
          description="Connect an autoresponder and push or pull contacts to see activity here."
        />
      ) : (
        <ul className="mt-3 flex flex-col divide-y divide-slate-100">
          {items.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "pill",
                    s.direction === "push" ? "pill-grape" : "bg-slate-100 text-slate-600",
                  )}
                >
                  {s.direction}
                </span>
                <span className="text-sm text-ink">
                  {s.succeeded_count}/{s.requested_count}
                  {s.audience_name || s.audience_external_id
                    ? ` · ${s.audience_name ?? s.audience_external_id}`
                    : ""}
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <SyncStatusPill status={s.status} />
                <span>{new Date(s.created_at).toLocaleString()}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Small bits
// ---------------------------------------------------------------------------

function Field({
  label,
  help,
  children,
}: {
  label: string;
  help?: string | null;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-slate-text">{label}</span>
      {children}
      {help ? <span className="text-xs text-slate-400">{help}</span> : null}
    </label>
  );
}

function StatusPill({ status }: { status: ConnectionStatus }) {
  return (
    <span
      className={cn(
        "pill",
        status === "connected" && "pill-success",
        status === "error" && "pill-danger",
        status === "disconnected" && "bg-slate-100 text-slate-600",
      )}
    >
      {status}
    </span>
  );
}

function SyncStatusPill({ status }: { status: ContactSync["status"] }) {
  return (
    <span
      className={cn(
        "pill",
        status === "succeeded" && "pill-success",
        status === "partial" && "pill-warning",
        status === "failed" && "pill-danger",
        status === "running" && "pill-grape",
      )}
    >
      {status}
    </span>
  );
}
