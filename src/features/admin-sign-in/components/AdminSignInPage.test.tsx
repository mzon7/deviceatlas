import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock SDK auth
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("@mzon7/zon-incubator-sdk/auth", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "@mzon7/zon-incubator-sdk/auth";
import AdminSignInPage from "./AdminSignInPage";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient();
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AdminSignInPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows redirecting spinner while loading", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      session: null,
      loading: true,
      registered: false,
      registrationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
    render(<AdminSignInPage />, { wrapper });
    expect(screen.getByText("Redirecting...")).toBeInTheDocument();
  });

  it("redirects unauthenticated user to /login?redirectTo=/admin/devices", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      session: null,
      loading: false,
      registered: false,
      registrationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
    render(<AdminSignInPage />, { wrapper });
    expect(mockNavigate).toHaveBeenCalledWith(
      "/login?redirectTo=/admin/devices",
      { replace: true }
    );
  });

  it("redirects authenticated user directly to /admin/devices", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: "user-1", email: "admin@test.com" } as never,
      session: {} as never,
      loading: false,
      registered: false,
      registrationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
    render(<AdminSignInPage />, { wrapper });
    expect(mockNavigate).toHaveBeenCalledWith("/admin/devices", { replace: true });
  });
});
