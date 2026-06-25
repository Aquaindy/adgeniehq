import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { Logomark } from "@/components/Logomark";
import { listWorkspaces } from "@/lib/workspaces";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import { useWorkspaceStore } from "@/stores/workspace-store";

const COLLAPSE_STORAGE_KEY = "advanta.sidebar.collapsed";

type NavItem = {
  to: string;
  label: string;
};

type NavGroup = {
  heading: string;
  items: NavItem[];
};

const navGroups: NavGroup[] = [
  {
    heading: "Overview",
    items: [
      { to: "/", label: "Command Center" },
      { to: "/growth-dna", label: "Growth DNA" },
    ],
  },
  {
    heading: "Agents & Automation",
    items: [
      { to: "/agents", label: "Agents" },
      { to: "/recommendations", label: "Recommendations" },
      { to: "/autopilot", label: "Autopilot" },
    ],
  },
  {
    heading: "Advertising",
    items: [
      { to: "/campaigns", label: "Campaigns" },
      { to: "/creatives", label: "Creatives" },
      { to: "/autoresponders", label: "Autoresponders" },
    ],
  },
  {
    heading: "SEO & Content",
    items: [
      { to: "/seo", label: "SEO & GEO" },
      { to: "/content", label: "Content" },
      { to: "/blog/posts", label: "Blog" },
      { to: "/outreach", label: "Outreach" },
    ],
  },
  {
    heading: "Conversion & Insights",
    items: [
      { to: "/website", label: "Website" },
      { to: "/ab-tests", label: "A/B tests" },
      { to: "/reports", label: "Reports" },
    ],
  },
  {
    heading: "Workspace",
    items: [
      { to: "/onboarding", label: "Onboarding" },
      { to: "/settings", label: "Settings" },
    ],
  },
];

const SUPERUSER_GROUP: NavGroup = {
  heading: "Admin",
  items: [{ to: "/admin", label: "Admin" }],
};

function navLinkClasses({ isActive }: { isActive: boolean }) {
  return cn(
    "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition",
    isActive
      ? "bg-white/15 text-white shadow-sm"
      : "text-white/70 hover:bg-white/10 hover:text-white",
  );
}

function isGroupActive(group: NavGroup, pathname: string): boolean {
  return group.items.some((item) =>
    item.to === "/" ? pathname === "/" : pathname.startsWith(item.to),
  );
}

function loadCollapsed(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(COLLAPSE_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 12 12"
      className={cn(
        "size-3 shrink-0 text-white/40 transition-transform duration-200",
        open ? "rotate-0" : "-rotate-90",
      )}
    >
      <path
        d="M2.5 4.5L6 8l3.5-3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const currentId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const memberships = useQuery({
    queryKey: ["workspaces"],
    queryFn: listWorkspaces,
    enabled: !!user,
  });
  const current = memberships.data?.find((m) => m.id === currentId) ?? null;
  const { pathname } = useLocation();

  const groups = user?.is_superuser
    ? [...navGroups, SUPERUSER_GROUP]
    : navGroups;

  // Per-group collapsed state, persisted. Default open; a group is force-open
  // while it contains the active route so the current page is always visible.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(loadCollapsed);

  const toggle = (heading: string) =>
    setCollapsed((prev) => {
      const next = { ...prev, [heading]: !prev[heading] };
      try {
        localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });

  return (
    <aside className="hidden h-screen w-64 shrink-0 flex-col border-r border-white/10 bg-grape-gradient text-white lg:flex">
      <div className="flex h-16 items-center gap-2 px-5 border-b border-white/10">
        <Logomark />
        <div>
          <div className="text-sm font-semibold text-white">AdVanta AI</div>
          <div className="text-xs text-white/60 truncate max-w-[10rem]">
            {current?.name ?? "Growth Command Center"}
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <div className="flex flex-col gap-1.5">
          {groups.map((group) => {
            const active = isGroupActive(group, pathname);
            const open = active || !collapsed[group.heading];
            return (
              <div key={group.heading}>
                <button
                  type="button"
                  onClick={() => toggle(group.heading)}
                  aria-expanded={open}
                  className="flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-white/40 transition hover:text-white/70"
                >
                  <span>{group.heading}</span>
                  <ChevronIcon open={open} />
                </button>
                <div
                  className={cn(
                    "grid transition-all duration-200 ease-in-out",
                    open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
                  )}
                >
                  <ul className="flex min-h-0 flex-col gap-1 overflow-hidden">
                    {group.items.map((item) => (
                      <li key={item.to}>
                        <NavLink
                          to={item.to}
                          end={item.to === "/"}
                          className={navLinkClasses}
                        >
                          <span aria-hidden className="size-1.5 rounded-full bg-current" />
                          {item.label}
                        </NavLink>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })}
        </div>
      </nav>

    </aside>
  );
}
