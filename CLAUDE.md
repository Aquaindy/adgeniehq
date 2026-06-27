# CLAUDE.md — AdGenieHQ

## Project Name

**AdGenieHQ**

## Product Type

Production-ready SaaS application for AI-powered ads automation, SEO/GEO intelligence, website conversion analysis, and cross-platform growth optimization.

## Core Positioning

**AdGenieHQ — Turn Ad Chaos Into Intelligent Growth.**

AdGenieHQ is an AI Growth Command Center where businesses connect real ad accounts, analytics platforms, websites, and search data. Specialized AI Skill Agents analyze performance, discover wasted spend, generate recommendations, improve landing pages, strengthen SEO/GEO visibility, and help teams plan, launch, monitor, and optimize campaigns across platforms such as Google Ads, Meta Ads, LinkedIn Ads, and future ad networks.

This is not a demo app. This must be built as a commercial, production-ready SaaS from the start.

---

# 1. Non-Negotiable Production Rules

Claude Code must follow these rules throughout the entire build:

1. Do not create demo campaigns.
2. Do not create simulated ad platform data.
3. Do not create fake dashboard metrics.
4. Do not hardcode users, workspaces, campaigns, spend, clicks, leads, ROAS, CPA, or impressions.
5. Do not use fake API responses as real product behavior.
6. If an integration is not connected, show a clean empty state with a clear connection CTA.
7. All dashboards must use real database records, real user input, real third-party API data, or real saved AI outputs.
8. All agent outputs must be saved, traceable, and connected to a workspace.
9. All external actions must be logged in audit logs.
10. Any action that can spend money, increase budget, pause campaigns, modify campaigns, launch campaigns, or change tracking must require approval unless the workspace has explicitly enabled guarded Autopilot Mode.
11. All OAuth tokens must be encrypted at rest.
12. All secrets must live in environment variables only.
13. All API routes must enforce authentication, workspace isolation, and permission checks.
14. The app must be mobile responsive from the beginning.
15. The application must be built with scalable SaaS architecture, not a prototype mindset.

---

# 2. Technology Stack

## Backend

Use:

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Redis
- Celery or Dramatiq for background jobs
- Pydantic Settings
- JWT authentication
- OAuth2 integration framework
- Stripe billing
- OpenAI-compatible LLM abstraction layer
- Encrypted token storage
- Structured logging
- Pytest for tests

## Frontend

Use:

- React.js
- TypeScript
- Vite or Next.js. Prefer Vite React for app dashboard speed unless SEO-focused public pages are included in the same app.
- Tailwind CSS
- Shadcn/UI or Radix-style reusable components
- TanStack Query
- Zustand or lightweight state management
- React Hook Form + Zod
- Recharts or Tremor-style charts
- Framer Motion for tasteful transitions
- Mobile-first responsive design

## Optional Gateway

NestJS may be added later as an API gateway or enterprise BFF layer, but the first production build should prioritize:

- React frontend
- FastAPI backend
- PostgreSQL database
- Redis workers

Do not add NestJS unless it improves the architecture and does not slow down the production MVP.

---

# 3. Brand & UI Direction

## Primary Color

**Grape Jelly:** `#3E2F84`

## Supporting Palette

- Deep Night: `#111827`
- Cloud White: `#F9FAFB`
- Soft Lavender: `#EEEAFE`
- Electric Violet: `#7C3AED`
- Growth Green: `#16A34A`
- Warning Amber: `#F59E0B`
- Danger Red: `#DC2626`
- Slate Text: `#334155`

## Design Personality

The UI should feel:

- Premium
- Calm
- Executive
- Intelligent
- Automated
- Secure
- Modern
- Trustworthy
- Mobile-first

## UI Style Rules

Use:

- Clean SaaS dashboard layout
- White cards on light background
- Soft shadows
- Rounded corners
- Grape jelly gradients
- Clear data hierarchy
- Agent status indicators
- Approval buttons
- Recommendation cards
- Mobile bottom navigation where useful
- Responsive tables that collapse gracefully on mobile
- Empty states with action-oriented CTAs

Do not use cluttered visuals, gimmicky AI art, fake charts, or placeholder metrics.

---

# 4. Product Architecture

AdGenieHQ should use a **Master Orchestrator + AI Skill Agents** model.

