import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "@/features/auth/LoginPage";
import * as authLib from "@/lib/auth";

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>Dashboard</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders email + password fields and a submit button", () => {
    renderLogin();
    expect(screen.getByLabelText(/work email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /sign in/i }),
    ).toBeInTheDocument();
  });

  it("calls loginRequest with the form values and routes to /", async () => {
    const user = userEvent.setup();
    const fakeUser = {
      id: "u-1",
      email: "alice@example.com",
      full_name: "Alice",
      is_active: true,
      is_superuser: false,
      email_verified_at: null,
      created_at: new Date().toISOString(),
    };
    const loginSpy = vi.spyOn(authLib, "loginRequest").mockResolvedValue({
      access_token: "tok",
      token_type: "bearer",
      expires_in: 1800,
      user: fakeUser,
    });

    renderLogin();
    await user.type(screen.getByLabelText(/work email/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "secret-pw-9");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(loginSpy).toHaveBeenCalledWith({
      email: "alice@example.com",
      password: "secret-pw-9",
    });
    // Successful login → redirect to "/" → renders the Dashboard route.
    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
  });

  it("renders a friendly error when the login API rejects", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    vi.spyOn(authLib, "loginRequest").mockRejectedValue(
      new ApiError("Invalid email or password.", { status: 401, code: "invalid_credentials" }),
    );

    renderLogin();
    await user.type(screen.getByLabelText(/work email/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/invalid email or password/i);
  });
});
