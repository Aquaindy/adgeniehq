import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { AdminPage } from "@/features/admin/AdminPage";
import { AgentRunDetailPage } from "@/features/agents/AgentRunDetailPage";
import { AgentsDashboardPage } from "@/features/agents/AgentsDashboardPage";
import { BillingPage } from "@/features/billing/BillingPage";
import { CampaignDetailPage } from "@/features/campaigns/CampaignDetailPage";
import { CampaignsPage } from "@/features/campaigns/CampaignsPage";
import { CreativesPage } from "@/features/creatives/CreativesPage";
import { ContentDraftDetailPage } from "@/features/content/ContentDraftDetailPage";
import { ContentDraftsPage } from "@/features/content/ContentDraftsPage";
import { BlogEditorPage } from "@/features/blog/BlogEditorPage";
import { BlogPostsPage } from "@/features/blog/BlogPostsPage";
import { AbTestDetailPage } from "@/features/ab-tests/AbTestDetailPage";
import { AbTestsPage } from "@/features/ab-tests/AbTestsPage";
import { OutreachPage } from "@/features/outreach/OutreachPage";
import { ProspectDetailPage } from "@/features/outreach/ProspectDetailPage";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { GoogleFinishPage } from "@/features/auth/GoogleFinishPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { AppSumoRedeemPage } from "@/features/appsumo/AppSumoRedeemPage";
import { BlogPage } from "@/features/marketing/BlogPage";
import { BlogPostPage } from "@/features/marketing/BlogPostPage";
import { LandingPage } from "@/features/marketing/LandingPage";
import { PricingPage } from "@/features/marketing/PricingPage";
import { PrivacyPage } from "@/features/marketing/PrivacyPage";
import { TermsPage } from "@/features/marketing/TermsPage";
import {
  bootstrapAuth,
  ensureApiClientConfigured,
} from "@/features/auth/auth-runtime";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { GrowthDnaPage } from "@/features/growth-dna/GrowthDnaPage";
import { IntegrationsPage } from "@/features/integrations/IntegrationsPage";
import { OnboardingWizardPage } from "@/features/onboarding/OnboardingWizardPage";
import { RecommendationDetailPage } from "@/features/recommendations/RecommendationDetailPage";
import { RecommendationsPage } from "@/features/recommendations/RecommendationsPage";
import { ReportDetailPage } from "@/features/reports/ReportDetailPage";
import { ReportsPage } from "@/features/reports/ReportsPage";
import { SeoPage } from "@/features/seo/SeoPage";
import { WebsitePage } from "@/features/website/WebsitePage";
import { AutopilotPage } from "@/features/autopilot/AutopilotPage";
import { ApiKeysPage } from "@/features/settings/ApiKeysPage";
import { ProfilePage } from "@/features/settings/ProfilePage";
import { ProviderCredentialsPage } from "@/features/settings/ProviderCredentialsPage";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { WorkspaceApiKeysPage } from "@/features/settings/WorkspaceApiKeysPage";
import { RequireWorkspace } from "@/features/workspaces/RequireWorkspace";
import { WorkspaceSelectorPage } from "@/features/workspaces/WorkspaceSelectorPage";

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
        <Routes>
          {/* Public */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/welcome" element={<Navigate to="/" replace />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/blog" element={<BlogPage />} />
          <Route path="/blog/:slug" element={<BlogPostPage />} />
          <Route path="/terms" element={<TermsPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/appsumo/redeem" element={<AppSumoRedeemPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
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
      </BrowserRouter>
    </QueryClientProvider>
  );
}
