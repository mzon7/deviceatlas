import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@mzon7/zon-incubator-sdk/auth", () => ({
  useAuth: vi.fn(),
}));

vi.mock("../lib/useRole", () => ({
  useRole: vi.fn(),
}));

import { useAuth } from "@mzon7/zon-incubator-sdk/auth";
import { useRole } from "../lib/useRole";
import AdminRoute from "./AdminRoute";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient();
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AdminRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading spinner while auth is loading", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null, session: null, loading: true,
      registered: false, registrationError: null,
      signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(),
    });
    vi.mocked(useRole).mockReturnValue({
      role: null, isLoading: false, isAdmin: false, isEditor: false, isAdminOrEditor: false,
    });
    render(
      <AdminRoute><div>protected</div></AdminRoute>,
      { wrapper }
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
  });

  it("shows loading spinner while role is loading", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: "u1", email: "a@b.com" } as never,
      session: {} as never, loading: false,
      registered: false, registrationError: null,
      signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(),
    });
    vi.mocked(useRole).mockReturnValue({
      role: null, isLoading: true, isAdmin: false, isEditor: false, isAdminOrEditor: false,
    });
    render(
      <AdminRoute><div>protected</div></AdminRoute>,
      { wrapper }
    );
    expect(screen.getByText("Verifying permissions...")).toBeInTheDocument();
  });

  it("renders AccessDenied when user has no admin role", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: "u1", email: "viewer@test.com" } as never,
      session: {} as never, loading: false,
      registered: false, registrationError: null,
      signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(),
    });
    vi.mocked(useRole).mockReturnValue({
      role: "Viewer", isLoading: false, isAdmin: false, isEditor: false, isAdminOrEditor: false,
    });
    render(
      <AdminRoute><div>protected</div></AdminRoute>,
      { wrapper }
    );
    expect(screen.getByText("Access Denied")).toBeInTheDocument();
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
  });

  it("renders children for Admin role", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: "u1", email: "admin@test.com" } as never,
      session: {} as never, loading: false,
      registered: false, registrationError: null,
      signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(),
    });
    vi.mocked(useRole).mockReturnValue({
      role: "Admin", isLoading: false, isAdmin: true, isEditor: false, isAdminOrEditor: true,
    });
    render(
      <AdminRoute><div>protected content</div></AdminRoute>,
      { wrapper }
    );
    expect(screen.getByText("protected content")).toBeInTheDocument();
  });

  it("renders children for Editor role", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: "u2", email: "editor@test.com" } as never,
      session: {} as never, loading: false,
      registered: false, registrationError: null,
      signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(),
    });
    vi.mocked(useRole).mockReturnValue({
      role: "Editor", isLoading: false, isAdmin: false, isEditor: true, isAdminOrEditor: true,
    });
    render(
      <AdminRoute><div>editor content</div></AdminRoute>,
      { wrapper }
    );
    expect(screen.getByText("editor content")).toBeInTheDocument();
  });
});
