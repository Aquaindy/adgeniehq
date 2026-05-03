import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { RequireAuth } from "@/features/auth/RequireAuth";
import { useAuthStore } from "@/stores/auth-store";

function _resetAuth(state: Partial<ReturnType<typeof useAuthStore.getState>>) {
  useAuthStore.setState({
    accessToken: null,
    user: null,
    hydrated: false,
    ...state,
  });
}

function renderWithRouter(initialPath = "/protected") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div>Login screen</div>} />
        <Route element={<RequireAuth />}>
          <Route path="/protected" element={<div>Protected content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  beforeEach(() => {
    _resetAuth({});
  });

  it("shows the restoring-session indicator until hydration completes", () => {
    _resetAuth({ hydrated: false, user: null });
    renderWithRouter();
    expect(screen.getByText(/restoring session/i)).toBeInTheDocument();
  });

  it("redirects to /login once hydrated and no user is present", () => {
    _resetAuth({ hydrated: true, user: null });
    renderWithRouter();
    expect(screen.getByText("Login screen")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("renders the protected outlet when a user is present", () => {
    _resetAuth({
      hydrated: true,
      user: {
        id: "u-1",
        email: "alice@example.com",
        full_name: "Alice",
        is_active: true,
        is_superuser: false,
        email_verified_at: null,
        created_at: new Date().toISOString(),
      },
    });
    renderWithRouter();
    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });
});