The system is not one giant AI prompt. It is a coordinated agentic SaaS system where specialized agents act as Skills under a Master Growth Orchestrator.

## Core Concept

The user connects business data and ad platforms. The Master Growth Orchestrator understands the user’s goal, breaks it into tasks, assigns tasks to skill agents, stores outputs, creates recommendations, and routes sensitive actions through approval workflows.

Example user command:

> Launch a lead generation campaign for my SaaS app with a $2,000 monthly budget across Meta and Google.

The orchestrator should activate:

- Market Intelligence Agent
- ICP & Persona Agent
- Creative Strategy Agent
- Campaign Builder Agent
- Paid Ads Agent
- Tracking & Attribution Agent
- Budget Guardian Agent
- Reporting Agent

---

# 5. Main AI Agents as Skills

## 5.1 Master Growth Orchestrator

Responsibilities:

- Accept user goals and campaign requests
- Break requests into structured tasks
- Select the right Skill Agents
- Validate agent outputs
- Store task history
- Create recommendations
- Trigger approval workflows
- Enforce budget and safety rules
- Coordinate multi-agent workflows
- Prevent unsafe or unauthorized actions
- Produce final action plans

The orchestrator must never directly execute sensitive external platform changes without checking permissions, plan limits, safety rules, and approval status.

---

## 5.2 SEO & GEO Agent

Purpose:

Improve organic visibility across traditional search engines and AI answer engines.

Core skills:

- Keyword research
- Competitor SEO analysis
- Search intent mapping
- Content gap discovery
- Technical SEO audit
- Metadata recommendations
- Internal linking suggestions
- Schema recommendations
- Entity optimization
- FAQ generation
- GEO optimization for AI search visibility
- Content refresh recommendations
- Search Console opportunity analysis

Integrations:

- Google Search Console
- GA4
- Website crawler
- Sitemap parser
- Optional DataForSEO/Semrush/Ahrefs connector later

Outputs:

- SEO opportunity report
- GEO visibility report
- Content calendar
- Technical SEO fixes
- Keyword opportunity list
- Search visibility score

---

## 5.3 Paid Ads Agent

Purpose:

Plan, monitor, and optimize paid advertising campaigns across connected ad platforms.

Supported platforms for initial architecture:

- Google Ads
- Meta Ads
- LinkedIn Ads

Future platforms:

- TikTok Ads
- Microsoft Ads
- X Ads
- Pinterest Ads

Core skills:

- Campaign planning
- Account performance analysis
- Budget allocation recommendations
- Keyword and audience strategy
- Ad structure recommendations
- Ad copy recommendations
- Creative test planning
- Campaign anomaly detection
- Budget waste detection
- CPA/ROAS monitoring
- Scaling suggestions
- Pause/boost recommendations
- Cross-platform comparison

Execution modes:

1. Advisor Mode — recommendations only.
2. Approval Mode — AI proposes, user approves.
3. Autopilot Mode — AI executes within strict rules and limits.

Default mode must be Approval Mode or Advisor Mode. Do not default to Autopilot Mode.

---

## 5.4 Website Agent

Purpose:

Improve website and landing page conversion performance.

Core skills:

- Website audit
- Landing page audit
- Mobile responsiveness check
- Page speed recommendations
- CTA clarity analysis
- Above-the-fold diagnosis
- Copy clarity scoring
- Offer clarity analysis
- Trust signal recommendations
- Form friction detection
- A/B test ideas
- Conversion improvement roadmap

Integrations:

- Website crawler
- Lighthouse/PageSpeed API
- GA4
- Optional Microsoft Clarity/Hotjar later

Outputs:

- Website health score
- Landing page conversion score
- Mobile UX score
- Speed recommendations
- Copy improvement recommendations
- A/B testing roadmap

---

## 5.5 Market Intelligence Agent

Purpose:

Understand market conditions before campaigns are launched or optimized.

Core skills:

- Competitor discovery
- Competitor positioning analysis
- Offer analysis
- Audience pain point extraction
- Trend detection
- Pricing comparison
- Category gap discovery
- Campaign opportunity mapping

Outputs:

- Market map
- Competitor matrix
- Positioning gaps
- Campaign angle recommendations
- Audience opportunity notes

---

## 5.6 ICP & Persona Agent

Purpose:

Build high-quality customer profiles for ad targeting, messaging, and landing pages.

Core skills:

