import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Outlet } from "react-router-dom";

import { listWorkspaces } from "@/lib/workspaces";
import { useWorkspaceStore } from "@/stores/workspace-store";

/** Ensures the user has selected a workspace they belong to. If not, redirects
 *  to the workspace selector. */
export function RequireWorkspace() {
  const currentId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const setCurrent = useWorkspaceStore((s) => s.setCurrentWorkspaceId);

  const memberships = useQuery({
    queryKey: ["workspaces"],
    queryFn: listWorkspaces,
  });

  // Reconcile the stored workspace with what the API actually returns.
  useEffect(() => {
    if (!memberships.data) return;
    if (memberships.data.length === 0) {
      if (currentId !== null) setCurrent(null);
      return;
    }
    const exists = currentId && memberships.data.some((m) => m.id === currentId);
    if (!exists) {
      setCurrent(memberships.data[0]!.id);
    }
  }, [memberships.data, currentId, setCurrent]);

  if (memberships.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-400">
        Loading workspaces…
      </div>
    );
  }

  if (!memberships.data || memberships.data.length === 0) {
    return <Navigate to="/workspaces" replace />;
  }

  return <Outlet />;
}
