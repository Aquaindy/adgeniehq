import { apiFetch } from "@/lib/api-client";
import type {
  AgentCatalogEntry,
  AgentRunDetail,
  AgentRunSummary,
  ApproveRecommendationResponse,
  AuditLogPublic,
  ExecutionPublic,
  RecommendationPublic,
} from "@/types/api";

export function listAgents(workspaceId: string) {
  return apiFetch<AgentCatalogEntry[]>(`/workspaces/${workspaceId}/agents`);
}

export function listAgentRuns(workspaceId: string) {
  return apiFetch<AgentRunSummary[]>(`/workspaces/${workspaceId}/agents/runs`);
}

export function getAgentRun(workspaceId: string, runId: string) {
  return apiFetch<AgentRunDetail>(`/workspaces/${workspaceId}/agents/runs/${runId}`);
}

export function runAgent(
  workspaceId: string,
  payload: { agent_type: string; input_payload?: Record<string, unknown> },
) {
  return apiFetch<AgentRunDetail>(`/workspaces/${workspaceId}/agents/run`, {
    method: "POST",
    body: payload,
  });
}

export function listRecommendations(workspaceId: string) {
  return apiFetch<RecommendationPublic[]>(`/workspaces/${workspaceId}/recommendations`);
}

export function getRecommendation(workspaceId: string, recommendationId: string) {
  return apiFetch<RecommendationPublic>(
    `/workspaces/${workspaceId}/recommendations/${recommendationId}`,
  );
}

export function approveRecommendation(
  workspaceId: string,
  recommendationId: string,
  options?: { autoExecute?: boolean },
) {
  return apiFetch<ApproveRecommendationResponse>(
    `/workspaces/${workspaceId}/recommendations/${recommendationId}/approve`,
    {
      method: "POST",
      body: { auto_execute: options?.autoExecute ?? true },
    },
  );
}

export function executeRecommendation(
  workspaceId: string,
  recommendationId: string,
  idempotencyKey?: string,
) {
  return apiFetch<ExecutionPublic>(
    `/workspaces/${workspaceId}/recommendations/${recommendationId}/execute`,
    {
      method: "POST",
      headers: idempotencyKey
        ? { "Idempotency-Key": idempotencyKey }
        : undefined,
    },
  );
}

export function listExecutions(workspaceId: string, recommendationId: string) {
  return apiFetch<ExecutionPublic[]>(
    `/workspaces/${workspaceId}/recommendations/${recommendationId}/executions`,
  );
}

export function revertExecution(workspaceId: string, executionId: string) {
  return apiFetch<ExecutionPublic>(
    `/workspaces/${workspaceId}/recommendations/executions/${executionId}/revert`,
    { method: "POST" },
  );
}

export function rejectRecommendation(
  workspaceId: string,
  recommendationId: string,
  reason?: string,
) {
  return apiFetch<RecommendationPublic>(
    `/workspaces/${workspaceId}/recommendations/${recommendationId}/reject`,
    { method: "POST", body: reason ? { reason } : undefined },
  );
}

export function updateRecommendation(
  workspaceId: string,
  recommendationId: string,
  payload: {
    title?: string;
    summary?: string;
    expected_impact?: string;
    suggested_action?: string;
  },
) {
  return apiFetch<RecommendationPublic>(
    `/workspaces/${workspaceId}/recommendations/${recommendationId}`,
    { method: "PATCH", body: payload },
  );
}

export function listRecommendationAuditLogs(workspaceId: string, recommendationId: string) {
  return apiFetch<AuditLogPublic[]>(
    `/workspaces/${workspaceId}/recommendations/${recommendationId}/audit-logs`,
  );
}
