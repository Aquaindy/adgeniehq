import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense, lazy, useEffect, type ComponentType } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

// Eager: layout, route guards, auth pages, public marketing, and the first
// authenticated view (Dashboard). These are on the critical path so we don't
// want a chunk round-trip for them.
import { AppShell } from "@/components/layout/AppShell";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { GoogleFinishPage } from "@/features/auth/GoogleFinishPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { VerifyEmailPage } from "@/features/auth/VerifyEmailPage";
import { AppSumoRedeemPage } from "@/features/appsumo/AppSumoRedeemPage";
import { BlogPage } from "@/features/marketing/BlogPage";
import { BlogPostPage } from "@/features/marketing/BlogPostPage";
import { LandingPage } from "@/features/marketing/LandingPage";
import { PricingPage } from "@/features/marketing/PricingPage";
import { PrivacyPage } from "@/features/marketing/PrivacyPage";
import { RefundPolicyPage } from "@/features/marketing/RefundPolicyPage";
import { TermsPage } from "@/features/marketing/TermsPage";
import {
  bootstrapAuth,
  ensureApiClientConfigured,
} from "@/features/auth/auth-runtime";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { RequireWorkspace } from "@/features/workspaces/RequireWorkspace";
import { WorkspaceSelectorPage } from "@/features/workspaces/WorkspaceSelectorPage";

// Lazy: the bulk of the authenticated app. Each becomes its own chunk loaded on
// first navigation, shrinking the initial bundle. `lazyPage` adapts our named
// exports to React.lazy's default-export contract.
function lazyPage(loader: () => Promise<Record<string, unknown>>, name: string) {
  return lazy(async () => ({ default: (await loader())[name] as ComponentType }));
}

const AdminPage = lazyPage(() => import("@/features/admin/AdminPage"), "AdminPage");
const AgentRunDetailPage = lazyPage(() => import("@/features/agents/AgentRunDetailPage"), "AgentRunDetailPage");
const AgentsDashboardPage = lazyPage(() => import("@/features/agents/AgentsDashboardPage"), "AgentsDashboardPage");
const BillingPage = lazyPage(() => import("@/features/billing/BillingPage"), "BillingPage");
const CampaignDetailPage = lazyPage(() => import("@/features/campaigns/CampaignDetailPage"), "CampaignDetailPage");
const CampaignsPage = lazyPage(() => import("@/features/campaigns/CampaignsPage"), "CampaignsPage");
const CreativesPage = lazyPage(() => import("@/features/creatives/CreativesPage"), "CreativesPage");
const ContentDraftDetailPage = lazyPage(() => import("@/features/content/ContentDraftDetailPage"), "ContentDraftDetailPage");
const ContentDraftsPage = lazyPage(() => import("@/features/content/ContentDraftsPage"), "ContentDraftsPage");
const BlogEditorPage = lazyPage(() => import("@/features/blog/BlogEditorPage"), "BlogEditorPage");
const BlogPostsPage = lazyPage(() => import("@/features/blog/BlogPostsPage"), "BlogPostsPage");
const AbTestDetailPage = lazyPage(() => import("@/features/ab-tests/AbTestDetailPage"), "AbTestDetailPage");
const AbTestsPage = lazyPage(() => import("@/features/ab-tests/AbTestsPage"), "AbTestsPage");
const OutreachPage = lazyPage(() => import("@/features/outreach/OutreachPage"), "OutreachPage");
const ProspectDetailPage = lazyPage(() => import("@/features/outreach/ProspectDetailPage"), "ProspectDetailPage");
const GrowthDnaPage = lazyPage(() => import("@/features/growth-dna/GrowthDnaPage"), "GrowthDnaPage");
const IntegrationsPage = lazyPage(() => import("@/features/integrations/IntegrationsPage"), "IntegrationsPage");
const OnboardingWizardPage = lazyPage(() => import("@/features/onboarding/OnboardingWizardPage"), "OnboardingWizardPage");
const RecommendationDetailPage = lazyPage(() => import("@/features/recommendations/RecommendationDetailPage"), "RecommendationDetailPage");
const RecommendationsPage = lazyPage(() => import("@/features/recommendations/RecommendationsPage"), "RecommendationsPage");
const ReportDetailPage = lazyPage(() => import("@/features/reports/ReportDetailPage"), "ReportDetailPage");
const ReportsPage = lazyPage(() => import("@/features/reports/ReportsPage"), "ReportsPage");
const SeoPage = lazyPage(() => import("@/features/seo/SeoPage"), "SeoPage");
const WebsitePage = lazyPage(() => import("@/features/website/WebsitePage"), "WebsitePage");
const AutopilotPage = lazyPage(() => import("@/features/autopilot/AutopilotPage"), "AutopilotPage");
const AutorespondersPage = lazyPage(() => import("@/features/autoresponders/AutorespondersPage"), "AutorespondersPage");
const ApiKeysPage = lazyPage(() => import("@/features/settings/ApiKeysPage"), "ApiKeysPage");
const ProfilePage = lazyPage(() => import("@/features/settings/ProfilePage"), "ProfilePage");
const ProviderCredentialsPage = lazyPage(() => import("@/features/settings/ProviderCredentialsPage"), "ProviderCredentialsPage");
const WorkspaceApiKeysPage = lazyPage(() => import("@/features/settings/WorkspaceApiKeysPage"), "WorkspaceApiKeysPage");

