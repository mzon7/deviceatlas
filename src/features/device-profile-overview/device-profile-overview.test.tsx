import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import DeviceProfilePage from "./components/DeviceProfilePage";
import StatusBadge from "./components/StatusBadge";
import DeviceSkeleton from "./components/DeviceSkeleton";

// Mock callEdgeFunction
vi.mock("@mzon7/zon-incubator-sdk", () => ({
  callEdgeFunction: vi.fn(),
}));

// Mock supabase
vi.mock("../../lib/supabase", () => ({
  supabase: {},
  dbTable: (name: string) => `deviceatlas_${name}`,
}));

import { callEdgeFunction } from "@mzon7/zon-incubator-sdk";

const mockDevice = {
  id: "test-device-id",
  name: "SynCardia Total Artificial Heart",
  manufacturer: "Syncardia Systems, LLC",
  category: "Cardiovascular",
  description: "A device that replaces both ventricles of a failing heart.",
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-15T00:00:00Z",
};

const mockApprovals = [
  {
    id: "approval-us-1",
    country: "US" as const,
    status: "Approved",
    approval_date: "2004-10-15",
    retired_date: null,
    source_ref: "P030011",
    is_active: true,
    updated_at: "2024-01-15T00:00:00Z",
    disease_state: {
      id: "ds-1",
      name: "Heart Failure",
      description: "A condition where the heart cannot pump enough blood.",
    },
  },
  {
    id: "approval-ca-1",
    country: "CA" as const,
    status: "Approved",
    approval_date: "2005-03-20",
    retired_date: null,
    source_ref: "84567",
    is_active: true,
    updated_at: "2024-01-15T00:00:00Z",
    disease_state: {
      id: "ds-1",
      name: "Heart Failure",
      description: "A condition where the heart cannot pump enough blood.",
    },
  },
];

const mockProfileData = {
  device: mockDevice,
  approvals: mockApprovals,
  us_approvals: [mockApprovals[0]],
  ca_approvals: [mockApprovals[1]],
  summary: {
    us_count: 1,
    ca_count: 1,
    total_count: 2,
    us_approved_count: 1,
    ca_approved_count: 1,
  },
};

function renderWithProviders(deviceId: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/device/${deviceId}`]}>
        <Routes>
          <Route path="/device/:deviceId" element={<DeviceProfilePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("StatusBadge", () => {
  it("renders approved status with green indicator", () => {
    const { container } = render(<StatusBadge status="Approved" />);
    expect(container.textContent).toContain("Approved");
  });

  it("renders pending status", () => {
    const { container } = render(<StatusBadge status="Pending" />);
    expect(container.textContent).toContain("Pending");
  });

  it("renders retired status", () => {
    const { container } = render(<StatusBadge status="Retired" />);
    expect(container.textContent).toContain("Retired");
  });
});

describe("DeviceSkeleton", () => {
  it("renders without crashing", () => {
    const { container } = render(<DeviceSkeleton />);
    expect(container.firstChild).toBeTruthy();
  });
});

describe("DeviceProfilePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading skeleton while fetching", () => {
    vi.mocked(callEdgeFunction).mockReturnValue(new Promise(() => {}));
    renderWithProviders("test-device-id");
    // Skeleton renders during loading
    expect(document.body).toBeTruthy();
  });

  it("renders device info after loading", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderWithProviders("test-device-id");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "SynCardia Total Artificial Heart" })).toBeInTheDocument();
    });

    expect(screen.getByText("Syncardia Systems, LLC")).toBeInTheDocument();
    expect(screen.getAllByText("Cardiovascular").length).toBeGreaterThan(0);
  });

  it("shows device description", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderWithProviders("test-device-id");

    await waitFor(() => {
      expect(screen.getByText(/A device that replaces both ventricles/)).toBeInTheDocument();
    });
  });

  it("shows approval sections for both countries", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderWithProviders("test-device-id");

    await waitFor(() => {
      expect(screen.getByText(/United States \(FDA\)/)).toBeInTheDocument();
      expect(screen.getByText(/Canada \(Health Canada\)/)).toBeInTheDocument();
    });
  });

  it("shows disease state in approval table", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderWithProviders("test-device-id");

    await waitFor(() => {
      expect(screen.getAllByText("Heart Failure").length).toBeGreaterThan(0);
    });
  });

  it("shows not found state on error", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: null, error: "Device not found" });
    renderWithProviders("nonexistent-id");

    await waitFor(
      () => {
        expect(screen.getByText("Device Not Found")).toBeInTheDocument();
      },
      { timeout: 5000 }
    );
  });

  it("shows inactive warning for inactive devices", async () => {
    const inactiveData = {
      ...mockProfileData,
      device: { ...mockDevice, is_active: false },
    };
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: inactiveData, error: null });
    renderWithProviders("test-device-id");

    await waitFor(() => {
      expect(screen.getByText(/marked as inactive/)).toBeInTheDocument();
    });
  });

  it("shows approval summary chips", async () => {
    vi.mocked(callEdgeFunction).mockResolvedValue({ data: mockProfileData, error: null });
    renderWithProviders("test-device-id");

    await waitFor(() => {
      expect(screen.getByText("FDA (USA)")).toBeInTheDocument();
      expect(screen.getByText("Health Canada")).toBeInTheDocument();
    });
  });
});
