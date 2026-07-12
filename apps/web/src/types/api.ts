export type Role = "owner" | "admin" | "marketer" | "analyst" | "viewer";
export type MemberStatus = "active" | "pending" | "disabled";

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  email_verified_at: string | null;
  created_at: string;
  two_factor_enabled?: boolean;
  google_subject?: string | null;
};

// ---- Ad hierarchy ----

export type AdGroupStatus = "active" | "paused" | "ended" | "archived";
export type AdStatus = "active" | "paused" | "ended" | "rejected" | "archived";
export type CreativeType =
  | "search_ad"
  | "responsive_display"
  | "single_image"
  | "video"
  | "carousel"
  | "ugc"
  | "other";
export type CreativeSource = "platform_synced" | "ai_generated" | "user_uploaded";
export type AdObjectSource = "platform_synced" | "advanta_draft";

export type SuggestedCopyType =
  | "keywords"
  | "ad_copy"
  | "landing_page"
  | "email"
  | "social_post"
  | "blog_outline"
  | "meta_tags"
  | "short_video_script";

export interface SuggestedCopy {
  id: string;
  workspace_id: string;
  growth_dna_profile_id: string | null;
  product_name: string;
  copy_type: SuggestedCopyType;
  section: string;
  title: string;
  body: string;
  /** Organic social only: catalog slug (e.g. "linkedin", "tiktok"). */
  platform: string | null;
  hashtags: string[] | null;
  source: string;
  model_used: string | null;
  created_at: string;
}

export type AdGroupTargeting = {
  locations?: string[];
  age_min?: number | null;
  age_max?: number | null;
  genders?: string[];
  interests?: string[];
  keywords?: string[];
  optimization_goal?: string | null;
  notes?: string | null;
};

export type AdGroup = {
  id: string;
  workspace_id: string;
  campaign_id: string;
  external_id: string | null;
  source: AdObjectSource;
  name: string;
  status: AdGroupStatus;
  daily_budget_cents: number | null;
  targeting: AdGroupTargeting | null;
  last_synced_at: string;
  created_at: string;
};

export type Ad = {
  id: string;
  workspace_id: string;
  campaign_id: string;
  ad_group_id: string;
  creative_id: string | null;
  external_id: string | null;
  source: AdObjectSource;
  name: string;
  status: AdStatus;
  landing_page_url: string | null;
  last_synced_at: string;
  created_at: string;
};

export type Creative = {
  id: string;
  workspace_id: string;
  type: CreativeType;
  source: CreativeSource;
  title: string | null;
  primary_text: string | null;
  headline: string | null;
  description: string | null;
  cta: string | null;
  image_url: string | null;
  video_url: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type CreativeUpdateRequest = {
  title?: string;
  primary_text?: string;
  headline?: string;
  description?: string;
  cta?: string;
  image_url?: string;
  video_url?: string;
};


// ---- 2FA ----

export type TwoFactorSetupResponse = {
  secret: string;
  provisioning_uri: string;
  issuer: string;
};

export type TwoFactorConfirmResponse = {
  recovery_codes: string[];
};

// ---- Admin (M12) ----

export type AdminOverview = {
  users_total: number;
  superusers_total: number;
  workspaces_total: number;
  paid_workspaces_total: number;
  agent_runs_total: number;
  agent_runs_last_7d: number;
  recommendations_open: number;
  integrations_connected: number;
  landing_pages_total: number;
  reports_generated_last_7d: number;
  // Phase A-D + ops surface
  executions_total: number;
  executions_succeeded_last_7d: number;
  content_drafts_total: number;
  content_drafts_published_last_7d: number;
  outreach_emails_sent_last_7d: number;
  outreach_prospects_total: number;
  ab_tests_active: number;
  ab_tests_completed_last_7d: number;
};

export type AdminWorkspaceRow = {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  member_count: number;
  plan_code: string;
  subscription_status: string;
};

export type AdminUserRow = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  workspace_count: number;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
};

export type Workspace = {
  id: string;
  name: string;
  slug: string;
  created_at: string;
};

export type WorkspaceMembership = Workspace & {
  role: Role;
  status: MemberStatus;
};

export type Member = {
  id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  role: Role;
  status: MemberStatus;
  created_at: string;
};

export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
};

export type AnalyticsStatus = "configured" | "partial" | "none" | "unknown";

export type AdPlatform =
  | "google_ads"
  | "meta_ads"
  | "linkedin_ads"
  | "tiktok_ads"
  | "microsoft_ads"
  | "x_ads"
  | "pinterest_ads"
  | "other";

export type CompetitorEntry = { name: string; url?: string | null };

