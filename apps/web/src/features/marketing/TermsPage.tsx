import { MarketingLayout } from "@/features/marketing/MarketingLayout";

export function TermsPage() {
  return (
    <MarketingLayout>
      <article className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <h1 className="text-3xl font-semibold text-ink">Terms of Service</h1>
        <p className="mt-2 text-sm text-slate-400">
          Last updated: {new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}
        </p>

        <Section title="1. Acceptance">
          <p>
            By creating an AdGenieHQ account or workspace you agree to these
            Terms. If you're using AdGenieHQ on behalf of a company, you
            represent that you have authority to bind that company.
          </p>
        </Section>

        <Section title="2. Your data + connected accounts">
          <p>
            You authorize AdGenieHQ to read and (where you've explicitly
            approved) write to ad accounts, analytics platforms, and websites
            you connect via OAuth. Tokens are encrypted at rest and used
            only to perform the actions you approve.
          </p>
          <p>
            You retain full ownership of all content, recommendations, and
            metrics produced in your workspace. You can disconnect any
            integration or delete your workspace at any time.
          </p>
        </Section>

        <Section title="3. Approvals + Autopilot">
          <p>
            Sensitive actions (campaign launches, budget changes, audience
            edits) require explicit approval. Autopilot Mode, when enabled,
            executes within rules you set and can be disabled at any time.
            AdGenieHQ is not liable for ad spend incurred via approved
            actions.
          </p>
        </Section>

        <Section title="4. Acceptable use">
          <p>
            Don't use AdGenieHQ to send unsolicited spam, run misleading ad
            campaigns, infringe third-party rights, or violate the terms of
            connected platforms (Google, Meta, LinkedIn, etc.). Outreach
            emails sent via AdGenieHQ must include an unsubscribe path —
            we add one automatically.
          </p>
        </Section>

        <Section title="5. Billing">
          <p>
            Paid plans are billed monthly or annually via Paddle. Plan limits are
            enforced on a 30-day rolling window. Past-due subscriptions revert to
            the free tier until payment resolves. You can cancel anytime; access
            continues until the end of the paid period and payments are
            non-refundable — see our{" "}
            <a className="text-grape-700" href="/refund">
              Refund &amp; Cancellation Policy
            </a>
            .
          </p>
        </Section>

        <Section title="6. Termination">
          <p>
            You can delete your workspace at any time. We may suspend
            accounts that violate these Terms, with notice when feasible.
          </p>
        </Section>

        <Section title="7. Liability">
          <p>
            AdGenieHQ is provided "as is." Our aggregate liability for any
            claim is limited to the fees you paid in the 12 months
            preceding the event giving rise to the claim.
          </p>
        </Section>

        <Section title="8. Contact">
          <p>
            Questions: <a className="text-grape-700" href="mailto:support@aimarketinghub.io">support@aimarketinghub.io</a>.
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
