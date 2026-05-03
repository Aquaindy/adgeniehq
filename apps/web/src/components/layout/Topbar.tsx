import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Logomark } from "@/components/Logomark";
import { AdminBadge } from "@/components/layout/AdminBadge";
import { PlanBadge } from "@/components/layout/PlanBadge";
import { APP_NAME } from "@/lib/constants";
import { logoutRequest } from "@/lib/auth";
import { listWorkspaces } from "@/lib/workspaces";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import { useWorkspaceStore } from "@/stores/workspace-store";

function useOutsideClose(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);
  return ref;
}

export function Topbar() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clear);
  const currentId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const setCurrent = useWorkspaceStore((s) => s.setCurrentWorkspaceId);

  const [wsOpen, setWsOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);

  const wsRef = useOutsideClose(() => setWsOpen(false));
  const userRef = useOutsideClose(() => setUserOpen(false));

  const memberships = useQuery({
    queryKey: ["workspaces"],
    queryFn: listWorkspaces,
    enabled: !!user,
  });

  const current = memberships.data?.find((m) => m.id === currentId) ?? null;

  async function onSignOut() {
    setUserOpen(false);
    try {
      await logoutRequest();
    } catch {
      // ignore
    }
    clearAuth();
    setCurrent(null);
    navigate("/login", { replace: true });
  }

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur sm:px-6 lg:h-16">
      <div className="flex items-center gap-3 lg:hidden">
        <Logomark />
        <span className="text-sm font-semibold text-ink">{APP_NAME}</span>
      </div>

      <div ref={wsRef} className="relative hidden lg:block">
        <button
          type="button"
          onClick={() => setWsOpen((v) => !v)}
          className="flex items-center gap-3 rounded-xl px-2 py-1.5 text-left transition hover:bg-slate-100"
        >
          <div>
            <div className="text-xs uppercase tracking-wider text-slate-400">Workspace</div>
            <div className="text-sm font-semibold text-ink">
              {current ? current.name : "Select a workspace"}
            </div>
          </div>
          <span aria-hidden className="text-slate-400">▾</span>
        </button>
        {wsOpen ? (
          <div className="absolute left-0 top-full z-40 mt-1 w-72 rounded-xl border border-slate-100 bg-white py-1 shadow-elevate">
            {memberships.data?.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  setCurrent(m.id);
                  setWsOpen(false);
                }}
                className={cn(
                  "flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition hover:bg-grape-50",
                  m.id === currentId && "bg-grape-50",
                )}
              >
                <span>
                  <span className="block font-medium text-ink">{m.name}</span>
                  <span className="block text-xs text-slate-500">advanta.ai/{m.slug}</span>
                </span>
                <span className="pill pill-grape">{m.role}</span>
              </button>
            ))}
            <Link
              to="/workspaces"
              onClick={() => setWsOpen(false)}
              className="block border-t border-slate-100 px-3 py-2 text-sm font-medium text-grape-700 hover:bg-grape-50"
            >
              + New workspace
            </Link>
          </div>
        ) : null}
      </div>

      <div ref={userRef} className="relative flex items-center gap-3">
        <AdminBadge />
        <PlanBadge />
        <button
          type="button"
          onClick={() => setUserOpen((v) => !v)}
          className="flex size-9 items-center justify-center rounded-full bg-grape text-sm font-semibold text-white shadow-sm hover:bg-grape-800"
          aria-label="Account menu"
        >
          {(user?.full_name ?? user?.email ?? "?").slice(0, 1).toUpperCase()}
        </button>
        {userOpen ? (
          <div className="absolute right-0 top-full z-40 mt-1 w-60 rounded-xl border border-slate-100 bg-white py-1 shadow-elevate">
            <div className="border-b border-slate-100 px-3 py-2">
              <div className="text-sm font-medium text-ink">{user?.full_name ?? "—"}</div>
              <div className="truncate text-xs text-slate-500">{user?.email}</div>
            </div>
            <Link
              to="/settings/profile"
              onClick={() => setUserOpen(false)}
              className="block px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
            >
              Profile
            </Link>
            <Link
              to="/workspaces"
              onClick={() => setUserOpen(false)}
              className="block px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
            >
              Switch workspace
            </Link>
            <button
              type="button"
              onClick={onSignOut}
              className="block w-full border-t border-slate-100 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100"
            >
              Sign out
            </button>
          </div>
        ) : null}
      </div>
    </header>
  );
}
