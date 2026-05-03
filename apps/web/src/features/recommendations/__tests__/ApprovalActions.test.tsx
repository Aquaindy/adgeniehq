import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ApprovalActions } from "@/features/recommendations/ApprovalActions";
import { useWorkspaceStore } from "@/stores/workspace-store";
import type {
  ApprovalSnapshot,
  RecommendationPublic,
} from "@/types/api";

function _baseRec(overrides: Partial<RecommendationPublic> = {}): RecommendationPublic {
  return {
    id: "r-1",
    workspace_id: "w-1",
    agent_run_id: "ar-1",
    title: "Pause campaign",
    summary: "—",
    recommendation_type: "campaign.pause",
    risk_level: "low",
    expected_impact: "—",
    suggested_action: "—",
    status: "open",
    platform: "meta_ads",
    metadata: { provider: "meta_ads", action: "campaign.pause" },
    created_at: new Date().toISOString(),
    approval: null,
    executions: [],
    has_executable_action: true,
    ...overrides,
  };
}

function _approval(status: ApprovalSnapshot["status"]): ApprovalSnapshot {
  return {
    id: "a-1",
    status,
    approved_by: status === "approved" || status === "executed" ? "u-1" : null,
    approved_at: null,
    rejected_by: status === "rejected" ? "u-1" : null,
    rejected_at: null,
  };
}

function renderWith(rec: RecommendationPublic) {
  useWorkspaceStore.setState({ currentWorkspaceId: "w-1" });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ApprovalActions rec={rec} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ApprovalActions", () => {
  it("shows Approve + Reject when the approval is pending", () => {
    renderWith(_baseRec({ approval: _approval("pending") }));
    expect(
      screen.getByRole("button", { name: /approve/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reject/i }),
    ).toBeInTheDocument();
  });

  it("hides Reject once the recommendation is approved", () => {
    renderWith(_baseRec({ approval: _approval("approved") }));
    expect(screen.queryByRole("button", { name: /^approve$|approve & apply/i })).not
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reject/i })).toBeInTheDocument();
  });

  it("hides Approve once the recommendation is rejected", () => {
    renderWith(_baseRec({ approval: _approval("rejected") }));
    expect(screen.queryByRole("button", { name: /reject/i })).not
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^approve$|approve & apply/i })).toBeInTheDocument();
  });

  it("hides BOTH actions once the recommendation has been executed", () => {
    renderWith(_baseRec({ approval: _approval("executed") }));
    expect(screen.queryByRole("button", { name: /approve/i })).not
      .toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reject/i })).not
      .toBeInTheDocument();
  });

  it("offers the apply-on-approve toggle only for actionable recommendations", () => {
    // Actionable rec → checkbox visible.
    renderWith(_baseRec({ approval: _approval("pending") }));
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
  });

  it("hides the apply-on-approve toggle when there is no executable action", () => {
    renderWith(
      _baseRec({
        approval: _approval("pending"),
        has_executable_action: false,
        platform: null,
      }),
    );
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
