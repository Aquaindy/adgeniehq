import type { ReactNode } from "react";

type EmptyStateProps = {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
};

export function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-10 text-center sm:py-14">
      {icon ? (
        <div className="flex size-12 items-center justify-center rounded-2xl bg-grape-100 text-grape">
          {icon}
        </div>
      ) : null}
      <div>
        <h3 className="text-base font-semibold text-ink">{title}</h3>
        <p className="mt-1 max-w-md text-sm text-slate-500">{description}</p>
      </div>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
