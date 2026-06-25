import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  disconnectIntegration,
  getConnectUrl,
  listIntegrations,
  syncIntegration,
} from "@/lib/integrations";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type { ConnectionStatus, IntegrationStatus } from "@/types/api";

export function IntegrationsPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [callbackBanner, setCallbackBanner] = useState<{
    kind: "success" | "error";
    text: string;
  } | null>(null);

  const integrations = useQuery({
    queryKey: ["integrations", workspaceId],
    queryFn: () => listIntegrations(workspaceId!),
    enabled: !!workspaceId,
  });

  // Read OAuth callback redirect params and show a banner once.
  useEffect(() => {
    const status = searchParams.get("status");
    const provider = searchParams.get("provider");
    const message = searchParams.get("message");
    if (!status || !provider) return;

    setCallbackBanner({
      kind: status === "success" ? "success" : "error",
      text:
        status === "success"
          ? `${provider} connected successfully.`
          : `${provider} connection failed${message ? `: ${message}` : "."}`,
    });
    queryClient.invalidateQueries({ queryKey: ["integrations", workspaceId] });

    // Strip the params so a refresh doesn't re-show the toast.
    const next = new URLSearchParams(searchParams);
    next.delete("status");
    next.delete("provider");
    next.delete("message");
    next.delete("workspace_id");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams, queryClient, workspaceId]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink sm:text-3xl">Connect real accounts</h1>
        <p className="mt-2 text-sm text-slate-500">
          OAuth tokens are encrypted at rest with Fernet. Connecting requires the workspace Admin
          role.
        </p>
      </header>

      {callbackBanner ? (
        <div
          className={cn(
            "rounded-xl px-4 py-3 text-sm",
            callbackBanner.kind === "success"
              ? "bg-emerald-50 text-emerald-700"
              : "bg-red-50 text-red-700",
          )}
          role="status"
        >
          {callbackBanner.text}
        </div>
      ) : null}

      {integrations.isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {integrations.data?.map((entry) => (
            <IntegrationCard key={entry.provider} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}

function IntegrationCard({ entry }: { entry: IntegrationStatus }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  // Default to requesting write access so users can run/manage ads; they can
  // opt down to read-only (analytics + recommendations) before connecting.
  const [enableWrite, setEnableWrite] = useState(true);
  const supportsWrite = entry.write_scopes.length > 0;

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["integrations", workspaceId] });
  }

  const connect = useMutation({
    mutationFn: () =>
      getConnectUrl(workspaceId!, entry.provider, enableWrite ? "write" : "read"),
    onSuccess: (resp) => {
      // Hand off to the provider's OAuth screen
      window.location.href = resp.authorization_url;
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "provider_not_configured") {
        setError(err.message);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not start connection.");
      }
    },
  });

  const disconnect = useMutation({
    mutationFn: () => disconnectIntegration(workspaceId!, entry.provider),
    onSuccess: () => invalidate(),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not disconnect."),
  });

  const sync = useMutation({
    mutationFn: () => syncIntegration(workspaceId!, entry.provider),
    onSuccess: () => invalidate(),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Sync failed."),
  });

  const busy = connect.isPending || disconnect.isPending || sync.isPending;

  return (
    <Card>
      <CardHeader
        title={entry.display_name}
        subtitle={entry.description}
        action={<StatusPill status={entry.status} />}
      />
      <dl className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <div>
          <dt className="text-slate-400">OAuth app</dt>
          <dd className={cn("font-medium", entry.configured ? "text-ink" : "text-amber-700")}>
            {entry.configured ? "Configured" : "Not configured"}
          </dd>
        </div>
        <div>
          <dt className="text-slate-400">Account</dt>
          <dd className="font-medium text-ink">
            {entry.display_account_name ?? entry.provider_account_id ?? "—"}
          </dd>
        </div>
        <div>
          <dt className="text-slate-400">Connected</dt>
          <dd className="font-medium text-ink">
            {entry.connected_at ? new Date(entry.connected_at).toLocaleString() : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-slate-400">Last sync</dt>
          <dd className="font-medium text-ink">
            {entry.last_sync_at ? new Date(entry.last_sync_at).toLocaleString() : "—"}
          </dd>
        </div>
        {supportsWrite ? (
          <div>
            <dt className="text-slate-400">Write access</dt>
            <dd
              className={cn(
                "font-medium",
                entry.status !== "connected"
                  ? "text-slate-500"
                  : entry.can_write
                    ? "text-emerald-700"
                    : "text-amber-700",
              )}
            >
              {entry.status !== "connected"
                ? "—"
                : entry.can_write
                  ? "Run & manage ads"
                  : "Read-only"}
            </dd>
          </div>
        ) : null}
      </dl>

      {entry.last_error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
          Last error: {entry.last_error}
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {error}
        </div>
      ) : null}

      {entry.status !== "connected" && supportsWrite ? (
        <label className="mt-4 flex items-center gap-2 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={enableWrite}
            onChange={(e) => setEnableWrite(e.target.checked)}
          />
          Enable write access — lets AdVanta run &amp; manage ads (not just read
          analytics). You can reconnect to change this later.
        </label>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {entry.status === "connected" ? (
          <>
            <Button onClick={() => sync.mutate()} disabled={busy}>
              {sync.isPending ? "Syncing…" : "Sync now"}
            </Button>
            {supportsWrite && !entry.can_write ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setEnableWrite(true);
                  connect.mutate();
                }}
                disabled={busy}
              >
                {connect.isPending ? "Opening…" : "Grant write access"}
              </Button>
            ) : null}
            <Button variant="ghost" onClick={() => disconnect.mutate()} disabled={busy}>
              {disconnect.isPending ? "Disconnecting…" : "Disconnect"}
            </Button>
          </>
        ) : (
          <Button
            onClick={() => connect.mutate()}
            disabled={busy}
            variant={entry.configured ? "primary" : "secondary"}
          >
            {connect.isPending ? "Opening…" : "Connect"}
          </Button>
        )}
      </div>

      {entry.recent_syncs.length > 0 ? (
        <details className="mt-4 text-xs text-slate-500">
          <summary className="cursor-pointer select-none font-medium text-slate-text">
            Recent syncs · {entry.recent_syncs.length}
          </summary>
          <ul className="mt-2 flex flex-col gap-1">
            {entry.recent_syncs.map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-1.5"
              >
                <span>
                  <span
                    className={cn(
                      "pill",
                      s.status === "succeeded" && "pill-success",
                      s.status === "failed" && "pill-danger",
                      s.status === "running" && "pill-grape",
                    )}
                  >
                    {s.status}
                  </span>
                  <span className="ml-2 text-slate-500">
                    {new Date(s.started_at).toLocaleString()}
                  </span>
                </span>
                {s.error_message ? (
                  <span className="text-red-700">{s.error_message.slice(0, 80)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </Card>
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