- ICP generation
- Persona creation
- Pain point mapping
- Buying trigger analysis
- Objection mapping
- Awareness stage mapping
- Segment scoring
- Platform targeting suggestions

Outputs:

- ICP profile
- Buyer personas
- Messaging matrix
- Audience segment recommendations

---

## 5.7 Creative Strategy Agent

Purpose:

Generate campaign angles, copy ideas, video scripts, and creative briefs.

Core skills:

- Ad hook generation
- Story-based ad angles
- Founder-led scripts
- UGC-style scripts
- Static ad concepts
- Carousel ad concepts
- Short-form video scripts
- Creative testing matrix
- Fatigue detection based on performance data

Outputs:

- Ad copy variations
- Creative briefs
- Hook library
- Video scripts
- Creative testing roadmap

---

## 5.8 Campaign Builder Agent

Purpose:

Turn strategy into platform-ready campaign structures.

Core skills:

- Campaign objective selection
- Campaign naming conventions
- Campaign structure generation
- Ad group/ad set planning
- Audience mapping
- Budget allocation
- Keyword grouping
- Conversion event selection
- Tracking checklist

Outputs:

- Campaign blueprint
- Platform-specific structure
- Launch checklist
- Approval-ready campaign plan

---

## 5.9 Tracking & Attribution Agent

Purpose:

Ensure campaign measurement is trustworthy.

Core skills:

- Pixel validation
- Conversion event mapping
- UTM generation
- GA4 event review
- Funnel tracking review
- Attribution comparison
- Missing event detection
- Broken tracking detection
- Tag quality scoring

Integrations:

- GA4
- Google Tag Manager
- Meta Pixel
- Meta CAPI
- Google Ads conversion tracking
- LinkedIn Insight Tag

Outputs:

- Tracking health score
- Missing event warnings
- UTM builder outputs
- Attribution report

---

## 5.10 Budget Guardian Agent

Purpose:

Protect users from wasted spend and unsafe campaign changes.

Core skills:

- Budget pacing
- Overspend detection
- CPA spike detection
- ROAS drop detection
- Fatigue alerts
- Anomaly detection
- Stop-loss recommendations
- Risk scoring
- Autopilot rule enforcement

Outputs:

- Budget risk alerts
- Pause recommendations
- Daily spend forecast
- Budget pacing score
- Campaign safety notes

---

## 5.11 Reporting Agent

Purpose:

Turn data into clear, executive-level insights.

Core skills:

- Daily summaries
- Weekly reports
- Monthly reports
- Campaign change logs
- Before/after analysis
- Client-ready report generation
- PDF export
- Email summary generation

Outputs:

- Daily growth summary
- Weekly report
- Monthly executive report
- PDF reports
- Shareable summaries

---

# 6. Core User Roles

Create role-based access control from the start.

Roles:

1. Owner
2. Admin
3. Marketer
4. Analyst
5. Viewer

Permissions must control:

- Workspace management
- Billing access
- Integration connection
- Agent execution
- Recommendation approval
- Campaign modification
- Reporting access
- Team invitations
- API key management

---

# 7. Core Product Modules

## 7.1 Authentication

Build:

- Email/password signup
- Email/password login
- Secure password hashing
- JWT access tokens
- Refresh token support
- Password reset
- Email verification foundation
- Optional Google OAuth login later

## 7.2 Workspaces

Build:

- Workspace creation
- Workspace switching
- Workspace settings
- Workspace members
- Role management
- Workspace-level billing
- Workspace-level connected accounts

## 7.3 Onboarding

Collect:

- Business name
- Website URL
- Industry
- Target audience
- Offer/product description
- Monthly ad budget
- Primary conversion goal
- Geographic target
- Current ad platforms
- Competitors
- Brand voice
- Landing page URLs
- Analytics status
- Current growth pain points

After onboarding, generate and store a **Growth DNA Profile**.

## 7.4 Growth DNA Profile

The Growth DNA Profile should include:

- Business summary
- ICP summary
- Offer positioning
- Funnel readiness score
- Paid ads readiness score
- SEO/GEO opportunity summary
- Website conversion risks
- Tracking readiness
- Recommended first campaigns
- 30-day growth plan

## 7.5 Agent Dashboard

Show:

- Agent cards
- Agent status
- Last activity
- Current task
- Pending approvals
- Latest recommendation
- Impact summary

