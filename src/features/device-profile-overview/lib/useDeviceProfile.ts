import { useQuery } from "@tanstack/react-query";
import { callEdgeFunction } from "@mzon7/zon-incubator-sdk";
import { supabase } from "../../../lib/supabase";

export interface DiseaseState {
  id: string;
  name: string;
  description: string | null;
}

export interface Approval {
  id: string;
  country: "US" | "CA" | "EU" | "UK";
  status: string;
  approval_date: string | null;
  retired_date: string | null;
  source_ref: string | null;
  is_active: boolean;
  updated_at: string;
  disease_state: DiseaseState | null;
}

export interface Device {
  id: string;
  name: string;
  manufacturer: string | null;
  category: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DeviceProfileSummary {
  us_count: number;
  ca_count: number;
  eu_count: number;
  uk_count: number;
  total_count: number;
  us_approved_count: number;
  ca_approved_count: number;
  eu_approved_count: number;
  uk_approved_count: number;
}

export interface DeviceProfileData {
  device: Device;
  approvals: Approval[];
  us_approvals: Approval[];
  ca_approvals: Approval[];
  eu_approvals: Approval[];
  uk_approvals: Approval[];
  summary: DeviceProfileSummary;
}

export function useDeviceProfile(deviceId: string | undefined) {
  return useQuery<DeviceProfileData>({
    queryKey: ["device-profile", deviceId],
    queryFn: async () => {
      const { data, error } = await callEdgeFunction<DeviceProfileData>(
        supabase,
        "device-profile",
        { deviceId }
      );
      if (error) throw new Error(error);
      if (!data) throw new Error("No data returned");
      return data;
    },
    enabled: Boolean(deviceId),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}
