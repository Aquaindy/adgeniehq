import { MarketingLayout } from "@/features/marketing/MarketingLayout";

export function RefundPolicyPage() {
  return (
    <MarketingLayout>
      <article className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
        <h1 className="text-3xl font-semibold text-ink">
          Refund &amp; Cancellation Policy
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          Last updated:{" "}
          {new Date().toLocaleDateString("en-US", {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>

        <Section title="1. Subscriptions">
          <p>
            AdGenieHQ subscriptions (Starter, Pro, Agency) are billed in advance
            on a recurring basis — monthly or annually, depending on the plan
            you choose — through our payment provider, Paddle, who acts as the
            merchant of record.
          </p>
        </Section>

        <Section title="2. Cancel anytime">
          <p>
            You can cancel your subscription at any time from{" "}
            <span className="font-medium text-slate-700">
              Settings → Billing → Manage plan
            </span>
            , which opens your secure Paddle billing portal. Cancellation stops
            future renewals.
          </p>
          <p>
            When you cancel, you keep full access to your paid plan until the end
            of the billing period you have already paid for. After that date the
            workspace reverts to the free tier — your data and saved work remain
            intact.
          </p>
        </Section>

        <Section title="3. No refunds for unused time">
          <p>
            Payments are non-refundable. We do not provide refunds or credits for
            partial billing periods, unused time, or features you did not use,
            except where required by applicable law. Cancelling simply prevents
            the next charge.
          </p>
        </Section>

        <Section title="4. Annual plans">
          <p>
            Annual subscriptions are paid upfront for the year. You can cancel an
            annual plan at any time to stop it from renewing; access continues
            until the end of the paid annual term and is not pro-rated or
            refunded for the remaining months.
          </p>
        </Section>

        <Section title="5. Platform fees">
          <p>
            AdGenieHQ also charges usage-based platform fees on ad activity managed
            through the app (a one-time listing fee per campaign plus a monthly
            run fee). These fees are earned when the activity occurs and are
            non-refundable once accrued.
          </p>
        </Section>

        <Section title="6. Failed or duplicate charges">
          <p>
            If you were charged in error — for example a duplicate charge or a
            charge after a confirmed cancellation — contact us and we will
            investigate and correct any genuine billing error promptly.
          </p>
        </Section>

        <Section title="7. Taxes">
          <p>
            As merchant of record, Paddle calculates and collects any applicable
            sales tax or VAT, which is added on top of the listed plan price at
            checkout. Tax amounts are handled by Paddle in accordance with their
            policies.
          </p>
        </Section>

        <Section title="8. Contact">
          <p>
            Questions about billing, cancellation, or a charge?{" "}
            <a
              className="text-grape-700"
              href="mailto:support@aimarketinghub.io"
            >
              support@aimarketinghub.io
            </a>
            .
          </p>
        </Section>
      </article>
    </MarketingLayout>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <div className="mt-2 flex flex-col gap-3 text-sm text-slate-600">
        {children}
      </div>
    </section>
  );
}