## 7.6 Command Center Dashboard

Show:

- Growth score
- Connected account status
- Active campaigns
- Spend today
- Leads/conversions
- CPA
- ROAS
- Conversion rate
- SEO visibility
- GEO visibility
- Website health
- Active agent tasks
- Critical alerts
- Recommended next actions

If there is no real data, show empty states.

## 7.7 Campaigns Dashboard

Show:

- Cross-platform campaign list
- Platform filter
- Objective filter
- Budget filter
- Status filter
- Campaign metrics
- AI recommendations
- Approval status

## 7.8 Recommendations Center

Every recommendation must include:

- Title
- Summary
- Agent source
- What the AI found
- Why it matters
- Expected impact
- Risk level
- Related platform
- Related campaign if applicable
- Suggested action
- Approve button
- Reject button
- Edit before applying button
- Audit trail

## 7.9 Integrations Center

Show real connection status for:

- Google Ads
- Meta Ads
- LinkedIn Ads
- GA4
- Google Search Console
- Google Tag Manager
- Stripe

For disconnected accounts, show a connect button.

## 7.10 Reports Center

Build:

- Daily report view
- Weekly report view
- Monthly report view
- PDF export
- CSV export where appropriate
- Shareable report link foundation
- Email report foundation

## 7.11 Billing

Build:

- Stripe checkout
- Stripe customer portal
- Subscription plan table
- Trial support
- Usage event tracking
- Plan limits
- Billing status checks

---

# 8. Data Model Requirements

Use PostgreSQL with SQLAlchemy models and Alembic migrations.

## Required Tables

Create models for:

- users
- workspaces
- workspace_members
- roles
- permissions
- connected_accounts
- oauth_tokens
- ad_platform_accounts
- websites
- landing_pages
- campaigns
- ad_groups
- ads
- creatives
- seo_projects
- keywords
- competitors
- growth_goals
- growth_dna_profiles
- agent_runs
- agent_tasks
- skill_outputs
- recommendations
- approvals
- reports
- notifications
- audit_logs
- billing_customers
- billing_subscriptions
- usage_events
- api_keys

## Important Model Notes

### AgentRun

Must store:

- id
- workspace_id
- agent_type
- status
- input_payload
- output_payload
- model_used
- token_usage
- estimated_cost
- started_at
- completed_at
- error_message

### Recommendation

Must store:

- id
- workspace_id
- agent_run_id
- title
- summary
- recommendation_type
- risk_level
- expected_impact
- suggested_action
- status
- platform
- campaign_id nullable
- metadata
- created_at

### Approval

Must store:

- id
- workspace_id
- recommendation_id
- action_type
- risk_level
- status
- approved_by
- approved_at
- rejected_by
- rejected_at
- execution_result

### AuditLog

Must store:

- id
- workspace_id
- actor_type
- actor_id
- action
- resource_type
- resource_id
- metadata
- ip_address
- user_agent
- created_at

### ConnectedAccount

Must store:

- id
- workspace_id
- provider
- provider_account_id
- display_name
- status
- scopes
- connected_by
- connected_at
- last_sync_at

### OAuthToken

Must store encrypted tokens only:

- id
- connected_account_id
- encrypted_access_token
- encrypted_refresh_token
- expires_at
- scopes
- created_at
- updated_at

---

# 9. Backend Folder Structure

Create this structure:

