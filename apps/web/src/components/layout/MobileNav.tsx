import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

type Item = { to: string; label: string };

const items: Item[] = [
  { to: "/dashboard", label: "Home" },
  { to: "/agents", label: "Agents" },
  { to: "/recommendations", label: "Recs" },
  { to: "/campaigns", label: "Ads" },
  { to: "/reports", label: "Reports" },
];

export function MobileNav() {
  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-slate-200 bg-surface/95 px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur lg:hidden"
    >
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/dashboard"}
          className={({ isActive }) =>
            cn(
              "flex flex-1 flex-col items-center gap-0.5 rounded-lg px-2 py-1 text-[11px] font-medium transition",
              isActive ? "text-grape-700" : "text-slate-500",
            )
          }
        >
          <span aria-hidden className="size-1.5 rounded-full bg-current" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
