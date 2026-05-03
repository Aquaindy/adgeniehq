import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ApiError } from "@/lib/api-client";
import {
  approveEmail,
  draftEmail,
  getProspect,
  listEmailsForProspect,
  markEmailReplied,
  sendEmail,
  updateEmail,
  updateProspect,
} from "@/lib/outreach";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  BacklinkProspectPublic,
  OutreachEmailPublic,
  OutreachEmailStatus,
  ProspectStatus,
} from "@/types/api";

const PROSPECT_PILL: Record<ProspectStatus, string> = {
  new: "bg-slate-100 text-slate-600",
  queued: "bg-slate-100 text-slate-600",
  contacted: "pill-grape",
  replied: "bg-amber-100 text-amber-700",
  won: "pill-success",
  declined: "bg-slate-100 text-slate-500",
  bounced: "pill-danger",
  archived: "bg-slate-100 text-slate-400",
};

const EMAIL_PILL: Record<OutreachEmailStatus, string> = {
  draft: "bg-slate-100 text-slate-600",
  approved: "bg-amber-100 text-amber-700",
  scheduled: "bg-amber-100 text-amber-700",
  sent: "pill-grape",
  failed: "pill-danger",
  replied: "pill-success",
  bounced: "pill-danger",
};

export function ProspectDetailPage() {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const { prospectId } = useParams<{ prospectId: string }>();

  const prospect = useQuery({
    queryKey: ["backlink-prospect", workspaceId, prospectId],
    queryFn: () => getProspect(workspaceId!, prospectId!),
    enabled: !!workspaceId && !!prospectId,
  });

  const emails = useQuery({
    queryKey: ["backlink-prospect", workspaceId, prospectId, "emails"],
    queryFn: () => listEmailsForProspect(workspaceId!, prospectId!),
    enabled: !!workspaceId && !!prospectId,
  });

  if (prospect.isLoading) return <div className="text-sm text-slate-400">Loading…</div>;
  if (prospect.error) {
    return (
      <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
        {prospect.error instanceof Error
          ? prospect.error.message
          : "Could not load."}
      </div>
    );
  }
  if (!prospect.data) return null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-grape-700">
            Outreach prospect
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">
            {prospect.data.domain}
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            {prospect.data.contact_name ?? "No contact yet"}
            {prospect.data.contact_email
              ? ` · ${prospect.data.contact_email}`
              : ""}
          </p>
        </div>
        <span className={cn("pill", PROSPECT_PILL[prospect.data.status])}>
          {prospect.data.status}
        </span>
      </header>

      <ProspectFields prospect={prospect.data} />

      <DraftSection prospect={prospect.data} />

      <EmailsList
        emails={emails.data ?? []}
        loading={emails.isLoading}
      />

      <div className="flex justify-between text-sm">
        <Link to="/outreach" className="font-medium text-grape-700 hover:text-grape-800">
          ← All prospects
        </Link>
      </div>
    </div>
  );
}