```text
apps/api/
├── app/
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   ├── celery_app.py
│   │   └── security_settings.py
│   │
│   ├── db/
│   │   ├── session.py
│   │   ├── base.py
│   │   └── init_db.py
│   │
│   ├── models/
│   ├── schemas/
│   ├── api/
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── users.py
│   │       ├── workspaces.py
│   │       ├── onboarding.py
│   │       ├── integrations.py
│   │       ├── campaigns.py
│   │       ├── agents.py
│   │       ├── recommendations.py
│   │       ├── approvals.py
│   │       ├── reports.py
│   │       ├── billing.py
│   │       └── health.py
│   │
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── workspace_service.py
│   │   ├── billing_service.py
│   │   ├── recommendation_service.py
│   │   └── audit_service.py
│   │
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── base_agent.py
│   │   ├── seo_geo_agent.py
│   │   ├── paid_ads_agent.py
│   │   ├── website_agent.py
│   │   ├── market_intelligence_agent.py
│   │   ├── icp_persona_agent.py
│   │   ├── creative_strategy_agent.py
│   │   ├── campaign_builder_agent.py
│   │   ├── tracking_attribution_agent.py
│   │   ├── budget_guardian_agent.py
│   │   └── reporting_agent.py
│   │
│   ├── skills/
│   │   ├── registry.py
│   │   ├── base_skill.py
│   │   ├── keyword_research_skill.py
│   │   ├── campaign_planning_skill.py
│   │   ├── ad_copy_skill.py
│   │   ├── landing_page_audit_skill.py
│   │   ├── budget_pacing_skill.py
│   │   ├── tracking_validation_skill.py
│   │   ├── seo_audit_skill.py
│   │   └── report_generation_skill.py
│   │
│   ├── integrations/
│   │   ├── google_ads/
│   │   ├── meta_ads/
│   │   ├── linkedin_ads/
│   │   ├── google_analytics/
│   │   ├── google_search_console/
│   │   ├── paddle_billing.py
│   │   └── email/
│   │
│   ├── workers/
│   │   ├── agent_jobs.py
│   │   ├── sync_jobs.py
│   │   ├── reporting_jobs.py
│   │   └── optimization_jobs.py
│   │
│   ├── security/
│   │   ├── auth.py
│   │   ├── encryption.py
│   │   ├── permissions.py
│   │   ├── rate_limit.py
│   │   └── oauth.py
│   │
│   └── utils/
│       ├── pagination.py
│       ├── dates.py
│       └── validators.py
│
├── alembic/
├── tests/
├── pyproject.toml
├── main.py
└── README.md
```

---

# 10. Frontend Folder Structure

Create this structure:

```text
apps/web/
├── src/
│   ├── app/
│   ├── components/
│   │   ├── ui/
│   │   ├── layout/
│   │   ├── dashboard/
│   │   ├── agents/
│   │   ├── campaigns/
│   │   ├── recommendations/
│   │   ├── integrations/
│   │   ├── reports/
│   │   └── forms/
│   │
│   ├── features/
│   │   ├── auth/
│   │   ├── onboarding/
│   │   ├── dashboard/
│   │   ├── agents/
│   │   ├── campaigns/
│   │   ├── recommendations/
│   │   ├── integrations/
│   │   ├── billing/
│   │   ├── reports/
│   │   └── settings/
│   │
│   ├── hooks/
│   ├── lib/
│   │   ├── api-client.ts
│   │   ├── auth.ts
│   │   ├── constants.ts
│   │   ├── routes.ts
│   │   └── utils.ts
│   │
│   ├── stores/
│   │   ├── auth-store.ts
│   │   ├── workspace-store.ts
│   │   └── ui-store.ts
│   │
│   ├── styles/
│   │   └── globals.css
│   │
│   └── types/
│       ├── api.ts
│       ├── auth.ts
│       ├── workspace.ts
│       ├── agents.ts
│       └── campaigns.ts
│
├── public/
├── package.json
├── tailwind.config.js
└── vite.config.ts
```

---

# 11. Monorepo Structure

Create:

```text
adgeniehq/
├── apps/
│   ├── web/
│   └── api/
│
├── packages/
│   ├── shared-types/
│   ├── ui/
│   └── config/
│
├── docs/
│   ├── architecture.md
│   ├── api-contracts.md
│   ├── agent-system.md
│   ├── integrations.md
│   ├── security.md
│   └── deployment.md
│
├── infra/
│   ├── render/
│   ├── nginx/
│   └── docker/
│
├── .env.example
├── CLAUDE.md
├── README.md
└── .gitignore
```

---

# 12. Required API Routes

Use `/api/v1` as the backend prefix.

## Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/confirm`

## Workspaces

- `GET /api/v1/workspaces`
- `POST /api/v1/workspaces`
- `GET /api/v1/workspaces/{workspace_id}`
- `PATCH /api/v1/workspaces/{workspace_id}`
- `GET /api/v1/workspaces/{workspace_id}/members`
- `POST /api/v1/workspaces/{workspace_id}/members/invite`
- `PATCH /api/v1/workspaces/{workspace_id}/members/{member_id}`

## Onboarding