export type OnboardingProfile = {
  id: string;
  workspace_id: string;
  business_name: string | null;
  website_url: string | null;
  industry: string | null;
  target_audience: string | null;
  offer_description: string | null;
  pain_points: string | null;
  primary_conversion_goal: string | null;
  monthly_ad_budget_min_usd: number | null;
  monthly_ad_budget_max_usd: number | null;
  geographic_target: string | null;
  current_ad_platforms: AdPlatform[] | null;
  landing_page_urls: string[] | null;
  analytics_status: AnalyticsStatus | null;
  competitors: CompetitorEntry[] | null;
  brand_voice: string | null;
  step_completed: number;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type OnboardingUpdate = Partial<
  Omit<OnboardingProfile, "id" | "workspace_id" | "step_completed" | "completed_at" | "created_at" | "updated_at">
> & {
  step_completed?: number;
  mark_completed?: boolean;
};

export type CampaignSuggestion = {
  platform: string;
  objective: string;
  budget_share_pct: number;
  rationale: string;
};

export type GrowthPlanWeek = {
  week: number;
  focus: string;
  deliverables: string[];
};

export type ChannelStrategy = {
  channel: string;
  category: "paid" | "owned" | "earned" | "foundation" | string;
  priority: "high" | "medium" | "low" | string;
  status: "ready" | "needs_setup" | "recommended" | string;
  cadence: string;
  summary: string;
  tactics: string[];
  kpis: string[];
  first_step: string;
};

export type ContentPillar = {
  name: string;
  allocation_pct: number;
  description: string;
  example_hooks: string[];
};

export type PlatformPlan = {
  platform: string;
  cadence: string;
  focus: string;
  best_for: string;
};

export type EmailFlow = {
  name: string;
  trigger: string;
  goal: string;
};

export type EmailStrategy = {
  summary: string;
  newsletter_cadence: string;
  flows: EmailFlow[];
  kpis: string[];
};

export type CalendarEntry = {
  day: number;
  channel: string;
  format: string;
  pillar: string;
  hook: string;
  caption_direction: string;
};

export type BudgetAllocation = {
  channel: string;
  pct: number;
  rationale: string;
};

export type MarketingStrategy = {
  overview: {
    model: string;
    thesis: string;
    priorities: string[];
    budget_allocation: BudgetAllocation[];
  };
  channels: ChannelStrategy[];
  content_pillars: ContentPillar[];
  platform_strategy: PlatformPlan[];
  email_strategy: EmailStrategy;
  content_calendar: CalendarEntry[];
  source: "deterministic" | "ai" | string;
  model_used: string | null;
  enrichment?: "pending" | "enriched" | "skipped" | null;
};

export type GrowthDna = {
  id: string;
  workspace_id: string;
  onboarding_profile_id: string;
  label: string | null;
  business_summary: string;
  icp_summary: string;
  offer_positioning: string;
  funnel_readiness_score: number;
  paid_ads_readiness_score: number;
  seo_geo_opportunity_summary: string;
  website_conversion_risks: string[];
  tracking_readiness: string;
  recommended_first_campaigns: CampaignSuggestion[];
  thirty_day_growth_plan: GrowthPlanWeek[];
  marketing_strategy: MarketingStrategy;
  engine_version: string;
  created_at: string;
};

export type GrowthDnaSummary = {
  id: string;
  workspace_id: string;
  label: string | null;
  business_summary: string;
  funnel_readiness_score: number;
  paid_ads_readiness_score: number;
  engine_version: string;
  created_at: string;
};

// ---- Agents (M4) ----

export type AgentRunStatus = "queued" | "running" | "succeeded" | "failed";
export type AgentTaskStatus = "queued" | "running" | "succeeded" | "failed" | "skipped";
export type RiskLevel = "low" | "medium" | "high";
export type RecommendationStatus =
  | "open"
  | "approved"
  | "rejected"
  | "executed"
  | "archived";

export type AgentRunSummary = {
  id: string;
  agent_type: string;
  status: AgentRunStatus;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
};

export type AgentCatalogEntry = {
  type: string;
  title: string;
  description: string;
  last_run: AgentRunSummary | null;
};

export type AgentTaskPublic = {
  id: string;
  task_index: number;
  skill_name: string;
  status: AgentTaskStatus;
  input_payload: Record<string, unknown> | null;
  output_payload: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
};

export type SkillOutputPublic = {
  id: string;
  skill_name: string;
  output_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type ApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "executed"
  | "canceled";

export type ApprovalSnapshot = {
  id: string;
  status: ApprovalStatus;
  approved_by: string | null;
  approved_at: string | null;
  rejected_by: string | null;
  rejected_at: string | null;
};

export type ExecutionStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "reverted";

export type ExecutionPublic = {
  id: string;
  recommendation_id: string;
  provider: string;
  action_type: string;
  status: ExecutionStatus;
  target_external_id: string | null;
  target_external_account_id: string | null;
  payload: Record<string, unknown> | null;
  prior_state: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  is_revert: boolean;
  reverts_execution_id: string | null;
  idempotency_key: string | null;
  executed_by: string | null;
  executed_at: string | null;
  created_at: string;
};

export type RecommendationPublic = {
  id: string;
  workspace_id: string;
  agent_run_id: string;
  title: string;
  summary: string;
  recommendation_type: string;
  risk_level: RiskLevel;
  expected_impact: string;
  suggested_action: string;
  status: RecommendationStatus;
  platform: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  approval: ApprovalSnapshot | null;
  executions: ExecutionPublic[];
  has_executable_action: boolean;
};

export type ApproveRecommendationResponse = {
  recommendation: RecommendationPublic;
  execution: ExecutionPublic | null;
};

export type AuditActorType = "user" | "agent" | "system";

export type AuditLogPublic = {
  id: string;
  workspace_id: string;
  actor_type: AuditActorType;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  metadata: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
};

// ---- Integrations (M6) ----

export type ConnectionStatus = "connected" | "disconnected" | "error";

export type SyncLogStatus = "running" | "succeeded" | "failed";

export type SyncLogPublic = {
  id: string;
  status: SyncLogStatus;
  started_at: string;
  completed_at: string | null;
  summary: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
};

export type IntegrationStatus = {
  provider: string;
  display_name: string;
  description: string;
  configured: boolean;
  status: ConnectionStatus;
  provider_account_id: string | null;
  display_account_name: string | null;
  scopes: string[] | null;
  write_scopes: string[];
  can_write: boolean;
  connected_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  recent_syncs: SyncLogPublic[];
};

export type ConnectUrlResponse = {
  authorization_url: string;
  state: string;
  redirect_uri: string;
};

export type AgentRunDetail = AgentRunSummary & {
  triggered_by_user_id: string | null;
  input_payload: Record<string, unknown> | null;
  output_payload: Record<string, unknown> | null;
  model_used: string | null;
  tasks: AgentTaskPublic[];
  skill_outputs: SkillOutputPublic[];
  recommendations: RecommendationPublic[];
};

// ---- Campaigns (M7) ----

export type CampaignStatus =
  | "active"
  | "paused"
  | "ended"
  | "archived"
  | "unknown";

export type CampaignPublic = {
  id: string;
  workspace_id: string;
  connected_account_id: string | null;
  provider: string;
  external_id: string;
  external_account_id: string | null;
  name: string;
  status: CampaignStatus;
  objective: string | null;
  daily_budget_cents: number | null;
  lifetime_budget_cents: number | null;
  currency: string | null;
  start_date: string | null;
  end_date: string | null;
  last_synced_at: string;
  created_at: string;
};

export type CampaignDetail = CampaignPublic & {
  raw_payload: Record<string, unknown> | null;
};

export type CampaignSummary = {
  total: number;
  active: number;
  paused: number;
  ended: number;
  archived: number;
  unknown: number;
  per_provider: Record<string, number>;
  active_without_budget: number;
  stale_active: number;
  last_synced_at: string | null;
};

export type ProviderSyncResult = {
  provider: string;
  sync_log_id: string;
  status: "running" | "succeeded" | "failed";
  fetched: number;
  upserted: number;
  error: string | null;
};

export type CampaignSyncResponse = {
  started_at: string;
  completed_at: string;
  providers: ProviderSyncResult[];
};

// ---- Analytics ----

export type Kpi = {
  impressions: number;
  clicks: number;
  spend_cents: number;
  conversions: number;
  conversion_value_cents: number;
  ctr: number;
  cpc_cents: number;
  cpm_cents: number;
  cpa_cents: number;
  roas: number;
  conversion_rate: number;
};

export type CampaignMetricsSeries = {
  campaign_id: string;
  days: number;
  points: Array<{
    date: string;
    impressions: number;
    clicks: number;
    spend_cents: number;
    conversions: number;
    conversion_value_cents: number;
  }>;
  totals: Kpi;
  currency: string;
};

export type WorkspaceAnalytics = {
  days: number;
  has_data: boolean;
  totals: Kpi;
  by_provider: Record<string, Kpi>;
  top_campaigns: Array<Kpi & { campaign_id: string; name: string }>;
  daily: Array<Kpi & { date: string }>;
  currency: string;
};

export type MetricsSyncResult = {
  upserted: number;
  providers: Array<{ provider: string; status: string; upserted?: number; error?: string | null }>;
  window: { from: string; to: string };
};

// ---- Platform fees ----

export type FeeRule = {
  id: string;
  provider: string | null;
  campaign_type: string | null;
  label: string;
  listing_fee_cents: number;
  run_flat_fee_cents: number;
  run_pct_basis_points: number;
  is_active: boolean;
  created_at: string;
};

export type FeeRuleUpsert = {
  provider?: string | null;
  campaign_type?: string | null;
  label: string;
  listing_fee_cents: number;
  run_flat_fee_cents: number;
  run_pct_basis_points: number;
};

export type FeeQuote = {
  provider: string | null;
  campaign_type: string;
  listing_fee_cents: number;
  run_flat_fee_cents: number;
  run_pct_basis_points: number;
  est_monthly_spend_cents: number;
  est_monthly_run_fee_cents: number;
  est_first_month_total_cents: number;
  source: "rule" | "default" | string;
};

export type WorkspaceFeeSummary = {
  period: string;
  total_cents: number;
  by_type: Record<string, number>;
  currency: string;
};

export type AdminRevenueSummary = {
  period: string;
  period_total_cents: number;
  all_time_total_cents: number;
  by_status_cents: Record<string, number>;
  accrual_count: number;
  currency: string;
};

export type CampaignActionResponse = {
  status: "executed" | "failed" | "queued";
  action: string;
  risk_level: "low" | "medium" | "high";
  required_role: string;
  message: string;
  recommendation_id: string;
  approval_id: string | null;
  approval_status: string | null;
  execution_id: string | null;
  execution_status: string | null;
  error_message: string | null;
  campaign: CampaignPublic;
};

export type CampaignLaunchRequest = {
  provider: string;
  name: string;
  campaign_type: string;
  daily_budget_cents: number;
  external_account_id?: string;
};

export type CampaignLaunchResponse = {
  status: "executed" | "failed" | "queued";
  risk_level: "low" | "medium" | "high";
  required_role: string;
  message: string;
  recommendation_id: string;
  approval_id: string | null;
  approval_status: string | null;
  execution_id: string | null;
  execution_status: string | null;
  error_message: string | null;
  campaign: CampaignPublic | null;
};

// ---- SEO & GEO (M8) ----

export type SeoCrawlSummary = {
  site_url?: string;
  sitemap_url_found?: string | null;
  page_url_count?: number;
  pages_crawled?: number;
  title_missing_count?: number;
  meta_missing_count?: number;
  h1_issue_count?: number;
  canonical_missing_count?: number;
  structured_data_missing_count?: number;
  open_graph_missing_count?: number;
  faq_schema_missing_count?: number;
  [key: string]: unknown;
};

export type SeoProjectPublic = {
  id: string;
  workspace_id: string;
  site_url: string | null;
  search_console_site_url: string | null;
  last_crawled_at: string | null;
  last_search_console_synced_at: string | null;
  crawl_summary: SeoCrawlSummary | null;
  created_at: string;
};

export type KeywordPublic = {
  id: string;
  query: string;
  impressions: number;
  clicks: number;
  ctr: number;
  position: number;
  opportunity_score: number;
  top_page: string | null;
  period_start: string | null;
  period_end: string | null;
  last_synced_at: string;
};

export type SearchConsoleSyncResponse = {
  site_url: string;
  period_start: string;
  period_end: string;
  keywords_upserted: number;
};

// ---- Landing pages (M9) ----

export type LandingPageSource = "manual" | "onboarding";

export type AuditScores = {
  conversion: number | null;
  mobile_ux: number | null;
  page_speed: number | null;
};

export type AuditSkillEntry = {
  score: number | null;
  severity: "ok" | "low" | "medium" | "high" | null;
};

export type LandingPageAuditSummary = {
  url: string;
  ran_at: string;
  scores: AuditScores;
  skills: Record<string, AuditSkillEntry>;
  page_speed: Record<string, unknown>;
};

export type LandingPagePublic = {
  id: string;
  workspace_id: string;
  url: string;
  label: string | null;
  source: LandingPageSource;
  is_primary: boolean;
  last_audited_at: string | null;
  last_audit_summary: LandingPageAuditSummary | null;
  created_at: string;
};

// ---- Reports (M10) ----

export type ReportPeriod = "daily" | "weekly" | "monthly";
export type ReportStatus = "generating" | "ready" | "failed";

export type ReportSummaryRow = {
  id: string;
  workspace_id: string;
  title: string;
  period: ReportPeriod;
  period_start: string;
  period_end: string;
  status: ReportStatus;
  error_message: string | null;
  email_sent_at: string | null;
  created_at: string;
};

export type ReportPayload = {
  workspace?: { id?: string; name?: string; slug?: string };
  period?: { type: ReportPeriod; label?: string; start: string; end: string };
  summary?: {
    agent_runs_total: number;
    recommendations_by_status: Record<string, number>;
    recommendations_by_risk: Record<string, number>;
    campaigns_total: number;
    campaigns_active: number;
    keywords_tracked: number;
    landing_pages_total: number;
    landing_pages_audited: number;
  };
  agent_runs?: Array<{
    id: string;
    agent_type: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
    recommendation_count: number;
  }>;
  top_recommendations?: Array<{
    id: string;
    title: string;
    summary: string;
    risk_level: "low" | "medium" | "high";
    recommendation_type: string;
    platform: string | null;
    expected_impact: string;
    suggested_action: string;
    agent_run_id: string;
    created_at: string;
  }>;
  campaigns?: {
    total: number;
    per_provider: Record<string, number>;
    active_without_budget: number;
    stale_active: number;
  };
  seo?: {
    present: boolean;
    site_url?: string | null;
    last_crawled_at?: string | null;
    last_search_console_synced_at?: string | null;
    crawl_summary?: Record<string, unknown> | null;
    top_keywords?: Array<{
      query: string;
      impressions: number;
      clicks: number;
      ctr: number;
      position: number;
      opportunity_score: number;
      top_page: string | null;
    }>;
  };
  landing_pages?: Array<{
    id: string;
    url: string;
    label: string | null;
    is_primary: boolean;
    last_audited_at: string | null;
    scores: { conversion: number | null; mobile_ux: number | null; page_speed: number | null } | null;
  }>;
  growth_dna?: {
    engine_version: string;
    funnel_readiness_score: number;
    paid_ads_readiness_score: number;
    generated_at: string;
  } | null;
  executions?: {
    total: number;
    by_status: Record<string, number>;
    by_provider: Record<string, number>;
  };
  content_drafts?: {
    total: number;
    by_status: Record<string, number>;
    by_type: Record<string, number>;
  };
  outreach?: {
    emails_total: number;
    emails_sent: number;
    emails_replied: number;
    emails_bounced: number;
    reply_rate: number;
    prospects_total: number;
    prospects_won: number;
  };
  ab_tests?: {
    total: number;
    by_status: Record<string, number>;
    completed_with_winner: number;
  };
};

export type ReportDetail = ReportSummaryRow & { payload: ReportPayload };

// ---- Billing (M11) ----

export type SubscriptionStatusValue =
  | "none"
  | "trialing"
  | "active"
  | "past_due"
  | "unpaid"
  | "canceled"
  | "incomplete"
  | "incomplete_expired"
  | "paused";

export type PlanLimits = {
  landing_pages: number | null;
  members: number | null;
  outbound_writes_per_month?: number | null;
  // AI work is metered as a single monthly credit pool.
  monthly_credits?: number | null;
};

export type Plan = {
  code: string;
  display_name: string;
  description: string;
  monthly_price_usd: number | null;
  annual_price_usd?: number | null;
  is_paid: boolean;
  limits: PlanLimits;
};

export type Usage = {
  credits_used_last_30d?: number;
  agent_runs_last_30d?: number;
  content_drafts_last_30d?: number;
  outreach_emails_last_30d?: number;
  ab_tests_last_30d?: number;
  outbound_writes_last_30d?: number;
  llm_tokens_last_30d?: number;
  llm_cost_cents_last_30d?: number;
};

export type BillingStatus = {
  plan: Plan;
  available_plans: Plan[];
  subscription_status: SubscriptionStatusValue;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  trial_end: string | null;
  usage: Usage;
  has_billing_customer: boolean;
  paddle_configured: boolean;
  subscription_provider: "paddle" | "none";
  subscription_source: "paddle" | "appsumo";
};

export type PaddleCheckout = {
  client_token: string;
  environment: string;
  price_id: string;
  customer_email: string;
  custom_data: Record<string, string>;
};

export type CheckoutSessionResponse = {
  provider: "paddle";
  paddle?: PaddleCheckout | null;
};
export type PortalSessionResponse = { url: string };

// ---- Content drafts (Phase B) ----

export type ContentDraftType =
  | "blog_post"
  | "landing_page"
  | "ad_copy"
  | "meta_description"
  | "email"
  | "social_post"
  | "short_video_script";

export type ContentDraftStatus =
  | "draft"
  | "approved"
  | "rejected"
  | "published"
  | "archived";

export type ContentDraftPublic = {
  id: string;
  workspace_id: string;
  agent_run_id: string | null;
  type: ContentDraftType;
  status: ContentDraftStatus;
  title: string;
  body: string;
  target_url: string | null;
  slug: string | null;
  excerpt: string | null;
  image_url: string | null;
  /** Social platform slug (see /social/platforms); null for non-social drafts. */
  platform: string | null;
  keywords: string[] | null;
  hashtags: string[] | null;
  seo_metadata: Record<string, unknown> | null;
  notes: string | null;
  source: string;
  model_used: string | null;
  created_by: string | null;
  approved_by: string | null;
  approved_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
};

export type GenerateContentDraftRequest = {
  type: ContentDraftType;
  topic: string;
  keywords?: string[];
  target_url?: string | null;
  audience?: string | null;
  notes?: string | null;
};

// ---- Social content ----

export type SocialFormat = "post" | "video_script";

export type SocialPlatformPublic = {
  slug: string;
  label: string;
  format: SocialFormat;
  draft_type: ContentDraftType;
  body_length_min: number;
  body_length_max: number;
  hard_char_limit: number | null;
  hashtag_min: number;
  hashtag_max: number;
  aspect_ratio: string | null;
  duration_min_seconds: number | null;
  duration_max_seconds: number | null;
  guidance: string;
};

export type GenerateSocialPackRequest = {
  /** Optional when source_url is provided (page title becomes the topic). */
  topic?: string | null;
  platforms: string[];
  keywords?: string[];
  audience?: string | null;
  target_url?: string | null;
  notes?: string | null;
  call_to_action?: string | null;
  /** A page to repurpose into social content; fetched server-side. */
  source_url?: string | null;
};

export type SocialPackResponse = {
  topic: string;
  drafts: ContentDraftPublic[];
};

/** Shape of `seo_metadata.script` on a `short_video_script` draft. */
export type VideoScriptBeat = {
  narration: string;
  on_screen_text?: string;
  visual?: string;
};

export type VideoScript = {
  hook: string;
  beats: VideoScriptBeat[];
  cta: string;
  aspect_ratio: string | null;
  target_duration_seconds: [number, number];
};

// ---- Public blog ----

export type PublicBlogPostSummary = {
  id: string;
  slug: string;
  title: string;
  excerpt: string | null;
  image_url: string | null;
  keywords: string[] | null;
  published_at: string | null;
};

export type PublicBlogPost = PublicBlogPostSummary & {
  body: string;
  seo_metadata: Record<string, unknown> | null;
};

// ---- Blog editor (AI Assistant + image upload) ----

export type AiAssistAction =
  | "outline"
  | "expand"
  | "refine"
  | "suggest_title"
  | "suggest_meta";

export type AiAssistResponse = {
  action: AiAssistAction;
  source: "llm" | "deterministic";
  result: Record<string, unknown>;
};

export type ImageUploadResponse = {
  url: string;
  bytes: number;
  content_type: string;
  filename: string;
};

// ---- Backlink outreach (Phase C) ----

export type ProspectStatus =
  | "new"
  | "queued"
  | "contacted"
  | "replied"
  | "won"
  | "declined"
  | "bounced"
  | "archived";

export type OutreachEmailStatus =
  | "draft"
  | "approved"
  | "scheduled"
  | "sent"
  | "failed"
  | "replied"
  | "bounced";

export type BacklinkProspectPublic = {
  id: string;
  workspace_id: string;
  domain: string;
  page_url: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_role: string | null;
  relevance_score: number | null;
  domain_authority: number | null;
  status: ProspectStatus;
  notes: string | null;
  source: string;
  last_contacted_at: string | null;
  won_at: string | null;
  backlink_url: string | null;
  created_at: string;
  updated_at: string;
};

export type OutreachEmailPublic = {
  id: string;
  workspace_id: string;
  prospect_id: string;
  subject: string;
  body: string;
  to_email: string;
  status: OutreachEmailStatus;
  source: string;
  model_used: string | null;
  scheduled_for: string | null;
  sent_at: string | null;
  replied_at: string | null;
  error_message: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
};

// ---- A/B tests (Phase D) ----

export type AbTestTarget = "ad" | "landing_page";
export type AbTestStatus =
  | "draft"
  | "ready"
  | "launched"
  | "paused"
  | "completed"
  | "archived";

export type AbTestVariantPublic = {
  id: string;
  ab_test_id: string;
  name: string;
  position: number;
  is_control: boolean;
  traffic_share: number;
  payload: Record<string, unknown>;
  external_id: string | null;
  launched_at: string | null;
  metrics: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AbTestPublic = {
  id: string;
  workspace_id: string;
  name: string;
  hypothesis: string | null;
  target: AbTestTarget;
  objective: string;
  status: AbTestStatus;
  provider: string | null;
  external_account_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  winner_variant_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  variants: AbTestVariantPublic[];
};

export type CreateAbTestRequest = {
  name: string;
  hypothesis?: string | null;
  target: AbTestTarget;
  objective: string;
  provider?: string | null;
  external_account_id?: string | null;
  metadata?: Record<string, unknown> | null;
  variants: Array<{
    name: string;
    is_control?: boolean;
    traffic_share?: number;
    payload?: Record<string, unknown>;
  }>;
};

// ---------------------------------------------------------------------------
// Autoresponders
// ---------------------------------------------------------------------------

export type AutoresponderConfigField = {
  key: string;
  label: string;
  type: string;
  required: boolean;
  placeholder: string | null;
  help_text: string | null;
};

export type AutoresponderProviderInfo = {
  provider: string;
  display_name: string;
  description: string;
  requires_api_key: boolean;
  api_key_label: string;
  api_key_help: string | null;
  config_fields: AutoresponderConfigField[];
  supports_audience_listing: boolean;
  supports_contact_pull: boolean;
  freeform_audience: boolean;
  docs_url: string | null;
};

export type AutoresponderConnection = {
  id: string;
  provider: string;
  display_name: string | null;
  provider_account_id: string | null;
  status: ConnectionStatus;
  config: Record<string, unknown> | null;
  connected_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
};

export type AutoresponderAudience = {
  external_id: string;
  name: string;
  member_count: number | null;
};

export type AudienceListResponse = {
  provider: string;
  supports_audience_listing: boolean;
  freeform_audience: boolean;
  audiences: AutoresponderAudience[];
};

export type ContactInput = {
  email?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  tags?: string[];
  custom_fields?: Record<string, unknown>;
};

export type ContactSyncDirection = "push" | "pull";
export type ContactSyncStatus = "running" | "succeeded" | "partial" | "failed";

export type ContactSync = {
  id: string;
  direction: ContactSyncDirection;
  status: ContactSyncStatus;
  audience_external_id: string | null;
  audience_name: string | null;
  source: string | null;
  requested_count: number;
  succeeded_count: number;
  failed_count: number;
  summary: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type ContactPublic = {
  email: string | null;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  tags: string[];
};

export type PullContactsResponse = {
  sync: ContactSync;
  contacts: ContactPublic[];
};

export type AdPublishResponse = {
  status: "executed" | "failed" | "queued";
  object_type: "ad_group" | "ad";
  risk_level: string;
  required_role: string;
  message: string;
  recommendation_id: string;
  approval_id: string | null;
  approval_status: string | null;
  execution_id: string | null;
  execution_status: string | null;
  external_id: string | null;
  error_message: string | null;
};

export type PaymentProviderInfo = {
  provider: string;
  display_name: string;
  description: string;
  configured: boolean;
};

export type FeeInvoiceStatus = "draft" | "open" | "paid" | "void" | "failed";

export type FeeInvoiceLineItem = {
  accrual_id: string;
  description: string;
  amount_cents: number;
  fee_type: string;
};

export type FeeInvoice = {
  id: string;
  workspace_id: string;
  provider: string;
  status: FeeInvoiceStatus;
  amount_cents: number;
  currency: string;
  period: string | null;
  accrual_count: number;
  external_id: string | null;
  hosted_url: string | null;
  line_items: FeeInvoiceLineItem[] | null;
  error_message: string | null;
  issued_at: string | null;
  paid_at: string | null;
  created_at: string;
};

// ---- Email campaigns (Omnisend) ----

export type EmailCampaignPublic = {
  id: string;
  provider: string;
  external_id: string;
  name: string | null;
  subject: string | null;
  from_name: string | null;
  campaign_type: string | null;
  status: string | null;
  sent_at: string | null;
  sent_count: number;
  opened_count: number;
  clicked_count: number;
  bounced_count: number;
  complained_count: number;
  unsubscribed_count: number;
  open_rate: number | null;
  click_rate: number | null;
  bounce_rate: number | null;
  complaint_rate: number | null;
  unsubscribe_rate: number | null;
  revenue_cents: number | null;
  currency: string | null;
  ad_campaign_id: string | null;
  synced_at: string;
};

// Shape of the `email_marketing` agent's output_payload. Every section is
// optional/loose because the agent degrades gracefully (no-LLM fallback, missing
// months, no subjects, etc.). The `skipped` branch is the empty-data state.
export type EmailSegment = { segment: string; why: string };

export type EmailMarketingReport = {
  skipped?: boolean;
  reason?: string;
  generated_at?: string;
  scope?: {
    provider?: string;
    campaigns_analyzed?: number;
    total_sent?: number;
  };
  data_caveats?: string[];
  executive_summary?: string;
  section_1_audit?: {
    score: number;
    grade: string;
    subscores?: Record<string, number>;
    weighted_rates?: Record<string, number>;
    benchmarks?: Record<string, number>;
  };
  section_2_segments?: {
    note?: string;
    recommended_segments?: EmailSegment[];
    ai_suggestions?: EmailSegment[];
  };
  section_3_black_friday?: {
    segment?: string;
    angle?: string;
    subject_lines?: string[];
    template_draft?: string;
    note?: string;
  };
  section_4_open_rate_trend?: {
    monthly?: { month: string; open_rate: number | null; sent: number }[];
    latest_month?: string;
    delta_vs_prev?: number;
    relative_change?: number;
    direction?: "up" | "down" | "flat";
    note?: string;
  };
  section_5_best_send_day?: {
    caveat?: string;
    by_day_of_week?: { day: string; open_rate: number | null; sent: number }[];
    best_day?: string | null;
  };
  section_6_subject_patterns?: {
    window_days?: number;
    patterns?: {
      pattern: string;
      campaigns_with: number;
      open_rate_with: number;
      open_rate_without: number;
      lift: number;
    }[];
    top_subjects?: { subject: string; open_rate: number; sent: number }[];
    note?: string;
  };
  section_7_deliverability?: {
    verdict?: "healthy" | "at_risk";
    flags?: string[];
    complaint_rate?: number;
    bounce_rate?: number;
    unsubscribe_rate?: number;
    limits?: Record<string, number>;
    not_covered?: string;
  };
};

// ---- Traffic Genie ----

export type TrafficCategory = {
  slug: string;
  name: string;
  description: string;
};

export type TrafficSource = {
  slug: string;
  name: string;
  category: string;
  source_type: "paid" | "paid_email" | "organic";
  best_for: string[];
  speed: "Fast" | "Medium" | "Slow";
  cost: "Free" | "Low" | "Medium" | "High";
  difficulty: "Easy" | "Medium" | "Hard";
  content_required: string;
  recommended_goal: string;
  tracking: string;
  recommended_followup: string;
  agents: string[];
  status: "active" | "manual" | "coming_soon";
  asset_types: string[];
};

export type TrafficRecipe = {
  slug: string;
  name: string;
  goal: string;
  sources: string[];
  assets: string[];
};

export type TrafficCatalog = {
  categories: TrafficCategory[];
  sources: TrafficSource[];
  recipes: TrafficRecipe[];
};

export type TrafficCampaign = {
  id: string;
  source_slug: string;
  name: string;
  goal: string | null;
  offer_name: string | null;
  offer_url: string | null;
  audience: string | null;
  budget_cents: number | null;
  currency: string | null;
  status: string;
  start_date: string | null;
  end_date: string | null;
  omnisend_segment: string | null;
  omnisend_flow: string | null;
  ai_summary: string | null;
  created_at: string;
  updated_at: string;
};

export type TrafficCampaignAsset = {
  id: string;
  campaign_id: string;
  agent_run_id: string | null;
  asset_type: string;
  title: string | null;
  content: string;
  platform: string | null;
  variation_label: string | null;
  agent_name: string | null;
  created_at: string;
};

export type TrafficCampaignDetail = TrafficCampaign & {
  assets: TrafficCampaignAsset[];
};

export type CreateTrafficCampaignRequest = {
  source_slug: string;
  name: string;
  goal?: string | null;
  offer_name?: string | null;
  offer_url?: string | null;
  audience?: string | null;
  budget_cents?: number | null;
  currency?: string | null;
  omnisend_segment?: string | null;
  omnisend_flow?: string | null;
};

export type UtmLink = {
  id: string;
  campaign_id: string | null;
  destination_url: string;
  source: string;
  medium: string;
  campaign: string;
  content: string | null;
  term: string | null;
  vendor_name: string | null;
  generated_url: string;
  short_url: string | null;
  created_at: string;
};

export type CreateUtmLinkRequest = {
  destination_url: string;
  source: string;
  medium: string;
  campaign: string;
  content?: string | null;
  term?: string | null;
  vendor_name?: string | null;
  campaign_id?: string | null;
};

export type TrafficRecommendationRequest = {
  business_type?: string;
  product?: string;
  audience?: string;
  goal?: string;
  monthly_budget?: number;
  speed?: string;
  business_model?: string;
  industry?: string;
  preference?: string;
};

// Shape of the traffic_recommendation agent's output_payload (plan).
export type TrafficRecommendation = {
  generated_at?: string;
  inputs_echo?: Record<string, unknown>;
  primary_source?: TrafficSource | null;
  secondary_source?: TrafficSource | null;
  organic_support?: TrafficSource | null;
  retargeting_channel?: TrafficSource | null;
  follow_up_journey?: string;
  tracking_setup?: string;
  estimated_difficulty?: string;
  estimated_speed?: string;
  assets_needed?: string[];
  launch_plan_7_day?: string[];
  optimization_plan_30_day?: string[];
  why?: string;
};

// ---- Solo Ads (Paid Email Traffic) ----

export type SoloAdVendor = {
  id: string;
  name: string;
  website: string | null;
  contact_email: string | null;
  niche: string | null;
  countries: string | null;
  average_cpc_cents: number | null;
  notes: string | null;
  quality_score: number | null;
  status: string;
  created_at: string;
};

export type CreateVendorRequest = {
  name: string;
  website?: string | null;
  contact_email?: string | null;
  niche?: string | null;
  countries?: string | null;
  average_cpc_cents?: number | null;
  notes?: string | null;
  status?: string | null;
};

export type SoloAdOrder = {
  id: string;
  vendor_id: string | null;
  traffic_campaign_id: string | null;
  name: string | null;
  status: string;
  currency: string | null;
  clicks_purchased: number;
  clicks_delivered: number;
  unique_clicks: number;
  cost_cents: number;
  optins: number;
  sales: number;
  revenue_cents: number;
  refunds: number;
  cpc_cents: number | null;
  cpl_cents: number | null;
  epc_cents: number | null;
  roi: number | null;
  optin_rate: number | null;
  quality_score: number | null;
  quality_verdict: string | null;
  quality_flags: string[] | null;
  quality_note: string | null;
  created_at: string;
};

export type CreateOrderRequest = {
  vendor_id?: string | null;
  traffic_campaign_id?: string | null;
  name?: string | null;
  status?: string | null;
  currency?: string | null;
  clicks_purchased?: number | null;
  clicks_delivered?: number | null;
  unique_clicks?: number | null;
  cost_cents?: number | null;
  optins?: number | null;
  sales?: number | null;
  revenue_cents?: number | null;
  refunds?: number | null;
};

export type SoloAdsPlaybookRequest = {
  offer_name?: string;
  offer_url?: string;
  audience?: string;
  goal?: string;
  niche?: string;
  lead_magnet?: string;
  vendor_name?: string;
  campaign_name?: string;
};

export type SoloAdsPlaybook = {
  offer_name?: string | null;
  goal?: string | null;
  generation?: string;
  offer_suitability?: string;
  subject_lines?: string[];
  email_swipes?: string[];
  preheader?: string;
  cta_options?: string[];
  landing_headline?: string;
  thank_you_cta?: string;
  vendor_screening_checklist?: string[];
  followup_sequence?: string[];
  tracking_plan?: string[];
  compliance_notes?: string[];
};

// ---- Omnisend journeys (Phase 5) ----

export type JourneyStep = { label: string; delay: string };

export type JourneyType = {
  slug: string;
  name: string;
  description: string;
  default_channel: string;
  trigger: string;
  recommended_for: string[];
  default_steps: JourneyStep[];
};

export type GenerateJourneyRequest = {
  journey_type: string;
  channel?: string;
  offer_name?: string;
  offer_url?: string;
  audience?: string;
  flow_name?: string;
  tag?: string;
  segment_name?: string;
  campaign_name?: string;
};

export type JourneyEmail = {
  step: number;
  delay: string;
  subject: string;
  preheader?: string;
  body: string;
  cta?: string;
  personalization_tokens?: string[];
};

export type JourneySms = { delay: string; message: string };

export type OmnisendJourney = {
  journey_type?: string;
  journey_name?: string;
  flow_name?: string;
  channel?: string;
  trigger?: string;
  segmentation_rules?: string;
  generation?: string;
  email_sequence?: JourneyEmail[];
  sms_sequence?: JourneySms[];
  exit_conditions?: string[];
  conversion_goal?: string;
  implementation_notes?: string[];
};

export type CampaignMapping = {
  traffic_campaign_id: string;
  source: string;
  segment_name: string;
  tag: string;
  flow_name: string;
  lead_source_field: string;
  recommended_journey_type: string;
  how_to: string;
};

export type SyncLeadSourceResult = {
  tag: string;
  requested: number;
  succeeded: number;
  failed: number;
  status: string;
};

// ---- Traffic analytics (Phase 6) ----

export type TrafficRollup = {
  clicks: number;
  leads: number;
  sales: number;
  cost_cents: number;
  revenue_cents: number;
  refunds: number;
  visitors: number;
  sessions: number;
  profit_cents: number;
  cpc_cents: number | null;
  cpl_cents: number | null;
  cps_cents: number | null;
  epc_cents: number | null;
  roas: number | null;
  lead_rate: number | null;
  conversion_rate: number | null;
  refund_rate: number | null;
  bounce_rate: number | null;
  quality_score?: number | null;
  quality_verdict?: string | null;
};

export type SourceRollup = TrafficRollup & {
  source_slug: string;
  source_name: string;
  source_type: string;
};

export type CampaignRollup = TrafficRollup & {
  campaign_id: string;
  name: string;
  source_slug: string | null;
};

export type TrafficAnalyticsOverview = {
  has_data: boolean;
  currency: string;
  totals: TrafficRollup;
  sources: SourceRollup[];
  campaigns: CampaignRollup[];
  by_type: Record<string, TrafficRollup>;
};

export type TrafficAction = {
  type: string;
  priority: "high" | "medium" | "low";
  source: string;
  title: string;
  detail: string;
};

export type TrafficOptimization = {
  has_data?: boolean;
  reason?: string;
  generated_at?: string;
  totals?: TrafficRollup;
  by_type?: Record<string, TrafficRollup>;
  top_sources?: SourceRollup[];
  top_campaigns?: CampaignRollup[];
  next_best_actions?: TrafficAction[];
  executive_summary?: string;
};

export type LogMetricRequest = {
  source_slug: string;
  traffic_campaign_id?: string | null;
  medium?: string | null;
  date?: string | null;
  currency?: string | null;
  clicks?: number | null;
  leads?: number | null;
  sales?: number | null;
  revenue_cents?: number | null;
  cost_cents?: number | null;
  visitors?: number | null;
  sessions?: number | null;
  refunds?: number | null;
};
