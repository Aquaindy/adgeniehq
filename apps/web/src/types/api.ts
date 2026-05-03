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

export type AdGroup = {
  id: string;
  workspace_id: string;
  campaign_id: string;
  external_id: string;
  name: string;
  status: AdGroupStatus;
  daily_budget_cents: number | null;
  targeting: Record<string, unknown> | null;
  last_synced_at: string;
  created_at: string;
};

export type Ad = {
  id: string;
  workspace_id: string;
  campaign_id: string;
  ad_group_id: string;
  creative_id: string | null;
  external_id: string;
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

export type GrowthDna = {
  id: string;
  workspace_id: string;
  onboarding_profile_id: string;
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
  agent_runs_per_month: number | null;
  landing_pages: number | null;
  members: number | null;
  content_drafts_per_month?: number | null;
  outreach_emails_per_month?: number | null;
  ab_tests_per_month?: number | null;
  outbound_writes_per_month?: number | null;
  llm_tokens_per_month?: number | null;
};

export type Plan = {
  code: string;
  display_name: string;
  description: string;
  monthly_price_usd: number | null;
  is_paid: boolean;
  limits: PlanLimits;
};

export type Usage = {
  agent_runs_last_30d: number;
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
  stripe_configured: boolean;
};

export type CheckoutSessionResponse = { url: string };
export type PortalSessionResponse = { url: string };

// ---- Content drafts (Phase B) ----

export type ContentDraftType =
  | "blog_post"
  | "landing_page"
  | "ad_copy"
  | "meta_description"
  | "email"
  | "social_post";

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
  keywords: string[] | null;
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
