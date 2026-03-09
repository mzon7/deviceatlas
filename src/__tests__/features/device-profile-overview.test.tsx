import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMockSupabase } from "@mzon7/zon-incubator-sdk/test";
import DeviceProfilePage from "../../features/device-profile-overview/components/DeviceProfilePage";

// Mock callEdgeFunction — the hook uses it to fetch device profile data
vi.mock("@mzon7/zon-incubator-sdk", () => ({
  callEdgeFunction: vi.fn(),
}));

// Mock supabase lib so the component doesn't try real network calls
vi.mock("../../lib/supabase", () => ({
  supabase: createMockSupabase(),
  dbTable: (name: string) => `deviceatlas_${name}`,
}));

import { callEdgeFunction } from "@mzon7/zon-incubator-sdk";

// ─── Fixtures ────────────────────────────────────────────────────────────────

const knownDevice = {
  id: "device-abc-123",
  name: "SynCardia Total Artificial Heart",
  manufacturer: "Syncardia Systems, LLC",
  category: "Cardiovascular",
  description:
    "A mechanical device that replaces both ventricles of the failing heart, bridging patients to transplant.",
  is_active: true,
  created_at: "2004-10-01T00:00:00Z",
  updated_at: "2024-06-15T00:00:00Z",
};

const heartFailureState = {
  id: "ds-hf-001",
  name: "Heart Failure",
  description: "A chronic condition where the heart cannot pump sufficient blood.",
};

const usApproval = {
  id: "approval-us-hf",
  country: "US" as const,
  status: "Approved",
  approval_date: "2004-10-15",
  retired_date: null,
  source_ref: "P030011",
  is_active: true,
  updated_at: "2024-06-15T00:00:00Z",
  disease_state: heartFailureState,
};

const caApproval = {
  id: "approval-ca-hf",
  country: "CA" as const,
  status: "Approved",
  approval_date: "2005-05-20",
  retired_date: null,
  source_ref: "123456",
  is_active: true,
  updated_at: "2024-06-15T00:00:00Z",
  disease_state: heartFailureState,
};

const mockProfileData = {
  device: knownDevice,
  approvals: [usApproval, caApproval],
  us_approvals: [usApproval],
  ca_approvals: [caApproval],
  summary: {
    us_count: 1,
    ca_count: 1,
    total_count: 2,
    us_approved_count: 1,
    ca_approved_count: 1,
  },
};

// ─── Render helper ───────────────────────────────────────────────────────────

function renderDeviceProfile(deviceId = "device-abc-123") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/device/${deviceId}`]}>
        <Routes>
          <Route path="/device/:deviceId" element={<DeviceProfilePage />} />
          <Route path="/devices" element={<div>Devices list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("Device profile overview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("Device detail shows device metadata for a known device — name matches stored record", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      // The device name is rendered as an h1 heading
      expect(
        screen.getByRole("heading", { name: "SynCardia Total Artificial Heart" })
      ).toBeInTheDocument();
    });
  });

  it("Device detail shows device metadata for a known device — manufacturer matches stored record", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      expect(screen.getByText("Syncardia Systems, LLC")).toBeInTheDocument();
    });
  });

  it("Device detail shows device metadata for a known device — category matches stored record", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      // Category appears in meta card
      expect(screen.getAllByText("Cardiovascular").length).toBeGreaterThan(0);
    });
  });

  it("device-profile edge function is called with the correct deviceId", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      expect(vi.mocked(callEdgeFunction)).toHaveBeenCalledWith(
        expect.anything(),
        "device-profile",
        { deviceId: "device-abc-123" }
      );
    });
  });

  it("displays the device description on the profile page", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      expect(screen.getByText(/replaces both ventricles/)).toBeInTheDocument();
    });
  });

  it("shows FDA approval section with correct country label", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      expect(screen.getByText(/United States \(FDA\)/)).toBeInTheDocument();
    });
  });

  it("shows Health Canada approval section with correct country label", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      expect(screen.getByText(/Canada \(Health Canada\)/)).toBeInTheDocument();
    });
  });

  it("shows disease state name in the approval table", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      expect(screen.getAllByText("Heart Failure").length).toBeGreaterThan(0);
    });
  });

  it("shows 'Device Not Found' when the device does not exist", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: null, error: "Device not found" });
    renderDeviceProfile("nonexistent-id");

    await waitFor(
      () => {
        expect(screen.getByText("Device Not Found")).toBeInTheDocument();
      },
      { timeout: 5000 }
    );
  });

  it("shows inactive warning banner for an inactive device", async () => {
    const inactiveProfile = {
      ...mockProfileData,
      device: { ...knownDevice, is_active: false },
    };
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: inactiveProfile, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      expect(screen.getByText(/marked as inactive/)).toBeInTheDocument();
    });
  });

  it("shows FDA approval summary chip on the meta card", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      expect(screen.getByText("FDA (USA)")).toBeInTheDocument();
    });
  });

  it("shows Health Canada approval summary chip on the meta card", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderDeviceProfile("device-abc-123");

    await waitFor(() => {
      expect(screen.getByText("Health Canada")).toBeInTheDocument();
    });
  });
});
