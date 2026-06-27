import { NavLink, Outlet } from "react-router-dom";

import { cn } from "@/lib/utils";

const SUB_TABS: { to: string; label: string }[] = [
  { to: "/settings/api-keys/your-keys", label: "Your API keys" },
  { to: "/settings/api-keys/providers", label: "Provider credentials (BYOK)" },
];

/**
 * `/settings/api-keys` layout. Two sub-tabs:
 *   - Your API keys — outbound. External clients calling AdGenieHQ on your
 *     workspace's behalf.
 *   - Provider credentials (BYOK) — inbound. AdGenieHQ calling OpenAI /
 *     Anthropic / Google AI on your behalf with your own billing.
 */
export function ApiKeysPage() {
  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="text-2xl font-semibold text-ink sm:text-3xl">API keys</h1>
        <p className="mt-2 text-sm text-slate-500">
          Two kinds of keys live here. <strong>Your API keys</strong> let
          external clients call AdGenieHQ on this workspace's behalf.{" "}
          <strong>Provider credentials</strong> let AdGenieHQ call OpenAI,
          Anthropic, or Google AI on your behalf with your own billing.
        </p>
      </header>

      <nav className="flex gap-1 overflow-x-auto rounded-xl bg-slate-100 p-1">
        {SUB_TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                "flex-1 whitespace-nowrap rounded-lg px-3 py-1.5 text-center text-sm font-medium transition",
                isActive
                  ? "bg-surface text-grape-700 shadow-sm"
                  : "text-slate-600 hover:text-ink",
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
