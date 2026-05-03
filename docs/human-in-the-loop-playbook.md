# AdVanta AI — Human-in-the-Loop Playbook

The 10–30% of ongoing growth-ops work that AdVanta's AI agents *don't*
fully cover, written as a step-by-step operational guide a virtual
assistant or in-house marketer can follow. Together with the agents,
this playbook closes the gap between AdVanta and a "done-for-you"
service like Mega AI.

> **Total time commitment**
> - Daily: 10–15 min
> - Weekly: 1–2 hrs
> - Monthly: 3–5 hrs
> - Quarterly: 4–8 hrs
> - Ad-hoc / events: variable
>
> **Total ≈ 8–14 hours/month** for a single-product, mid-market
> account. Larger accounts or agencies running multiple workspaces will
> scale this up roughly linearly.

---

## Access checklist (do this once before the first shift)

Before the VA starts, the workspace owner should confirm:

- [ ] VA invited to the workspace as **Marketer** role (not Admin or Owner).
      This lets them approve/reject recommendations and ship A/B winners
      but blocks them from billing, integration disconnects, or API-key
      management — which are Owner-only by design.
- [ ] Real ad accounts connected under **Settings → Integrations**
      (Google Ads, Meta Ads, LinkedIn Ads as applicable) plus GA4 and
      Search Console.
- [ ] **Onboarding profile** completed — business name, ICP, offer,
      brand voice, monthly ad budget, primary conversion goal,
      competitors. The agents' output quality scales with this.
- [ ] **Autopilot config** decided. Default: Approval Mode (every action
      needs a human click). Owner toggles guardrails before VA shifts
      begin.
- [ ] **2FA enabled** on the VA's account (Settings → User account →
      Two-factor).
- [ ] Shared escalation channel agreed (Slack DM, email, etc.) — the
      VA needs a way to flag anything outside their authority.

---

## Daily routine (10–15 minutes)

The goal of the daily shift is to keep nothing important sitting in a
queue for more than 24 hours. It is not strategic work — it is hygiene.

### Step 1 — Open the Command Center (2 min)

1. Navigate to `/` (Command Center).
2. Scan the four KPI tiles: *Connected accounts*, *Active campaigns*,
   *Open recs*, *Spend today*.
3. Confirm:
   - All connected accounts show green status. Any red/yellow → log a
     ticket (see "Escalation playbook" below) and continue.
   - *Spend today* is within the expected daily band. If it's spiking
     >2× the normal pace before noon, escalate immediately.
4. Read the "Critical alerts" strip at the top, if any. Treat anything
   tagged **high** risk as a same-shift item.

### Step 2 — Triage the recommendations queue (5–8 min)