- `GET /api/v1/workspaces/{workspace_id}/onboarding`
- `POST /api/v1/workspaces/{workspace_id}/onboarding`
- `POST /api/v1/workspaces/{workspace_id}/growth-dna/generate`
- `GET /api/v1/workspaces/{workspace_id}/growth-dna`

## Agents

- `GET /api/v1/workspaces/{workspace_id}/agents`
- `POST /api/v1/workspaces/{workspace_id}/agents/run`
- `GET /api/v1/workspaces/{workspace_id}/agents/runs`
- `GET /api/v1/workspaces/{workspace_id}/agents/runs/{run_id}`
- `GET /api/v1/workspaces/{workspace_id}/agents/tasks`

## Recommendations

- `GET /api/v1/workspaces/{workspace_id}/recommendations`
- `GET /api/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}`
- `POST /api/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/approve`
- `POST /api/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}/reject`
- `PATCH /api/v1/workspaces/{workspace_id}/recommendations/{recommendation_id}`

## Integrations

- `GET /api/v1/workspaces/{workspace_id}/integrations`
- `GET /api/v1/workspaces/{workspace_id}/integrations/{provider}/connect-url`
- `GET /api/v1/integrations/{provider}/callback`
- `POST /api/v1/workspaces/{workspace_id}/integrations/{provider}/disconnect`
- `POST /api/v1/workspaces/{workspace_id}/integrations/{provider}/sync`

## Campaigns

- `GET /api/v1/workspaces/{workspace_id}/campaigns`
- `GET /api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}`
- `GET /api/v1/workspaces/{workspace_id}/campaigns/summary`
- `POST /api/v1/workspaces/{workspace_id}/campaigns/sync`

## Reports

- `GET /api/v1/workspaces/{workspace_id}/reports`
- `POST /api/v1/workspaces/{workspace_id}/reports/generate`
- `GET /api/v1/workspaces/{workspace_id}/reports/{report_id}`
- `GET /api/v1/workspaces/{workspace_id}/reports/{report_id}/download`

## Billing

- `GET /api/v1/workspaces/{workspace_id}/billing/status`
- `POST /api/v1/workspaces/{workspace_id}/billing/checkout-session`
- `POST /api/v1/workspaces/{workspace_id}/billing/portal-session`
- `POST /api/v1/billing/webhook`

## Health

- `GET /api/v1/health`
- `GET /api/v1/health/db`
- `GET /api/v1/health/redis`

---

# 13. Integration Requirements

Build integrations using real OAuth flows. Do not simulate connected accounts.

## Initial Integrations

1. Google Ads
2. Meta Ads
3. LinkedIn Ads
4. Google Analytics 4
5. Google Search Console
6. Stripe

## Integration Rules

- Store provider connection status.
- Encrypt tokens at rest.
- Refresh expired OAuth tokens where supported.
- Log sync attempts.
- Store sync errors.
- Show integration health in the UI.
- Never expose access tokens to the frontend.
- Use backend API routes for all provider calls.

---

# 14. Approval & Autopilot Safety System

The app must include three modes.

## Advisor Mode

AI only analyzes and recommends. No external actions.

## Approval Mode

AI recommends actions. User must approve before execution.

## Autopilot Mode

AI can execute approved categories of actions within strict limits.

Autopilot must require:

- Explicit workspace opt-in
- Max daily budget setting
- Max percentage budget increase
- Min conversion threshold
- Stop-loss rules
- Risk limit
- Audit logging
- Easy disable button

Actions requiring approval by default:

- Launching campaigns
- Increasing campaign budgets
- Pausing major campaigns
- Editing campaign objectives
- Editing conversion events
- Changing tracking settings
- Deleting anything
- Connecting or disconnecting integrations

---

# 15. Security Requirements

Implement:

- JWT authentication
- Password hashing with bcrypt or argon2
- Refresh token strategy
- Workspace isolation
- RBAC permissions
- OAuth token encryption
- Secure CORS configuration
- Rate limiting
- Request validation
- Webhook signature verification
- SQL injection protection through ORM
- Audit logging
- Centralized error handling
- Environment-based config
- Secrets never committed
- Secure production cookie/session settings if cookies are used
- API response sanitization

---

# 16. Environment Variables

Create `.env.example` with:

