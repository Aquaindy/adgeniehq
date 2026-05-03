import { NavLink, Outlet } from "react-router-dom";

import { cn } from "@/lib/utils";

const TABS: { to: string; label: string }[] = [
  { to: "/settings/profile", label: "User account" },
  { to: "/settings/billing", label: "Billing" },
  { to: "/settings/integrations", label: "Integrations" },
  { to: "/settings/api-keys", label: "API keys" },
];

export function SettingsLayout() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <p className="text-xs uppercase tracking-wider text-grape-700">Settings</p>

      <nav className="-mt-3 flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition whitespace-nowrap",
                isActive
                  ? "border-grape-700 text-grape-700"
                  : "border-transparent text-slate-500 hover:text-ink",
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  );
}
