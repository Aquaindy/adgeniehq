import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequireWorkspace } from "@/features/workspaces/RequireWorkspace";
import * as workspacesLib from "@/lib/workspaces";
import { useWorkspaceStore } from "@/stores/workspace-store";

function renderWith(initialPath = "/") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/workspaces" element={<div>Workspace selector</div>} />
          <Route element={<RequireWorkspace />}>
            <Route path="/" element={<div>Inside workspace</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequireWorkspace", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({ currentWorkspaceId: null });
    vi.restoreAllMocks();
  });

  it("redirects to /workspaces when the user has zero memberships", async () => {
    vi.spyOn(workspacesLib, "listWorkspaces").mockResolvedValue([]);
    renderWith();
    expect(
      await screen.findByText("Workspace selector"),
    ).toBeInTheDocument();
  });

  it("auto-selects the first membership and renders the outlet", async () => {
    vi.spyOn(workspacesLib, "listWorkspaces").mockResolvedValue([
      {
        id: "ws-1",
        name: "Acme",
        slug: "acme",
        created_at: new Date().toISOString(),
        role: "owner",
        status: "active",
      },
    ]);

    renderWith();
    expect(await screen.findByText("Inside workspace")).toBeInTheDocument();
    await waitFor(() =>
      expect(useWorkspaceStore.getState().currentWorkspaceId).toBe("ws-1"),
    );
  });
});
