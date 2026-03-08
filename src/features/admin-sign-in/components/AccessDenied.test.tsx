import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@mzon7/zon-incubator-sdk/auth", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "@mzon7/zon-incubator-sdk/auth";
import AccessDenied from "./AccessDenied";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient();
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AccessDenied", () => {
  it("shows user email and access denied message", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: "u1", email: "viewer@test.com" } as never,
      session: {} as never, loading: false,
      registered: false, registrationError: null,
      signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(),
    });
    render(<AccessDenied />, { wrapper });
    expect(screen.getByText("Access Denied")).toBeInTheDocument();
    expect(screen.getByText(/viewer@test\.com/)).toBeInTheDocument();
    expect(screen.getByText(/Contact your administrator/)).toBeInTheDocument();
  });

  it("shows sign out button", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: "u1", email: "viewer@test.com" } as never,
      session: {} as never, loading: false,
      registered: false, registrationError: null,
      signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(),
    });
    render(<AccessDenied />, { wrapper });
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });
});