1. Open `/recommendations`.
2. Filter by status = **Open**, sort by risk descending.
3. For each recommendation, the VA decides one of three things:
   - **Approve** — the change is obvious and within VA authority
     (low/medium risk, inside the budget guardrails).
   - **Reject** — the recommendation conflicts with a known business
     reality (e.g. "don't pause this — campaign supports a launch
     next Tuesday"). Add a one-line reason in the Reject modal.
   - **Escalate** — high-risk, or the VA isn't sure. Tag the owner in
     the shared channel with the recommendation URL and "needs your
     call before EOD."
4. The VA's authority limits (suggested defaults, the owner can adjust):
   - ✅ Approve: pauses, audience tightening, fatigue-driven creative
     swaps, low-risk budget reductions.
   - ❌ Don't approve without owner sign-off: budget *increases* over
     20%, new campaign launches, conversion-event changes, audience
     *expansion*, anything tagged **high** risk.

### Step 3 — Review yesterday's Autopilot decisions (3 min)

1. Open `/autopilot`. Scroll to "Recent auto-approved actions."
2. Skim the last 24 hours of decisions. The VA isn't second-guessing
   the agent — they're checking that the rules produced sensible
   outcomes.
3. Anything that looks wrong (e.g. agent paused a campaign that
   *should* have stayed live because of a context the rules can't
   see), the VA reverts via the recommendation's *Revert* button and
   notes the reason for the weekly review.

### Step 4 — Glance at the audit log (2 min)

1. Open `/admin/audit` *(Owner / superuser only — VAs without admin
   skip this step and rely on the recommendation queue instead).*
2. Scan for anything weird:
   - Failed webhook events
   - Agent runs that errored out
   - Provider sync failures
3. Anything failing repeatedly → escalate.

### Step 5 — Close out the shift

End each day with a one-line note in the shared channel:
> "AdVanta — daily: 4 recs approved (3 pause, 1 budget tighten),
> 1 rejected (campaign supports Tuesday launch), 0 escalations.
> Spend pacing normal."

This single line gives the owner everything they need to know the day
ran clean without reading anything else.

---

## Weekly routine (1–2 hours, run every Monday morning)

The weekly shift is where the VA stops doing pure hygiene and starts
adding judgment back to the system.

### Step 1 — Generate and read the weekly report (15 min)

1. Open `/reports`. Click **Generate report** → period = "Last 7 days".
2. When the PDF renders, scan top-to-bottom:
   - **Spend / leads / CPA / ROAS** — directional vs prior week.
   - **Campaign change log** — what shipped, what was reverted.
   - **A/B test results** — anything reaching significance?
   - **Open recommendations** — any that have aged >7 days? Those need
     a decision today.

### Step 2 — Ship A/B test winners (15 min)

1. Open `/ab-tests`. Filter by status = **Reached significance**.
2. For each test that's reached significance:
   - Open the detail page.
   - Confirm sample size and conversion delta look stable (not
     driven by a single freak day).
   - Click **Promote winner**. The agent rolls the winning variant
     to 100% traffic and opens a recommendation to retire the loser.
3. For tests that are stalled (>14 days, no significance, low traffic),
   click **Stop test** and note the reason.

### Step 3 — Review the recommendations backlog (20 min)

1. Open `/recommendations`. Filter by status = **Open**, age > 3 days.
2. The daily routine should keep this list near-empty. Anything still
   here means the agent thinks it matters but the VA wasn't sure on
   first pass. Today, decide:
   - Approve, reject, or escalate to the owner with a recommendation.
3. Goal at the end of step 3: **zero open recs older than 3 days.**

### Step 4 — Recalibrate Autopilot rules (15 min)

1. Open `/autopilot`. Click **Recent auto-approved actions** for the
   past 7 days.
2. Tally:
   - Auto-approvals you're glad happened ✓
   - Auto-approvals you reverted ✗
   - Auto-approvals you'd have done differently 🤔
3. If the ✗ + 🤔 column is more than 15% of total, the rules are out
   of calibration. Tighten the rule that produced the bad outcome:
   - If the agent paused too aggressively → raise the CPA threshold
     or extend the look-back window.
   - If the agent shifted budget too fast → lower the max-shift cap.
   - If the agent allowed an action you'd never approve → remove that
     action type from the allowlist.
4. Save changes. The audit log captures who changed what.

### Step 5 — Briefing note for the agents (15 min)

This is the highest-leverage habit in the whole playbook. Open the
**Onboarding profile** (`/onboarding`) and update the "Current
context" field with anything that changed this week and the agents
need to know about. Examples:

- "Competitor X launched a 30%-off promo on May 5 — expect their CPCs
  to be high through end of month."
- "We're cutting Q3 budget by 25% starting June 1. Bias toward
  tightening, not expanding."
- "New product line *Acme Pro* launches June 10 — campaigns prefixed
  `acme-pro-` should not be paused even if early CPA is high."

The agents read this profile on every run. Two minutes typing here
saves five hours of fixing wrong-decisions later.

### Step 6 — Weekly note to the owner (10 min)

In the shared channel:
> **AdVanta — weekly summary**
> - Spend: $X (week-over-week ±Y%)
> - Wins: [bullet list of ranked actions taken]
> - Stuck on: [anything escalated, awaiting owner decision]
> - Asks: [budget changes, new context, anything needing owner action]
> - Next week's plan: [3-bullet preview]

---

## Monthly routine (3–5 hours, run on the 1st)

The monthly shift is where strategy enters. It's the closest analog to
what a Mega AI account manager would do on a monthly client call.

### Step 1 — Generate and study the monthly report (45 min)

1. `/reports` → period "Last 30 days" → **Generate report** → save the
   PDF to a shared drive labeled by month.
2. Annotate the PDF (any tool — Preview, Notion, Google Docs):
   - 3 things the agents got right that materially helped numbers
   - 3 things that didn't work and why
   - 1 surprise (positive or negative) that needs investigation

### Step 2 — Strategic alignment review (45 min)

Open `/growth-dna`. Read the Growth DNA profile end-to-end. Compare:

- The original goals (top of the page) vs. what actually happened in
  the last 30 days. Are we trending toward target CPA / ROAS /
  conversion volume?
- The recommended first campaigns from onboarding vs. what's actually
  running. Did the strategy drift? Is that drift good (we found
  something better) or bad (we got distracted)?
- The 30-day growth plan from the original DNA. Update or replace it
  for the next 30 days. Click **Regenerate** if the underlying
  business has shifted enough that the AI should re-derive the plan.

Output: a one-page "What we're doing in [Month]" document. This is
what the VA presents to the owner at the monthly check-in.

### Step 3 — Refresh the competitor + ICP context (30 min)

1. Open `/onboarding` → Competitors section. For each competitor, the
   VA spends 3–5 minutes:
   - Visit their site. Anything new? New pricing? New offer? New
     positioning?
   - Update the competitor row with the date and a one-line note.
2. Re-read the ICP and Persona output (`/agents` → Market Intelligence
   + ICP/Persona agent runs). If the company has signed a notably
   different customer profile in the last 30 days, update the ICP and
   re-run the Creative Strategy agent so future ad copy reflects it.

### Step 4 — Audit the Autopilot rules at the rule level (30 min)

Daily review catches *incidents*. Monthly review catches *drift*. Open
`/autopilot` → **Configuration**. For each guardrail:

- **Max daily budget shift**: still appropriate given current monthly
  budget? (If budget grew 50%, this should grow too.)
- **Stop-loss CPA**: still aligned with current target CPA?
- **Action allowlist**: any action types we should add now that we
  trust the agent more, or remove because they keep producing
  surprises?
- **Min confidence threshold**: any patterns of "agent was confident
  and still wrong"? If yes, raise the threshold.

### Step 5 — Costs + provider review (30 min)

1. Open `/settings/billing`. Read:
   - Current plan, current usage, days until reset.
   - LLM tokens used vs. quota. Cost in USD for the period.
2. Open `/settings/api-keys → Provider credentials`. For each saved
   provider key, click **Test**. Confirm all three are still valid.
   Rotate any key older than 90 days (revoke + add new).
3. Open `/settings/integrations`. For each provider:
   - Last sync timestamp should be < 24 hours.
   - No errored syncs.
   - If a token is about to expire (some providers don't auto-refresh),
     the VA reconnects it during this window — never on a Friday
     afternoon.

### Step 6 — Monthly readout to the owner (30 min)

A 30-minute call (or written memo, if the owner prefers async):

- 30-day numbers vs. plan
- What the agents did well, what didn't work, what surprised us
- What's changing next month and why
- Asks: budget changes, strategic direction, hires, new platforms

---

## Quarterly routine (4–8 hours, run in the first week of each quarter)

The quarterly shift is the strategic reset. Most of the work lives
outside the AdVanta dashboard — it's research, conversation, and
documentation.

### Step 1 — Refresh the Growth DNA from scratch (1 hr)

1. Open `/growth-dna` → click **Regenerate**. The orchestrator pulls
   the current onboarding profile, runs Market Intelligence + ICP +
   Creative Strategy from a clean slate, and produces a new 90-day
   plan.
2. Compare side-by-side with last quarter's plan. The diff *is* the
   strategic narrative — keep it for the owner.

### Step 2 — Channel mix review (1 hr)

Strategic question: are we on the right *channels*? AdVanta optimizes
*within* a channel; it doesn't decide whether you should be on
LinkedIn at all.

1. Pull the last 90 days of spend + conversions per channel from the
   monthly reports.
2. Compute cost per acquisition by channel. The cheapest one isn't
   always best — pair it with notes on lead quality from sales
   feedback.
3. Recommend to the owner: a channel to scale, a channel to pause,
   a channel to test net-new.

### Step 3 — Creative refresh (1–2 hrs)

1. Open `/creatives`. Sort by creation date — anything older than 60
   days is at risk of fatigue.
2. Open `/agents` → run the **Creative Strategy** agent with the
   updated ICP and brand voice. It produces a fresh creative brief +
   variant ideas.
3. Hand the brief to whoever produces actual creative (designer,
   founder, agency). The VA's job ends at the brief — they aren't
   producing ads themselves unless that's explicitly in scope.

### Step 4 — A/B testing roadmap (1 hr)

1. Open `/ab-tests`. Read the last 90 days of test outcomes.
2. List 5–10 tests to run next quarter, prioritized by expected
   impact. Common candidates:
   - Hero headline / subhead variants
   - CTA button text
   - Pricing presentation (monthly vs annual default)
   - Trust signals (logos, testimonials placement)
   - Lead form length
3. Schedule them across the quarter so no two compete for the same
   traffic.

### Step 5 — Tracking + attribution audit (1 hr)

1. Open `/agents` → run the **Tracking & Attribution** agent.
2. Read its output. Common findings:
   - Pixel firing on the wrong page
   - Conversion event misconfigured
   - UTM parameters inconsistent across campaigns
   - GA4 event names diverging from ad-platform conversion names
3. Each issue → a recommendation; approve and ship.

### Step 6 — Quarterly business review with the owner (1–2 hrs)

A real meeting. Suggested agenda:

1. **Numbers** (15 min) — what happened vs. plan
2. **Strategy** (30 min) — what's working, what isn't, what we're
   changing
3. **Asks** (15 min) — budget, hires, tooling, escalations
4. **Roadmap** (30 min) — next quarter's plan, locked in

Output: a 2-page memo the owner can forward to their board / spouse /
co-founder, summarizing what they're paying AdVanta + the VA to do.

---

## Ad-hoc / event-driven work (variable)

These are the situations where automation can't substitute for
judgment. The VA's job is to recognize them fast and either resolve
them or escalate.

### Provider policy rejection / account flag

Symptom: an agent run errors out with a provider-side rejection, OR
the platform sends a webhook event flagging an issue (e.g. ad
disapproved, account under review).

Steps:
1. Find the original recommendation in `/recommendations` — the
   execution row will have the provider's error message.
2. Read it. Common rejections:
   - Trademark issue → swap the offending word, re-submit.
   - Landing page violation → fix the landing page, re-submit.
   - Account-level flag (suspension, review) → escalate to owner
     immediately. The VA does not contact provider support directly
     unless authorized.
3. Document in the shared channel: what happened, what was done,
   whether it's resolved.

### Crisis: campaign goes wrong fast

Symptom: spend spikes, CPA explodes, conversions drop, all within
hours.

Steps:
1. Open `/campaigns` → sort by spend descending. Identify the
   offender.
2. **Pause it manually** via `/recommendations` → click the pause
   action on that campaign. Don't wait for the next agent run.
3. Open the campaign's audit log entries — what changed in the last
   24 hours? Was it a budget bump? A targeting change? A creative
   swap?
4. **Revert** the most recent change via the recommendation row's
   *Revert* button.
5. Notify the owner immediately with: campaign ID, what happened,
   what you did, what you think went wrong.

### New context: something material changed in the business

Examples: a price change, a new product launch, a key competitor
ad-launch, a regulatory shift, an upcoming holiday or sale, a PR
event.

Steps:
1. Update `/onboarding` → Current context field within the same day.
2. If the change is large (re-pricing, re-positioning), tag the
   owner and propose a re-run of the **Market Intelligence** and
   **Creative Strategy** agents.

### Provider rep / partner manager reaches out

Mega AI handles this in-house. AdVanta doesn't. The VA captures the
inbound and routes:
- "Performance review call" — schedule and forward to owner.
- "Beta program / feature invite" — forward to owner.
- "Account credit / refund" — forward to owner.
- "Compliance issue" — escalate immediately.

The VA never authorizes a budget change or accepts a beta on the
owner's behalf.

---

## Escalation playbook (use the same format every time)

When the VA escalates, use this template in the shared channel:

```
🟡 ESCALATION — AdVanta · [date]

What happened: [one sentence]
Where: [URL to the recommendation / campaign / audit entry]
Risk level: [low / medium / high]
What I tried: [one sentence, or "haven't acted yet"]
What I need from you: [decision / approval / context]
Decision deadline: [end of today / end of week / no rush]
```

Escalate, don't guess. A 30-second escalation is always cheaper than
a wrong action that has to be reverted.

---

## What this playbook does NOT cover

The VA is not expected to:
- Produce creative assets (copy, design, video) — only briefs.
- Negotiate provider billing, refunds, or beta access.
- Approve budget *increases* over the daily authority limit.
- Make pricing or positioning changes.
- Onboard new customers or run sales calls.
- Talk to the owner's board, investors, or accountant.

If a task lands in their queue that fits any of the above, they
escalate it instead of acting.

---

## Self-evaluation: am I doing this right?

End of each month, the VA scores themselves honestly on five things:

| Question | Target |
|---|---|
| % of recommendations decided within 24 hrs | ≥ 95% |
| Auto-approvals reverted | ≤ 10% |
| Escalations resolved within deadline | 100% |
| Owner asks "what's going on?" outside scheduled checkpoints | 0–1× per month |
| Material business context updated within the same day | yes / no |

If any of these slips for two months running, that's a signal to
re-read the playbook — or to bring in someone more senior for the
strategic layer while the VA stays focused on hygiene.

---

## Tooling the VA needs (besides AdVanta itself)

- A **password manager** entry for their AdVanta login (with 2FA).
- Access to the **shared escalation channel** (Slack, Discord, email
  thread — owner's choice).
- A **shared drive folder** for monthly + quarterly PDF reports.
- A simple **time tracker** so the actual hours spent are visible to
  the owner.
- Optional: a **note app** (Notion, Apple Notes, plain text) for
  weekly briefing-note drafts before they're posted.

---

## Hand-off note

This document plus the AdVanta dashboard is everything a competent VA
needs to keep an account healthy and growing without the owner being
in the weeds daily. The owner's job is what's left:
**strategic direction, creative direction, big budget calls, edge
cases the VA escalates, and the periodic reality-check that the
agents + rules are still pointed at the right goals.**

That's the 10–30%. The rest the agents do.