```env
APP_NAME=AdGenieHQ
APP_ENV=development
APP_DEBUG=true
APP_SECRET_KEY=replace-with-secure-secret
API_V1_PREFIX=/api/v1

DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/adgeniehq_ai
REDIS_URL=redis://localhost:6379/0

CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

ENCRYPTION_KEY=replace-with-fernet-key

OPENAI_API_KEY=
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4-mini

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_LOGIN_CUSTOMER_ID=

META_APP_ID=
META_APP_SECRET=

LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=

PADDLE_API_KEY=
PADDLE_CLIENT_TOKEN=
PADDLE_WEBHOOK_SECRET=
PADDLE_ENVIRONMENT=sandbox
PADDLE_PRICE_ID_STARTER=
PADDLE_PRICE_ID_PRO=
PADDLE_PRICE_ID_AGENCY=
PADDLE_PRICE_ID_STARTER_ANNUAL=
PADDLE_PRICE_ID_PRO_ANNUAL=
PADDLE_PRICE_ID_AGENCY_ANNUAL=

FRONTEND_URL=http://localhost:5173
BACKEND_URL=http://localhost:8000
```

---

# 17. Frontend Pages

Build these pages:

## Public Pages

- Landing page
- Pricing page
- Login page
- Register page
- Forgot password page
- Terms page
- Privacy page

## Authenticated App Pages

- Workspace selector
- Onboarding wizard
- Command Center Dashboard
- Agents Dashboard
- Recommendations Center
- Campaigns Dashboard
- SEO & GEO Dashboard
- Website Intelligence Dashboard
- Integrations Center
- Reports Center
- Billing page
- Team settings
- Workspace settings
- User profile

---

# 18. Empty State Requirements

Every empty state must be useful.

Examples:

## No Ad Account Connected

Show:

- Clear headline
- Brief explanation
- Connect Google Ads button
- Connect Meta Ads button
- Connect LinkedIn Ads button
- Link to integration docs

Do not show fake charts.

## No Campaign Data

Show:

- Real message explaining no campaigns were found
- Sync button if account is connected
- Create campaign plan CTA

## No Reports

Show:

- Generate report CTA
- Explain reports require connected data or completed agent runs

---

# 19. Milestone-Based Development Plan

## Milestone 1 — Foundation

Build:

- Monorepo structure
- FastAPI backend
- React frontend
- Tailwind theme with Grape Jelly primary color
- PostgreSQL connection
- Redis connection
- SQLAlchemy setup
- Alembic setup
- Environment config
- Health routes
- Basic app shell
- Mobile responsive layout

Deliverable:

A running full-stack app with backend health checks and frontend shell.

---

## Milestone 2 — Authentication & Workspaces

Build:

- User model
- Workspace model
- Workspace members
- Roles and permissions
- Register/login/logout
- JWT auth
- Protected routes
- Workspace creation
- Workspace switcher
- User profile

Deliverable:

Users can sign up, log in, create a workspace, and access protected dashboard pages.

---

## Milestone 3 — Onboarding & Growth DNA

Build:

- Multi-step onboarding wizard
- Business profile storage
- Website URL input
- Goals and budget settings
- Competitor input
- Brand voice input
- Growth DNA Profile model
- AI generation endpoint
- Growth DNA UI

Deliverable:

User completes onboarding and receives a saved AI-generated Growth DNA Profile.

---

## Milestone 4 — Agent & Skill System

Build:

- Base Agent class
- Base Skill class
- Skill registry
- Master Growth Orchestrator
- AgentRun model
- AgentTask model
- SkillOutput model
- Recommendation model
- Agent dashboard
- Agent run details page

Deliverable:

Agents can run real tasks based on user/workspace data, save outputs, and display results.

---

## Milestone 5 — Recommendations & Approvals

Build:

- Recommendation Center
- Approval model
- Approve/reject endpoints
- Risk levels
- Approval status UI
- Audit logs
- Action summary cards

Deliverable:

AI recommendations can be reviewed, approved, rejected, and audited.

---

## Milestone 6 — Integration Framework

Build:

- ConnectedAccount model
- OAuthToken model
- Token encryption
- OAuth connection framework
- Provider status UI
- Sync logs
- Disconnect flow

Initial provider shells with real OAuth foundation:

- Google Ads
- Meta Ads
- LinkedIn Ads
- GA4
- Search Console

Deliverable:

Users can connect real accounts through OAuth foundation. Disconnected accounts show useful empty states.

---

## Milestone 7 — Paid Ads Agent MVP

