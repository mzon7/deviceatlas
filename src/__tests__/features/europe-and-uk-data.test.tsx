import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMockSupabase } from "@mzon7/zon-incubator-sdk/test";

// Mock callEdgeFunction — the hook uses it to fetch device profile data
vi.mock("@mzon7/zon-incubator-sdk", () => ({
  callEdgeFunction: vi.fn(),
}));

// Mock supabase lib
vi.mock("../../lib/supabase", () => ({
  supabase: createMockSupabase(),
  dbTable: (name: string) => `deviceatlas_${name}`,
}));

import { callEdgeFunction } from "@mzon7/zon-incubator-sdk";
import DeviceProfilePage from "../../features/device-profile-overview/components/DeviceProfilePage";

// ─── Fixtures ────────────────────────────────────────────────────────────────

const baseDevice = {
  id: "eu-device-001",
  name: "Transcatheter Aortic Valve System",
  manufacturer: "Edwards Lifesciences",
  category: "Cardiovascular",
  description: "A transcatheter aortic valve replacement system for severe aortic stenosis.",
  is_active: true,
  created_at: "2011-11-02T00:00:00Z",
  updated_at: "2024-01-15T00:00:00Z",
};

const aorticStenosisDS = {
  id: "ds-as-001",
  name: "Aortic Stenosis",
  description: "Narrowing of the aortic valve opening restricting blood flow.",
};

const usApproval = {
  id: "approval-us-as",
  country: "US" as const,
  status: "Approved",
  approval_date: "2011-11-02",
  retired_date: null,
  source_ref: "P100041",
  is_active: true,
  updated_at: "2024-01-15T00:00:00Z",
  disease_state: aorticStenosisDS,
};

const euApprovalWithUDI = {
  id: "approval-eu-as",
  country: "EU" as const,
  status: "Approved",
  approval_date: null,
  retired_date: null,
  source_ref: "B-12345678901234",
  is_active: true,
  updated_at: "2024-01-15T00:00:00Z",
  disease_state: null,
};

const euApprovalWithDS = {
  ...euApprovalWithUDI,
  id: "approval-eu-as-2",
  disease_state: aorticStenosisDS,
};

const ukApproval = {
  id: "approval-uk-as",
  country: "UK" as const,
  status: "Approved",
  approval_date: "2021-07-01",
  retired_date: null,
  source_ref: "UK-MED-98765",
  is_active: true,
  updated_at: "2024-01-15T00:00:00Z",
  disease_state: null,
};

// ─── Render helper ───────────────────────────────────────────────────────────

