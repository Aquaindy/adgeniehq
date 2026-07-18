import { MarketingLayout } from "@/features/marketing/MarketingLayout";

export function PrivacyPage() {
  return (
    <MarketingLayout>
      <article className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <h1 className="text-3xl font-semibold text-ink">Privacy Policy</h1>
        <p className="mt-2 text-sm text-slate-400">
          Last updated: {new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}
        </p>

        <Section title="What we collect">
          <p>
            We store the data you give us (workspace name, contact info,
            onboarding profile), tokens for the OAuth integrations you
            connect (encrypted at rest with Fernet), and the agent
            outputs/recommendations our system produces from your
            workspace data.
          </p>
          <p>
            We do not sell your data. We don't use your data to train
            third-party models — LLM calls are scoped to your prompt with
            no cross-customer learning.
          </p>
        </Section>

        <Section title="Subprocessors">
          <p>
            We use a small set of subprocessors: PayPal (billing),
            OpenAI-compatible LLM providers (content generation),
            transactional email (send/receive), Sentry (error tracking),
            and the platforms you explicitly connect via OAuth.
          </p>
        </Section>

        <Section title="Cookies">
          <p>
            We use a single auth refresh-token cookie scoped to{" "}
            <code className="text-xs">/api/v1/auth</code> (httpOnly,
            Secure, SameSite=Lax). We don't use marketing or analytics
            cookies on the dashboard.
          </p>
        </Section>

        <Section title="Your rights">
          <p>
            You can export, edit, or delete your data at any time via the
            workspace settings. EU/UK residents have the rights described
            in GDPR / UK GDPR; California residents have the rights in
            CCPA. Email{" "}
            <a className="text-grape-700" href="mailto:support@aimarketinghub.io">
              support@aimarketinghub.io
            </a>
            .
          </p>
        </Section>

        <Section title="Outreach + inbound email">
          <p>
            Outreach emails sent via AdGenieHQ carry a Reply-To address
            that routes replies back to your workspace. Reply payloads are
            stored only to update the linked outreach status — we don't
            persist the message body beyond the inbound webhook log.
          </p>
        </Section>

        <Section title="Data retention">
          <p>
            We keep account data for as long as your workspace is active.
            Deleted workspaces are removed within 30 days; encrypted
            backups age out within 90 days of deletion.
          </p>
        </Section>

        <Section title="Contact">
          <p>
            Reach us at{" "}
            <a className="text-grape-700" href="mailto:support@aimarketinghub.io">
              support@aimarketinghub.io
            </a>
            .
          </p>
        </Section>
      </article>
    </MarketingLayout>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <div className="mt-2 flex flex-col gap-3 text-sm text-slate-600">{children}</div>
    </section>
  );
}