function ProspectFields({ prospect }: { prospect: BacklinkProspectPublic }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [contactName, setContactName] = useState(prospect.contact_name ?? "");
  const [contactEmail, setContactEmail] = useState(prospect.contact_email ?? "");
  const [contactRole, setContactRole] = useState(prospect.contact_role ?? "");
  const [pageUrl, setPageUrl] = useState(prospect.page_url ?? "");
  const [notes, setNotes] = useState(prospect.notes ?? "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setContactName(prospect.contact_name ?? "");
    setContactEmail(prospect.contact_email ?? "");
    setContactRole(prospect.contact_role ?? "");
    setPageUrl(prospect.page_url ?? "");
    setNotes(prospect.notes ?? "");
  }, [prospect]);

  const mut = useMutation({
    mutationFn: () =>
      updateProspect(workspaceId!, prospect.id, {
        contact_name: contactName || null,
        contact_email: contactEmail || null,
        contact_role: contactRole || null,
        page_url: pageUrl || null,
        notes: notes || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["backlink-prospect", workspaceId, prospect.id],
      });
      setOpen(false);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not save."),
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    mut.mutate();
  }

  if (!open) {
    return (
      <Card>
        <CardHeader
          title="Contact"
          action={
            <Button variant="secondary" onClick={() => setOpen(true)}>
              Edit
            </Button>
          }
        />
        <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <Field label="Contact name" value={prospect.contact_name} />
          <Field label="Contact email" value={prospect.contact_email} />
          <Field label="Contact role" value={prospect.contact_role} />
          <Field label="Specific page" value={prospect.page_url} />
          {prospect.notes ? (
            <div className="sm:col-span-2">
              <dt className="text-slate-400">Notes</dt>
              <dd className="mt-1 whitespace-pre-wrap text-slate-700">
                {prospect.notes}
              </dd>
            </div>
          ) : null}
          {prospect.backlink_url ? (
            <div className="sm:col-span-2">
              <dt className="text-slate-400">Backlink URL</dt>
              <dd className="mt-1">
                <a
                  href={prospect.backlink_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-grape-700 hover:text-grape-800"
                >
                  {prospect.backlink_url}
                </a>
              </dd>
            </div>
          ) : null}
        </dl>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader title="Edit contact" />
      <form className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2" onSubmit={onSubmit}>
        <Input label="Contact name" value={contactName} onChange={setContactName} />
        <Input label="Contact email" value={contactEmail} onChange={setContactEmail} />
        <Input label="Contact role" value={contactRole} onChange={setContactRole} />
        <Input label="Specific page URL" value={pageUrl} onChange={setPageUrl} />
        <label className="sm:col-span-2 flex flex-col gap-1.5">
          <span className="font-medium text-slate-text">Notes</span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
          />
        </label>
        {error ? (
          <div className="sm:col-span-2 rounded-lg bg-red-50 px-3 py-2 text-red-700">
            {error}
          </div>
        ) : null}
        <div className="sm:col-span-2 flex items-center gap-2">
          <Button type="submit" disabled={mut.isPending}>
            {mut.isPending ? "Saving…" : "Save"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-slate-400">{label}</dt>
      <dd className="mt-1 text-slate-700">{value || "—"}</dd>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="font-medium text-slate-text">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
      />
    </label>
  );
}

function DraftSection({ prospect }: { prospect: BacklinkProspectPublic }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [angle, setAngle] = useState("");
  const [senderName, setSenderName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: () =>
      draftEmail(workspaceId!, prospect.id, {
        angle: angle || null,
        sender_name: senderName || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["backlink-prospect", workspaceId, prospect.id, "emails"],
      });
      setAngle("");
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not draft."),
  });

  const cannotDraft = !prospect.contact_email;

  return (
    <Card>
      <CardHeader
        title="Draft an outreach email"
        subtitle={
          cannotDraft
            ? "Add a contact email above before drafting."
            : "Uses the configured LLM if available; otherwise a deterministic template."
        }
      />
      {!cannotDraft ? (
        <form
          className="mt-4 grid grid-cols-1 gap-3 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            mut.mutate();
          }}
        >
          <Input label="Angle (optional)" value={angle} onChange={setAngle} />
          <Input
            label="Sender name (optional)"
            value={senderName}
            onChange={setSenderName}
          />
          {error ? (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-red-700">
              {error}
            </div>
          ) : null}
          <div>
            <Button type="submit" disabled={mut.isPending}>
              {mut.isPending ? "Drafting…" : "Draft email"}
            </Button>
          </div>
        </form>
      ) : null}
    </Card>
  );
}

