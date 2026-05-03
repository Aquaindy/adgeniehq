import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { Logomark } from "@/components/Logomark";
import { listWorkspaces } from "@/lib/workspaces";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import { useWorkspaceStore } from "@/stores/workspace-store";

type NavItem = {
  to: string;
  label: string;
};

const navItems: NavItem[] = [
  { to: "/", label: "Command Center" },
  { to: "/growth-dna", label: "Growth DNA" },
  { to: "/onboarding", label: "Onboarding" },
  { to: "/agents", label: "Agents" },
  { to: "/recommendations", label: "Recommendations" },
  { to: "/campaigns", label: "Campaigns" },
  { to: "/creatives", label: "Creatives" },
  { to: "/blog/posts", label: "Blog" },
  { to: "/content", label: "Content" },
  { to: "/seo", label: "SEO & GEO" },
  { to: "/outreach", label: "Outreach" },
  { to: "/ab-tests", label: "A/B tests" },
  { to: "/website", label: "Website" },
  { to: "/reports", label: "Reports" },
  { to: "/autopilot", label: "Autopilot" },
  { to: "/settings", label: "Settings" },
];

const SUPERUSER_NAV: NavItem[] = [{ to: "/admin", label: "Admin" }];

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const currentId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const memberships = useQuery({
    queryKey: ["workspaces"],
    queryFn: listWorkspaces,
    enabled: !!user,
  });
  const current = memberships.data?.find((m) => m.id === currentId) ?? null;

  return (
    <aside className="hidden h-screen w-64 shrink-0 flex-col border-r border-grape-800 bg-grape-700 text-white lg:flex">
      <div className="flex h-16 items-center gap-2 px-5 border-b border-white/10">
        <Logomark />
        <div>
          <div className="text-sm font-semibold text-white">AdVanta AI</div>
          <div className="text-xs text-grape-200 truncate max-w-[10rem]">
            {current?.name ?? "Growth Command Center"}
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="flex flex-col gap-1">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition",
                    isActive
                      ? "bg-white/15 text-white shadow-sm"
                      : "text-grape-100/90 hover:bg-white/10 hover:text-white",
                  )
                }
              >
                <span aria-hidden className="size-1.5 rounded-full bg-current" />
                {item.label}
              </NavLink>
            </li>
          ))}
          {user?.is_superuser
            ? SUPERUSER_NAV.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition",
                        isActive
                          ? "bg-white/15 text-white shadow-sm"
                          : "text-grape-100/90 hover:bg-white/10 hover:text-white",
                      )
                    }
                  >
                    <span aria-hidden className="size-1.5 rounded-full bg-current" />
                    {item.label}
                  </NavLink>
                </li>
              ))
            : null}
        </ul>
      </nav>

    </aside>
  );
}
