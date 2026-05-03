import { apiFetch } from "@/lib/api-client";
import type { GrowthDna, OnboardingProfile, OnboardingUpdate } from "@/types/api";

export function getOnboarding(workspaceId: string) {
  return apiFetch<OnboardingProfile>(`/workspaces/${workspaceId}/onboarding`);
}

export function updateOnboarding(workspaceId: string, payload: OnboardingUpdate) {
  return apiFetch<OnboardingProfile>(`/workspaces/${workspaceId}/onboarding`, {
    method: "POST",
    body: payload,
  });
}

export function generateGrowthDna(workspaceId: string) {
  return apiFetch<GrowthDna>(`/workspaces/${workspaceId}/growth-dna/generate`, {
    method: "POST",
  });
}

export function getGrowthDna(workspaceId: string) {
  return apiFetch<GrowthDna>(`/workspaces/${workspaceId}/growth-dna`);
}
