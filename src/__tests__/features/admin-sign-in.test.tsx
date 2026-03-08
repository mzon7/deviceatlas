import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import React from "react";
import { AuthContext, type AuthContextValue } from "@mzon7/zon-incubator-sdk/auth";
import LoginPage from "../../pages/LoginPage";
import HomePage from "../../pages/HomePage";

// Mock react-router-dom navigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function makeAuthContext(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    user: null,
    session: null,
    loading: false,
    registered: false,
    registrationError: null,
    signIn: vi.fn().mockResolvedValue({ error: null }),
    signUp: vi.fn().mockResolvedValue({ error: null, needsConfirmation: false }),
    signOut: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

function renderWithAuth(ui: React.ReactElement, ctx: AuthContextValue) {
  return render(
    <MemoryRouter>
      <AuthContext.Provider value={ctx}>{ui}</AuthContext.Provider>
    </MemoryRouter>
  );
}

describe("Admin sign-in", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
  });

  it("signs in admin with valid credentials and navigates to home", async () => {
    const mockSignIn = vi.fn().mockResolvedValue({ error: null });
    const ctx = makeAuthContext({ signIn: mockSignIn });

    renderWithAuth(<LoginPage />, ctx);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "admin@deviceatlas.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "adminpassword123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockSignIn).toHaveBeenCalledWith(
        "admin@deviceatlas.com",
        "adminpassword123"
      );
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/home", { replace: true });
    });

    // No error displayed
    expect(screen.queryByRole("paragraph", { name: /error/i })).toBeNull();
  });

  it("shows error message when credentials are invalid", async () => {
    const mockSignIn = vi.fn().mockResolvedValue({ error: "Invalid login credentials" });
    const ctx = makeAuthContext({ signIn: mockSignIn });

    renderWithAuth(<LoginPage />, ctx);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "admin@deviceatlas.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "wrongpassword" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText("Invalid login credentials")).toBeInTheDocument();
    });

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("disables the submit button while sign-in is in progress", async () => {
    let resolveSignIn!: (val: { error: null }) => void;
    const pendingSignIn = new Promise<{ error: null }>((resolve) => {
      resolveSignIn = resolve;
    });
    const mockSignIn = vi.fn().mockReturnValue(pendingSignIn);
    const ctx = makeAuthContext({ signIn: mockSignIn });

    renderWithAuth(<LoginPage />, ctx);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "admin@deviceatlas.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "adminpassword123" },
    });

    const button = screen.getByRole("button", { name: /sign in/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
    });

    resolveSignIn({ error: null });
  });

  it("authenticated admin user sees email in the header on home page", () => {
    const adminUser = {
      id: "admin-uuid",
      email: "admin@deviceatlas.com",
      app_metadata: {},
      user_metadata: {},
      aud: "authenticated",
      created_at: new Date().toISOString(),
    } as AuthContextValue["user"];

    const ctx = makeAuthContext({ user: adminUser, session: {} as AuthContextValue["session"] });

    renderWithAuth(<HomePage />, ctx);

    expect(screen.getByText("admin@deviceatlas.com")).toBeInTheDocument();
  });
});
