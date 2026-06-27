import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError, apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { Role } from "@/types/api";
import { useWorkspaceStore } from "@/stores/workspace-store";

type ApiKey = {
  id: string;
  label: string;
  prefix: string;
  role: Role;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

type ApiKeyCreated = ApiKey & { plaintext_key: string };

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "marketer", label: "Marketer (default)" },
  { value: "admin", label: "Admin (can approve recommendations)" },
  { value: "analyst", label: "Analyst (read-only insights)" },
  { value: "viewer", label: "Viewer (dashboards only)" },
];


/**
 * Workspace API keys — outbound. External clients use these to call the
 * AdGenieHQ API on this workspace's behalf via
 * `Authorization: ApiKey ak_…`. Plaintext is shown exactly once at
 * creation.
 */
export function WorkspaceApiKeysPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  if (!workspaceId) {
    return <div className="text-sm text-slate-500">Select a workspace first.</div>;
  }
  return <WorkspaceApiKeysInner workspaceId={workspaceId} />;
}


function WorkspaceApiKeysInner({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient();
  const [justMinted, setJustMinted] = useState<ApiKeyCreated | null>(null);
  const [label, setLabel] = useState("");
  const [role, setRole] = useState<Role>("marketer");
  const [error, setError] = useState<string | null>(null);

  const list = useQuery<ApiKey[]>({
    queryKey: ["api-keys", workspaceId],
    queryFn: () => apiFetch(`/workspaces/${workspaceId}/api-keys`),
  });

  const create = useMutation({
    mutationFn: async () =>
      apiFetch<ApiKeyCreated>(
        `/workspaces/${workspaceId}/api-keys`,
        { method: "POST", body: { label, role } },
      ),
    onSuccess: (created) => {
      setJustMinted(created);
      setLabel("");
      setRole("marketer");
      void queryClient.invalidateQueries({ queryKey: ["api-keys", workspaceId] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not mint key.");
    },
  });

  const revoke = useMutation({
    mutationFn: async (id: string) =>
      apiFetch<ApiKey>(
        `/workspaces/${workspaceId}/api-keys/${id}/revoke`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["api-keys", workspaceId] });
    },
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!label.trim()) {
      setError("Give the key a label so future-you can find it.");
      return;
    }
    create.mutate();
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader
          title="Mint a new key"
          subtitle={
            <>
              Programmatic access via{" "}
              <code className="text-xs">Authorization: ApiKey ak_…</code>.
              Owner-only. Plaintext is shown exactly once.
            </>
          }
        />
        <form className="mt-3 flex flex-col gap-3" onSubmit={onSubmit} noValidate>
          <label className="flex flex-col gap-1.5 text-sm" htmlFor="api-key-label">
            <span className="font-medium text-slate-text">Label</span>
            <input
              id="api-key-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="ci-ingest, zapier, etc."
              required
              className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm" htmlFor="api-key-role">
            <span className="font-medium text-slate-text">Role</span>
            <select
              id="api-key-role"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            >
              {ROLE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          {error ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </div>
          ) : null}
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Minting…" : "Mint key"}
          </Button>
        </form>

        {justMinted ? (
          <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm">
            <div className="font-medium text-amber-900">Copy this now.</div>
            <p className="mt-1 text-amber-900/80">
              We hash the secret at rest — refreshing this page won't show it
              again.
            </p>
            <code className="mt-2 block break-all rounded-lg bg-surface px-2 py-1 font-mono text-xs text-ink">
              {justMinted.plaintext_key}
            </code>
            <Button
              variant="secondary"
              onClick={() => setJustMinted(null)}
              className="mt-3"
            >
              I've saved it
            </Button>
          </div>
        ) : null}
      </Card>

      <Card>
        <CardHeader title="Existing keys" />
        {list.isLoading ? (
          <p className="mt-3 text-sm text-slate-400">Loading…</p>
        ) : (list.data ?? []).length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">No keys yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-xs uppercase tracking-wider text-slate-400">
                  <th className="px-3 py-2">Label</th>
                  <th className="px-3 py-2">Prefix</th>
                  <th className="px-3 py-2">Role</th>
                  <th className="px-3 py-2">Last used</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(list.data ?? []).map((k) => (
                  <tr key={k.id}>
                    <td className="px-3 py-2 text-ink">{k.label}</td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-500">
                      ak_{k.prefix}
                    </td>
                    <td className="px-3 py-2 text-slate-700">{k.role}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {k.last_used_at
                        ? new Date(k.last_used_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={cn(
                          "pill",
                          k.revoked_at ? "pill-danger" : "pill-success",
                        )}
                      >
                        {k.revoked_at ? "revoked" : "active"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {k.revoked_at ? null : (
                        <Button
                          variant="secondary"
                          onClick={() => revoke.mutate(k.id)}
                          disabled={
                            revoke.isPending && revoke.variables === k.id
                          }
                        >
                          Revoke
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
