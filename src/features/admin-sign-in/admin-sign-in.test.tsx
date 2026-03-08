import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock("@mzon7/zon-incubator-sdk/auth", () => ({
  useAuth: vi.fn(),
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  AuthCallback: () => <div>callback</div>,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("../admin-sign-in/lib/useRole", () => ({
  useRole: vi.fn(),
}));

vi.mock("../../lib/supabase", () => ({
  supabase: {},
  dbTable: (name: string) => `deviceatlas_${name}`,
  PROJECT_PREFIX: "deviceatlas_",
}));

import { useAuth } from "@mzon7/zon-incubator-sdk/auth";
import { useRole } from "./lib/useRole";
import AccessDenied from "./components/AccessDenied";
import AdminRoute from "./components/AdminRoute";
import AdminSignInPage from "./components/AdminSignInPage";

const mockUseAuth = vi.mocked(useAuth);
const mockUseRole = vi.mocked(useRole);

function wrap(ui: React.ReactElement, initialEntries = ["/"]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// AccessDenied
// ---------------------------------------------------------------------------
describe("AccessDenied", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({
      user: { email: "user@example.com" } as never,
      session: null,
      loading: false,
      registered: false,
      registrationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
  });

  it("renders the access denied heading", () => {
    wrap(<AccessDenied />);
    expect(screen.getByText("Access Denied")).toBeTruthy();
  });

  it("shows the user email", () => {
    wrap(<AccessDenied />);
    expect(screen.getByText("user@example.com")).toBeTruthy();
  });

  it("shows contact admin message", () => {
    wrap(<AccessDenied />);
    expect(screen.getByText(/Contact your administrator/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// AdminRoute — unauthenticated
// ---------------------------------------------------------------------------
describe("AdminRoute — unauthenticated", () => {
  it("redirects to /login when no user", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      session: null,
      loading: false,
      registered: false,
      registrationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
    mockUseRole.mockReturnValue({
      role: null,
      isLoading: false,
      isAdmin: false,
      isEditor: false,
      isAdminOrEditor: false,
    });

    wrap(
      <AdminRoute>
        <div>secret</div>
      </AdminRoute>,
    );
    expect(screen.queryByText("secret")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// AdminRoute — authenticated but no role
// ---------------------------------------------------------------------------
describe("AdminRoute — authenticated, no role", () => {
  it("renders AccessDenied when role is null", () => {
    mockUseAuth.mockReturnValue({
      user: { email: "viewer@example.com" } as never,
      session: null,
      loading: false,
      registered: false,
      registrationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
    mockUseRole.mockReturnValue({
      role: null,
      isLoading: false,
      isAdmin: false,
      isEditor: false,
      isAdminOrEditor: false,
    });

    wrap(
      <AdminRoute>
        <div>admin content</div>
      </AdminRoute>,
    );
    expect(screen.getByText("Access Denied")).toBeTruthy();
    expect(screen.queryByText("admin content")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// AdminRoute — Admin role grants access
// ---------------------------------------------------------------------------
describe("AdminRoute — Admin role", () => {
  it("renders children when user has Admin role", () => {
    mockUseAuth.mockReturnValue({
      user: { email: "admin@example.com" } as never,
      session: null,
      loading: false,
      registered: false,
      registrationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
    mockUseRole.mockReturnValue({
      role: "Admin",
      isLoading: false,
      isAdmin: true,
      isEditor: true,
      isAdminOrEditor: true,
    });

    wrap(
      <AdminRoute>
        <div>admin content</div>
      </AdminRoute>,
    );
    expect(screen.getByText("admin content")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// AdminSignInPage
// ---------------------------------------------------------------------------
describe("AdminSignInPage", () => {
  it("shows redirecting state while auth is loading", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      session: null,
      loading: true,
      registered: false,
      registrationError: null,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
    });
    wrap(<AdminSignInPage />);
    expect(screen.getByText(/Redirecting/i)).toBeTruthy();
  });
});