Build:

- Campaign sync model
- Campaign list UI
- Google Ads campaign ingestion foundation
- Meta Ads campaign ingestion foundation
- LinkedIn Ads campaign ingestion foundation
- Paid Ads Agent analysis workflow
- Budget Guardian risk checks
- Paid ads recommendations

Deliverable:

Users can view real synced campaign records and receive AI-generated optimization recommendations.

---

## Milestone 8 — SEO & GEO Agent MVP

Build:

- Search Console data sync foundation
- Website crawler
- Sitemap parser
- Keyword opportunity model
- SEO audit skill
- GEO recommendation skill
- SEO/GEO dashboard

Deliverable:

User can analyze real website/search data and receive SEO/GEO recommendations.

---

## Milestone 9 — Website Agent MVP

Build:

- Landing page model
- Landing page audit workflow
- Page speed/Lighthouse integration foundation
- Mobile UX checklist
- CTA analysis
- Copy improvement recommendations
- Website Intelligence dashboard

Deliverable:

Users can audit landing pages and receive conversion improvement recommendations.

---

## Milestone 10 — Reporting

Build:

- Report model
- Daily report generator
- Weekly report generator
- Monthly report generator
- Report dashboard
- PDF export
- CSV export for tables
- Email report foundation

Deliverable:

Users can generate real reports based on connected data and saved AI outputs.

---

## Milestone 11 — Billing

Build:

- Stripe customer creation
- Stripe checkout
- Stripe webhook handling
- Subscription model
- Plan limits
- Billing page
- Customer portal
- Usage tracking

Deliverable:

AdGenieHQ can charge customers and enforce plan limits.

---

## Milestone 12 — Production Hardening

Build:

- Tests
- Error handling
- Rate limiting
- API docs
- Deployment docs
- Logging
- Monitoring hooks
- Backup notes
- Security review
- Final responsive QA
- Admin dashboard foundation

Deliverable:

Production-ready SaaS build prepared for deployment.

---

# 20. Testing Requirements

Create tests for:

- Auth routes
- Workspace isolation
- Permission checks
- Agent run creation
- Recommendation approvals
- Integration connection records
- Token encryption/decryption
- Billing webhook handling
- Campaign sync service boundaries
- Empty state logic where applicable

Use Pytest for backend.

For frontend:

- Component tests where practical
- Form validation tests
- Route protection checks
- Mobile responsiveness manual QA checklist

---

# 21. Documentation Requirements

Create docs:

- `docs/architecture.md`
- `docs/api-contracts.md`
- `docs/agent-system.md`
- `docs/integrations.md`
- `docs/security.md`
- `docs/deployment.md`
- `docs/local-development.md`

Docs must explain how to run the app locally and how to configure required environment variables.

---

# 22. Deployment Direction

Prepare for deployment on Render, Railway, or VPS.

Include:

- Backend deployment instructions
- Frontend deployment instructions
- PostgreSQL setup
- Redis setup
- Environment variable checklist
- CORS production setup
- Stripe webhook setup
- OAuth redirect URL setup
- Worker deployment
- Migration command

Production CORS example:

```env
CORS_ORIGINS=["https://app.adgeniehq.com","https://adgeniehq.com"]
```

Use actual production domain once chosen.

---

# 23. Final Product Experience

When a user logs into AdGenieHQ, the product should feel like a living growth command center.

The app should communicate:

- Your ad spend is being watched.
- Your website is being studied.
- Your SEO/GEO opportunities are being uncovered.
- Your campaigns are being protected from waste.
- Your next best growth move is becoming clearer.

The experience should be inspiring, but operationally serious.

AdGenieHQ should feel like an always-awake growth team, not a simple dashboard.

---

# 24. First Build Instruction to Claude Code

Start with Milestone 1 only.

Do not jump ahead.

Build the foundation cleanly:

1. Create the monorepo.
2. Create the FastAPI backend.
3. Create the React frontend.
4. Add Tailwind CSS with the Grape Jelly brand system.
5. Add PostgreSQL and Redis configuration.
6. Add health routes.
7. Add a responsive app shell.
8. Add clean documentation for local setup.

After Milestone 1 is complete, stop and provide:

- Summary of files created
- Setup instructions
- Commands to run backend
- Commands to run frontend
- Any environment variables needed
- Next recommended milestone