function EmailsList({
  emails,
  loading,
}: {
  emails: OutreachEmailPublic[];
  loading: boolean;
}) {
  if (loading) return <p className="text-sm text-slate-400">Loading emails…</p>;
  if (emails.length === 0) {
    return (
      <Card>
        <CardHeader title="Outreach emails" />
        <p className="mt-3 text-sm text-slate-500">
          No drafts yet. Use the form above to generate one.
        </p>
      </Card>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {emails.map((email) => (
        <EmailCard key={email.id} email={email} />
      ))}
    </div>
  );
}

function EmailCard({ email }: { email: OutreachEmailPublic }) {
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspaceId);
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState(email.subject);
  const [body, setBody] = useState(email.body);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSubject(email.subject);
    setBody(email.body);
  }, [email.subject, email.body]);

  function invalidate() {
    queryClient.invalidateQueries({
      queryKey: ["backlink-prospect", workspaceId, email.prospect_id],
    });
    queryClient.invalidateQueries({
      queryKey: ["backlink-prospect", workspaceId, email.prospect_id, "emails"],
    });
    queryClient.invalidateQueries({ queryKey: ["backlink-prospects", workspaceId] });
  }

  const update = useMutation({
    mutationFn: () =>
      updateEmail(workspaceId!, email.id, { subject, body }),
    onSuccess: () => {
      invalidate();
      setEditing(false);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not save."),
  });
  const approve = useMutation({
    mutationFn: () => approveEmail(workspaceId!, email.id),
    onSuccess: invalidate,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not approve."),
  });
  const send = useMutation({
    mutationFn: () => sendEmail(workspaceId!, email.id),
    onSuccess: invalidate,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not send."),
  });
  const replied = useMutation({
    mutationFn: (won: boolean) =>
      markEmailReplied(workspaceId!, email.id, { won }),
    onSuccess: invalidate,
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not mark."),
  });

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <span className={cn("pill", EMAIL_PILL[email.status])}>
              {email.status}
            </span>
            <span>{email.subject}</span>
          </span>
        }
        subtitle={
          <span className="text-xs text-slate-400">
            to {email.to_email}
            {email.model_used ? ` · ${email.model_used}` : email.source === "deterministic" ? " · deterministic" : ""}
            {email.sent_at
              ? ` · sent ${new Date(email.sent_at).toLocaleString()}`
              : ""}
          </span>
        }
        action={
          email.status === "draft" ? (
            <Button variant="secondary" onClick={() => setEditing((v) => !v)}>
              {editing ? "Cancel" : "Edit"}
            </Button>
          ) : null
        }
      />

      {error ? (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {email.error_message && email.status === "failed" ? (
        <pre className="mt-3 max-h-32 overflow-auto rounded-lg bg-red-50 p-2 text-xs text-red-700">
{email.error_message}
        </pre>
      ) : null}

      {editing ? (
        <form
          className="mt-3 flex flex-col gap-3 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            update.mutate();
          }}
        >
          <Input label="Subject" value={subject} onChange={setSubject} />
          <label className="flex flex-col gap-1.5">
            <span className="font-medium text-slate-text">Body</span>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={10}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-xs text-ink shadow-sm outline-none focus:border-grape focus:ring-2 focus:ring-grape-200"
            />
          </label>
          <div>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      ) : (
        <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-xl bg-slate-50 p-4 font-sans text-sm text-slate-700">
{email.body}
        </pre>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {email.status === "draft" ? (
          <Button onClick={() => approve.mutate()} disabled={approve.isPending}>
            {approve.isPending ? "Approving…" : "Approve"}
          </Button>
        ) : null}
        {email.status === "approved" || email.status === "failed" ? (
          <Button onClick={() => send.mutate()} disabled={send.isPending}>
            {send.isPending ? "Sending…" : "Send via SMTP"}
          </Button>
        ) : null}
        {email.status === "sent" ? (
          <>
            <Button
              variant="ghost"
              onClick={() => replied.mutate(true)}
              disabled={replied.isPending}
            >
              Mark won
            </Button>
            <Button
              variant="ghost"
              onClick={() => replied.mutate(false)}
              disabled={replied.isPending}
            >
              Mark replied
            </Button>
          </>
        ) : null}
      </div>
    </Card>
  );
}
