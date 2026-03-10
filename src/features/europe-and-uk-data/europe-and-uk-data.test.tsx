import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import EUApprovalSection from "./components/EUApprovalSection";
import UKApprovalSection from "./components/UKApprovalSection";
import CertificationBadge from "./components/CertificationBadge";
import { eudamedUrl, mdallUrl } from "./lib/euUkUtils";
import type { Approval } from "../device-profile-overview/lib/useDeviceProfile";

const mockEUApproval: Approval = {
  id: "eu-1",
  country: "EU",
  status: "Approved",
  approval_date: null,
  retired_date: null,
  source_ref: "B-12345678901234",
  is_active: true,
  updated_at: "2024-01-01",
  disease_state: null,
};

const mockEUApprovalWithDS: Approval = {
  ...mockEUApproval,
  id: "eu-2",
  disease_state: { id: "ds-1", name: "Atrial Fibrillation", description: null },
};

describe("EUApprovalSection", () => {
  it("renders empty state when no approvals", () => {
    render(<EUApprovalSection approvals={[]} />);
    expect(screen.getByText(/No EU CE marking data/i)).toBeTruthy();
  });

  it("renders EU header with CE marking badge", () => {
    render(<EUApprovalSection approvals={[mockEUApproval]} />);
    expect(screen.getByText(/European Union/i)).toBeTruthy();
    expect(screen.getByText(/CE Marked/i)).toBeTruthy();
  });

  it("shows UDI reference with EUDAMED link", () => {
    render(<EUApprovalSection approvals={[mockEUApproval]} />);
    expect(screen.getByText("B-12345678901234")).toBeTruthy();
  });

  it("shows indications table when disease_state is present", () => {
    render(<EUApprovalSection approvals={[mockEUApprovalWithDS]} />);
    expect(screen.getByText("Atrial Fibrillation")).toBeTruthy();
  });

  it("shows regulatory framework", () => {
    render(<EUApprovalSection approvals={[mockEUApproval]} />);
    expect(screen.getByText(/EU MDR 2017\/745/i)).toBeTruthy();
  });
});

describe("UKApprovalSection", () => {
  it("renders MHRA placeholder when no approvals", () => {
    render(<UKApprovalSection approvals={[]} />);
    expect(screen.getByText(/UK MHRA Data Coming Soon/i)).toBeTruthy();
    expect(screen.getByText(/Check MHRA Register/i)).toBeTruthy();
  });

  it("renders UK header", () => {
    render(<UKApprovalSection approvals={[]} />);
    expect(screen.getByText(/United Kingdom/i)).toBeTruthy();
  });

  it("renders UK approval data when present", () => {
    const ukApproval: Approval = {
      id: "uk-1",
      country: "UK",
      status: "Approved",
      approval_date: "2022-06-15",
      retired_date: null,
      source_ref: "UK-123456",
      is_active: true,
      updated_at: "2024-01-01",
      disease_state: null,
    };
    render(<UKApprovalSection approvals={[ukApproval]} />);
    expect(screen.getByText(/UKCA Marked/i)).toBeTruthy();
    expect(screen.getByText("UK-123456")).toBeTruthy();
  });
});

describe("CertificationBadge", () => {
  it("renders CE badge", () => {
    render(<CertificationBadge type="CE" />);
    expect(screen.getByText("CE")).toBeTruthy();
  });

  it("renders UKCA badge", () => {
    render(<CertificationBadge type="UKCA" />);
    expect(screen.getByText("UKCA")).toBeTruthy();
  });
});

describe("euUkUtils", () => {
  it("generates correct EUDAMED URL", () => {
    const url = eudamedUrl("B-12345678901234");
    expect(url).toContain("eudamed");
    expect(url).toContain("B-12345678901234");
  });

  it("generates correct MDALL URL", () => {
    const url = mdallUrl("94844");
    expect(url).toContain("health-products.canada.ca");
    expect(url).toContain("94844");
  });
});