ensureApiClientConfigured();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 10_000,
      retry: (failureCount, error) => {
        if (error && (error as { status?: number }).status === 401) return false;
        return failureCount < 2;
      },
    },
  },
});

export function App() {
  useEffect(() => {
    void bootstrapAuth();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense
          fallback={
            <div className="flex min-h-screen items-center justify-center text-sm text-slate-400">
              Loading…
            </div>
          }
        >
        <Routes>
          {/* Public */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/welcome" element={<Navigate to="/" replace />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/blog" element={<BlogPage />} />
          <Route path="/blog/:slug" element={<BlogPostPage />} />
          <Route path="/terms" element={<TermsPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/refund" element={<RefundPolicyPage />} />
          <Route path="/appsumo/redeem" element={<AppSumoRedeemPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/auth/google/finish" element={<GoogleFinishPage />} />

          {/* Authenticated, but pre-workspace */}
          <Route element={<RequireAuth />}>
            <Route path="/workspaces" element={<WorkspaceSelectorPage />} />

            {/* Authenticated + workspace selected */}
            <Route element={<RequireWorkspace />}>
              <Route element={<AppShell />}>
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="onboarding" element={<OnboardingWizardPage />} />
                <Route path="growth-dna" element={<GrowthDnaPage />} />
                <Route path="settings" element={<SettingsLayout />}>
                  <Route index element={<Navigate to="/settings/profile" replace />} />
                  <Route path="profile" element={<ProfilePage />} />
                  <Route path="billing" element={<BillingPage />} />
                  <Route path="integrations" element={<IntegrationsPage />} />
                  <Route path="api-keys" element={<ApiKeysPage />}>
                    <Route
                      index
                      element={<Navigate to="/settings/api-keys/your-keys" replace />}
                    />
                    <Route path="your-keys" element={<WorkspaceApiKeysPage />} />
                    <Route path="providers" element={<ProviderCredentialsPage />} />
                  </Route>
                </Route>
                <Route path="autopilot" element={<AutopilotPage />} />
                <Route path="billing" element={<Navigate to="/settings/billing" replace />} />
                <Route path="integrations" element={<Navigate to="/settings/integrations" replace />} />
                <Route path="admin" element={<AdminPage />} />
                <Route path="agents" element={<AgentsDashboardPage />} />
                <Route path="agents/runs/:runId" element={<AgentRunDetailPage />} />
                <Route path="recommendations" element={<RecommendationsPage />} />
                <Route
                  path="recommendations/:recommendationId"
                  element={<RecommendationDetailPage />}
                />
                <Route path="campaigns" element={<CampaignsPage />} />
                <Route path="campaigns/:campaignId" element={<CampaignDetailPage />} />
                <Route path="creatives" element={<CreativesPage />} />
                <Route path="autoresponders" element={<AutorespondersPage />} />
                <Route path="content" element={<ContentDraftsPage />} />
                <Route path="content/:draftId" element={<ContentDraftDetailPage />} />
                <Route path="blog/posts" element={<BlogPostsPage />} />
                <Route path="blog/posts/:draftId" element={<BlogEditorPage />} />
                <Route path="outreach" element={<OutreachPage />} />
                <Route path="outreach/:prospectId" element={<ProspectDetailPage />} />
                <Route path="ab-tests" element={<AbTestsPage />} />
                <Route path="ab-tests/:testId" element={<AbTestDetailPage />} />
                <Route path="seo" element={<SeoPage />} />
                <Route path="website" element={<WebsitePage />} />
                <Route path="reports" element={<ReportsPage />} />
                <Route path="reports/:reportId" element={<ReportDetailPage />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Route>
            </Route>
          </Route>
        </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