function renderDeviceProfile(deviceId = "eu-device-001") {
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

describe("Europe and UK data", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Happy path: EU section appears with EUDAMED data ──────────────────────

  it("shows European Union (EUDAMED) section header when EU approvals exist", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [usApproval, euApprovalWithUDI],
        us_approvals: [usApproval],
        ca_approvals: [],
        eu_approvals: [euApprovalWithUDI],
        uk_approvals: [],
        summary: {
          us_count: 1, ca_count: 0, total_count: 2,
          us_approved_count: 1, ca_approved_count: 0,
          eu_count: 1, uk_count: 0, eu_approved_count: 1, uk_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getByText(/European Union \(EUDAMED\)/)).toBeInTheDocument();
    });
  });

  it("shows CE Marked badge when device has EU approval", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [euApprovalWithUDI],
        us_approvals: [],
        ca_approvals: [],
        eu_approvals: [euApprovalWithUDI],
        uk_approvals: [],
        summary: {
          us_count: 0, ca_count: 0, total_count: 1,
          us_approved_count: 0, ca_approved_count: 0,
          eu_count: 1, uk_count: 0, eu_approved_count: 1, uk_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getByText("CE Marked")).toBeInTheDocument();
    });
  });

  it("displays Basic UDI-DI source_ref from EUDAMED in EU section", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [euApprovalWithUDI],
        us_approvals: [],
        ca_approvals: [],
        eu_approvals: [euApprovalWithUDI],
        uk_approvals: [],
        summary: {
          us_count: 0, ca_count: 0, total_count: 1,
          us_approved_count: 0, ca_approved_count: 0,
          eu_count: 1, uk_count: 0, eu_approved_count: 1, uk_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getByText("B-12345678901234")).toBeInTheDocument();
    });
  });

  it("shows EU MDR 2017/745 regulatory framework in EU section", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [euApprovalWithUDI],
        us_approvals: [],
        ca_approvals: [],
        eu_approvals: [euApprovalWithUDI],
        uk_approvals: [],
        summary: {
          us_count: 0, ca_count: 0, total_count: 1,
          us_approved_count: 0, ca_approved_count: 0,
          eu_count: 1, uk_count: 0, eu_approved_count: 1, uk_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getByText(/EU MDR 2017\/745/)).toBeInTheDocument();
    });
  });

  it("shows disease state name in EU approvals table when Grok-enriched", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [euApprovalWithDS],
        us_approvals: [],
        ca_approvals: [],
        eu_approvals: [euApprovalWithDS],
        uk_approvals: [],
        summary: {
          us_count: 0, ca_count: 0, total_count: 1,
          us_approved_count: 0, ca_approved_count: 0,
          eu_count: 1, uk_count: 0, eu_approved_count: 1, uk_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getAllByText("Aortic Stenosis").length).toBeGreaterThan(0);
    });
  });

  // ── Happy path: UK section ─────────────────────────────────────────────────

  it("shows United Kingdom (MHRA) section header", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [usApproval],
        us_approvals: [usApproval],
        ca_approvals: [],
        eu_approvals: [],
        uk_approvals: [],
        summary: {
          us_count: 1, ca_count: 0, total_count: 1,
          us_approved_count: 1, ca_approved_count: 0,
          eu_count: 0, uk_count: 0, eu_approved_count: 0, uk_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getByText(/United Kingdom \(MHRA\)/)).toBeInTheDocument();
    });
  });

  it("shows MHRA placeholder when no UK approvals exist", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [usApproval],
        us_approvals: [usApproval],
        ca_approvals: [],
        eu_approvals: [],
        uk_approvals: [],
        summary: {
          us_count: 1, ca_count: 0, total_count: 1,
          us_approved_count: 1, ca_approved_count: 0,
          eu_count: 0, uk_count: 0, eu_approved_count: 0, uk_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getByText(/UK MHRA Data Coming Soon/i)).toBeInTheDocument();
    });
  });

  it("shows UKCA Marked badge and reference when UK approval exists", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [ukApproval],
        us_approvals: [],
        ca_approvals: [],
        eu_approvals: [],
        uk_approvals: [ukApproval],
        summary: {
          us_count: 0, ca_count: 0, total_count: 1,
          us_approved_count: 0, ca_approved_count: 0,
          eu_count: 0, uk_count: 1, eu_approved_count: 0, uk_approved_count: 1,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getByText("UKCA Marked")).toBeInTheDocument();
      expect(screen.getByText("UK-MED-98765")).toBeInTheDocument();
    });
  });

  // ── Edge cases ────────────────────────────────────────────────────────────

  it("shows 'No EU CE marking data' empty state when eu_approvals is empty array", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [],
        us_approvals: [],
        ca_approvals: [],
        eu_approvals: [],
        uk_approvals: [],
        summary: {
          us_count: 0, ca_count: 0, total_count: 0,
          us_approved_count: 0, ca_approved_count: 0,
          eu_count: 0, uk_count: 0, eu_approved_count: 0, uk_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getByText(/No EU CE marking data/i)).toBeInTheDocument();
    });
  });

  it("renders EU and UK sections alongside FDA section for multi-country device", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [usApproval, euApprovalWithUDI, ukApproval],
        us_approvals: [usApproval],
        ca_approvals: [],
        eu_approvals: [euApprovalWithUDI],
        uk_approvals: [ukApproval],
        summary: {
          us_count: 1, ca_count: 0, total_count: 3,
          us_approved_count: 1, ca_approved_count: 0,
          eu_count: 1, uk_count: 1, eu_approved_count: 1, uk_approved_count: 1,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      expect(screen.getByText(/United States \(FDA\)/)).toBeInTheDocument();
      expect(screen.getByText(/European Union \(EUDAMED\)/)).toBeInTheDocument();
      expect(screen.getByText(/United Kingdom \(MHRA\)/)).toBeInTheDocument();
    });
  });

  it("EU section renders without crash when eu_approvals is missing from response", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [usApproval],
        us_approvals: [usApproval],
        ca_approvals: [],
        // eu_approvals and uk_approvals deliberately omitted
        summary: {
          us_count: 1, ca_count: 0, total_count: 1,
          us_approved_count: 1, ca_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      // Device name must still render — no crash from missing eu/uk arrays
      expect(screen.getByRole("heading", { name: baseDevice.name })).toBeInTheDocument();
    });
  });

  // ── Error handling ────────────────────────────────────────────────────────

  it("shows Device Not Found when edge function returns error (EU device lookup failure)", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: null,
      error: "Device not found",
    });
    renderDeviceProfile("nonexistent-eu-device");

    await waitFor(
      () => {
        expect(screen.getByText("Device Not Found")).toBeInTheDocument();
      },
      { timeout: 5000 }
    );
  });

  it("Check MHRA Register link is present in UK placeholder", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({
      data: {
        device: baseDevice,
        approvals: [],
        us_approvals: [],
        ca_approvals: [],
        eu_approvals: [],
        uk_approvals: [],
        summary: {
          us_count: 0, ca_count: 0, total_count: 0,
          us_approved_count: 0, ca_approved_count: 0,
          eu_count: 0, uk_count: 0, eu_approved_count: 0, uk_approved_count: 0,
        },
      },
      error: null,
    });
    renderDeviceProfile();

    await waitFor(() => {
      const mhraLink = screen.getByRole("link", { name: /Check MHRA Register/i });
      expect(mhraLink).toBeInTheDocument();
      expect(mhraLink).toHaveAttribute("href", expect.stringContaining("gov.uk"));
    });
  });
});
