import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  generateFeeInvoice,
  listFeeInvoices,
  listPaymentProviders,
  markFeeInvoicePaid,
  voidFeeInvoice,
} from "@/lib/fees";
import { cn } from "@/lib/utils";
import type { FeeInvoice } from "@/types/api";

const money = (cents: number) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(cents / 100);

const inputCls =
  "w-full rounded-xl border border-slate-200 bg-surface px-3 py-1.5 text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200";

export function FeeInvoicesAdminPanel() {
  const qc = useQueryClient();
  const [workspaceId, setWorkspaceId] = useState("");
  const [provider, setProvider] = useState("manual");
  const [period, setPeriod] = useState("");
  const [error, setError] = useState<string | null>(null);

  const providers = useQuery({
    queryKey: ["admin", "payment-providers"],
    queryFn: listPaymentProviders,
  });
  const invoices = useQuery({
    queryKey: ["admin", "fee-invoices"],
    queryFn: () => listFeeInvoices(),
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admin", "fee-invoices"] });
    qc.invalidateQueries({ queryKey: ["admin", "fee-revenue"] });
  };

  const generate = useMutation({
    mutationFn: () =>
      generateFeeInvoice({
        workspace_id: workspaceId.trim(),
        provider,
        period: period.trim() || null,
      }),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not generate invoice."),
  });

  const markPaid = useMutation({
    mutationFn: (id: string) => markFeeInvoicePaid(id),
    onSuccess: refresh,
  });
  const voidInv = useMutation({
    mutationFn: (id: string) => voidFeeInvoice(id),
    onSuccess: refresh,
  });

  return (
    <Card>
      <CardHeader
        title="Fee invoices"
        subtitle="Bill a workspace's accrued fees through a payment provider. The ledger stays processor-agnostic; only invoiced fees leave the accrued pool."
      />

      {/* Generate form */}
      <div className="mt-4 rounded-2xl border border-slate-100 p-4">
        <div className="text-sm font-semibold text-ink">Generate an invoice</div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Workspace ID">
            <input
              value={workspaceId}
              onChange={(e) => setWorkspaceId(e.target.value)}
              placeholder="uuid"
              className={inputCls}
            />
          </Field>
          <Field label="Payment provider">
            <select value={provider} onChange={(e) => setProvider(e.target.value)} className={inputCls}>
              {(providers.data ?? []).map((p) => (
                <option key={p.provider} value={p.provider} disabled={!p.configured}>
                  {p.display_name}
                  {p.configured ? "" : " (not configured)"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Period (optional)">
            <input
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              placeholder="YYYY-MM"
              className={inputCls}
            />
          </Field>
          <div className="flex items-end">
            <Button
              onClick={() => generate.mutate()}
              disabled={!workspaceId.trim() || generate.isPending}
            >
              {generate.isPending ? "Billing…" : "Generate invoice"}
            </Button>
          </div>
        </div>
        {error ? (
          <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        ) : null}
      </div>

      {/* Invoices table */}
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-xs uppercase tracking-wider text-slate-400">
              <th className="px-3 py-2">Created</th>
              <th className="px-3 py-2">Workspace</th>
              <th className="px-3 py-2">Provider</th>
              <th className="px-3 py-2">Amount</th>
              <th className="px-3 py-2">Fees</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(invoices.data ?? []).length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-slate-500">
                  No invoices yet. Generate one above to bill a workspace's accrued fees.
                </td>
              </tr>
            ) : (
              (invoices.data ?? []).map((inv: FeeInvoice) => (
                <tr key={inv.id} className="hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-700">
                    {new Date(inv.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-500">
                    {inv.workspace_id.slice(0, 8)}…
                  </td>
                  <td className="px-3 py-2 text-slate-700">{inv.provider}</td>
                  <td className="px-3 py-2 font-medium text-ink">{money(inv.amount_cents)}</td>
                  <td className="px-3 py-2 text-slate-700">{inv.accrual_count}</td>
                  <td className="px-3 py-2">
                    <StatusPill status={inv.status} />
                    {inv.hosted_url ? (
                      <a
                        href={inv.hosted_url}
                        target="_blank"
                        rel="noreferrer"
                        className="ml-2 text-xs text-grape-700 underline"
                      >
                        view
                      </a>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {inv.status === "open" ? (
                      <div className="flex justify-end gap-3">
                        <button
                          onClick={() => markPaid.mutate(inv.id)}
                          disabled={markPaid.isPending}
                          className="text-xs font-medium text-success hover:underline disabled:opacity-50"
                        >
                          Mark paid
                        </button>
                        <button
                          onClick={() => voidInv.mutate(inv.id)}
                          disabled={voidInv.isPending}
                          className="text-xs font-medium text-danger hover:underline disabled:opacity-50"
                        >
                          Void
                        </button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-xs text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function StatusPill({ status }: { status: FeeInvoice["status"] }) {
  return (
    <span
      className={cn(
        "pill",
        status === "paid" && "pill-success",
        status === "open" && "pill-grape",
        status === "failed" && "pill-danger",
        status === "void" && "bg-slate-100 text-slate-500",
        status === "draft" && "pill-warning",
      )}
    >
      {status}
    </span>
  );
}
