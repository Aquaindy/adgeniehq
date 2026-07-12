import { apiFetch } from "@/lib/api-client";
import type {
  GrowthDna,
  GrowthDnaSummary,
  OnboardingProfile,
  OnboardingUpdate,
} from "@/types/api";

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

export function listGrowthDnaHistory(workspaceId: string) {
  return apiFetch<GrowthDnaSummary[]>(`/workspaces/${workspaceId}/growth-dna/history`);
}

export function getGrowthDnaById(workspaceId: string, dnaId: string) {
  return apiFetch<GrowthDna>(`/workspaces/${workspaceId}/growth-dna/${dnaId}`);
}

export function renameGrowthDna(
  workspaceId: string,
  dnaId: string,
  label: string | null,
) {
  return apiFetch<GrowthDna>(`/workspaces/${workspaceId}/growth-dna/${dnaId}`, {
    method: "PATCH",
    body: { label },
  });
}

export function deleteGrowthDna(workspaceId: string, dnaId: string) {
  return apiFetch<void>(`/workspaces/${workspaceId}/growth-dna/${dnaId}`, {
    method: "DELETE",
  });
}
