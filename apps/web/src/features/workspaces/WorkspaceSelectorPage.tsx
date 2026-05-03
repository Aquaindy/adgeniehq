import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api-client";
import { logoutRequest } from "@/lib/auth";
import { createWorkspace, listWorkspaces } from "@/lib/workspaces";
import { useAuthStore } from "@/stores/auth-store";
import { useWorkspaceStore } from "@/stores/workspace-store";

export function WorkspaceSelectorPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setCurrent = useWorkspaceStore((s) => s.setCurrentWorkspaceId);
  const clearAuth = useAuthStore((s) => s.clear);

  const memberships = useQuery({
    queryKey: ["workspaces"],
    queryFn: listWorkspaces,
  });

  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: createWorkspace,
    onSuccess: (workspace) => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      setCurrent(workspace.id);
      navigate("/", { replace: true });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not create workspace.");
    },
  });

  // If there's exactly one workspace and nothing selected yet, auto-pick it.
  useEffect(() => {
    if (!memberships.data) return;
    if (memberships.data.length === 1 && !useWorkspaceStore.getState().currentWorkspaceId) {
      setCurrent(memberships.data[0]!.id);
      navigate("/", { replace: true });
    }
  }, [memberships.data, navigate, setCurrent]);

  function onSelect(id: string) {
    setCurrent(id);
    navigate("/", { replace: true });
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (name.trim().length < 2) {
      setError("Workspace name must be at least 2 characters.");
      return;
    }
    setError(null);
    create.mutate({ name: name.trim() });
  }

  async function onSignOut() {
    try {
      await logoutRequest();
    } catch {
      // ignore — we always clear local state
    }
    clearAuth();
    setCurrent(null);
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-grape-soft">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-10 sm:px-6 sm:py-14">
        <header className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-grape-700">Workspaces</p>
            <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
              Pick a workspace to enter
            </h1>
            <p className="mt-2 text-sm text-slate-500">
              Each workspace has its own connected accounts, agents, and reports.
            </p>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            className="text-sm font-medium text-slate-500 hover:text-ink"
          >
            Sign out
          </button>
        </header>

        <section>
          {memberships.isLoading ? (
            <Card>Loading…</Card>
          ) : memberships.data && memberships.data.length > 0 ? (
            <div className="flex flex-col gap-3">
              {memberships.data.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => onSelect(m.id)}
                  className="card flex items-center justify-between gap-4 px-5 py-4 text-left transition hover:border-grape-200 hover:shadow-elevate"
                >
                  <div>
                    <div className="font-semibold text-ink">{m.name}</div>
                    <div className="text-xs text-slate-500">advanta.ai/{m.slug}</div>
                  </div>
                  <span className="pill pill-grape">{m.role}</span>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No workspaces yet"
              description="Create a workspace to set up your first business and start onboarding."
            />
          )}
        </section>

        <Card>
          <CardHeader title="Create a new workspace" subtitle="You'll be the Owner." />
          <form className="mt-4 flex flex-col gap-3 sm:flex-row" onSubmit={onSubmit} noValidate>
            <input
              type="text"
              placeholder="e.g. Acme Marketing"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create workspace"}
            </Button>
          </form>
          {error ? (
            <p className="mt-2 text-sm text-red-700" role="alert">
              {error}
            </p>
          ) : null}
        </Card>
      </div>
    </div>
  );
}
