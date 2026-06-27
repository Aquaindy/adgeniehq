import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import {
  type ProviderCredential,
  type ProviderId,
  type ProviderSpec,
  addProviderCredential,
  listProviderCredentials,
  listProviderSpecs,
  revokeProviderCredential,
  testProviderCredential,
} from "@/lib/provider-credentials";

/**
 * BYOK credentials section — embedded below the workspace API keys section
 * on the same Settings → API keys tab.
 *
 * Distinction from the section above:
 *   - "Your API keys" = OUTBOUND. Keys *external clients* use to call the
 *     AdGenieHQ API on this workspace's behalf.
 *   - "Provider credentials" = INBOUND. Keys *AdGenieHQ uses* to call OpenAI,
 *     Anthropic, Google AI on this workspace's behalf for LLM-backed work.
 *
 * Keys are encrypted with Fernet at rest. The plaintext is never returned
 * after submission — only `last_four` is shown.
 */
export function ProviderCredentialsCard({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const queryClient = useQueryClient();

  const specs = useQuery({
    queryKey: ["provider-credential-specs", workspaceId],
    queryFn: () => listProviderSpecs(workspaceId),
  });
  const list = useQuery({
    queryKey: ["provider-credentials", workspaceId],
    queryFn: () => listProviderCredentials(workspaceId),
  });

  const activeByProvider = new Map<ProviderId, ProviderCredential>();
  for (const cred of list.data ?? []) {
    if (!cred.revoked_at && !activeByProvider.has(cred.provider)) {
      activeByProvider.set(cred.provider, cred);
    }
  }

  const test = useMutation({
    mutationFn: (id: string) => testProviderCredential(workspaceId, id),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["provider-credentials", workspaceId],
      });
    },
  });

  const revoke = useMutation({
    mutationFn: (id: string) => revokeProviderCredential(workspaceId, id),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["provider-credentials", workspaceId],
      });
    },
  });

  return (
    <Card>
      <CardHeader
        title="Provider credentials (BYOK)"
        subtitle="Workspace-scoped keys for OpenAI, Anthropic, and Google AI. AdGenieHQ uses these on your behalf for LLM-backed agents and skills. Encrypted at rest with Fernet — only the last four characters are shown after saving."
      />

      {specs.isLoading || list.isLoading ? (
        <p className="mt-3 text-sm text-slate-400">Loading…</p>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          {(specs.data ?? []).map((spec) => (
            <ProviderRow
              key={spec.provider_id}
              workspaceId={workspaceId}
              spec={spec}
              active={activeByProvider.get(spec.provider_id) ?? null}
              onTest={(id) => test.mutate(id)}
              onRevoke={(id) => revoke.mutate(id)}
              testPending={test.isPending && test.variables === activeByProvider.get(spec.provider_id)?.id}
              revokePending={revoke.isPending && revoke.variables === activeByProvider.get(spec.provider_id)?.id}
            />
          ))}
        </div>
      )}
    </Card>
  );
}


function ProviderRow({
  workspaceId,
  spec,
  active,
  onTest,
  onRevoke,
  testPending,
  revokePending,
}: {
  workspaceId: string;
  spec: ProviderSpec;
  active: ProviderCredential | null;
  onTest: (id: string) => void;
  onRevoke: (id: string) => void;
  testPending: boolean;
  revokePending: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-slate-200 bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div>
          <div className="font-medium text-ink">{spec.display_name}</div>
          <div className="text-xs text-slate-500">
            {spec.secret_hint} ·{" "}
            <a
              href={spec.docs_url}
              target="_blank"
              rel="noreferrer"
              className="text-grape-700 underline hover:text-grape-800"
            >
              get a key
            </a>
          </div>
        </div>
        {active ? (
          <ActiveBadge cred={active} />
        ) : (
          <span className="pill bg-slate-100 text-slate-600">No key saved</span>
        )}
      </div>

      {active ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-3 text-xs text-slate-500">
          <div>
            Last 4: <code className="font-mono text-slate-700">…{active.last_four}</code>
            {active.label ? <> · {active.label}</> : null}
            {active.last_tested_at ? (
              <>
                {" · tested "}
                {new Date(active.last_tested_at).toLocaleString()}
                {active.last_test_status === "failed" && active.last_test_error ? (
                  <span className="ml-2 text-red-600">
                    ({active.last_test_error})
                  </span>
                ) : null}
              </>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => onTest(active.id)}
              disabled={testPending}
            >
              {testPending ? "Testing…" : "Test"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => onRevoke(active.id)}
              disabled={revokePending}
            >
              {revokePending ? "Revoking…" : "Revoke"}
            </Button>
            <Button variant="secondary" onClick={() => setOpen((v) => !v)}>
              {open ? "Cancel" : "Replace"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="border-t border-slate-100 px-4 py-3">
          <Button variant="secondary" onClick={() => setOpen((v) => !v)}>
            {open ? "Cancel" : "Add key"}
          </Button>
        </div>
      )}

      {open ? (
        <AddForm
          workspaceId={workspaceId}
          providerId={spec.provider_id}
          onDone={() => setOpen(false)}
        />
      ) : null}
    </div>
  );
}


function ActiveBadge({ cred }: { cred: ProviderCredential }) {
  if (cred.last_test_status === "ok") {
    return <span className="pill pill-success">Active · tested OK</span>;
  }
  if (cred.last_test_status === "failed") {
    return <span className="pill pill-danger">Active · last test failed</span>;
  }
  return <span className="pill pill-grape">Active · untested</span>;
}


function AddForm({
  workspaceId,
  providerId,
  onDone,
}: {
  workspaceId: string;
  providerId: ProviderId;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [secret, setSecret] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      addProviderCredential(workspaceId, {
        provider: providerId,
        secret: secret.trim(),
        label: label.trim() || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["provider-credentials", workspaceId],
      });
      setSecret("");
      setLabel("");
      onDone();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Could not save key.");
    },
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (secret.trim().length < 12) {
      setError("That secret looks too short to be a valid API key.");
      return;
    }
    mutation.mutate();
  }

  return (
    <form
      className="flex flex-col gap-3 border-t border-slate-100 bg-slate-50 px-4 py-3"
      onSubmit={onSubmit}
      noValidate
    >
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-slate-text">Secret</span>
        <input
          type="password"
          autoComplete="new-password"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder="Paste your key…"
          required
          className={cn(
            "rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink",
            "shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200",
          )}
        />
      </label>
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-slate-text">
          Label <span className="text-slate-400">(optional)</span>
        </span>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. Acme prod, dev sandbox"
          className="rounded-xl border border-slate-200 bg-surface px-3 py-2 text-sm text-ink shadow-sm outline-none transition focus:border-grape focus:ring-2 focus:ring-grape-200"
        />
      </label>
      {error ? (
        <div className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700" role="alert">
          {error}
        </div>
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save key"}
        </Button>
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
