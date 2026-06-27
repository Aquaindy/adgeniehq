import type { ReactNode } from "react";

import { Logomark } from "@/components/Logomark";

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-grape-soft">
      <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10 sm:px-6">
        <div className="flex items-center gap-3 pb-8">
          <Logomark size="lg" />
          <div>
            <div className="text-base font-semibold text-ink">AdGenieHQ</div>
            <div className="text-xs text-slate-500">Growth Command Center</div>
          </div>
        </div>

        <div className="card p-6 sm:p-8">
          <h1 className="text-xl font-semibold text-ink sm:text-2xl">{title}</h1>
          {subtitle ? (
            <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
          ) : null}
          <div className="mt-6">{children}</div>
        </div>

        {footer ? (
          <div className="pt-4 text-center text-sm text-slate-500">{footer}</div>
        ) : null}
      </div>
    </div>
  );
}
