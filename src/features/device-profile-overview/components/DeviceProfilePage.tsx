import { useParams, Link } from "react-router-dom";
import { useDeviceProfile } from "../lib/useDeviceProfile";
import DeviceMetaCard from "./DeviceMetaCard";
import ApprovalSection from "./ApprovalSection";
import DeviceSkeleton from "./DeviceSkeleton";
import PublicHeader from "../../shared/components/PublicHeader";

export default function DeviceProfilePage() {
  const { deviceId } = useParams<{ deviceId: string }>();
  const { data, isLoading, isError, error } = useDeviceProfile(deviceId);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg, #fff0f8 0%, #fff5fb 40%, #fff8fc 100%)",
        position: "relative",
      }}
    >
      {/* Background orbs */}
      <div
        style={{
          position: "fixed",
          top: "10%",
          left: "5%",
          width: 320,
          height: 320,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(244,87,187,0.08) 0%, transparent 70%)",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />
      <div
        style={{
          position: "fixed",
          bottom: "15%",
          right: "8%",
          width: 260,
          height: 260,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(234,16,92,0.06) 0%, transparent 70%)",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />

      <PublicHeader />

      <main
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: 1000,
          margin: "0 auto",
          padding: "32px 16px 64px",
        }}
      >
        {/* Breadcrumb */}
        <nav style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#888" }}>
          <Link
            to="/"
            style={{
              color: "#f457bb",
              textDecoration: "none",
              fontWeight: 500,
              transition: "opacity 0.15s",
            }}
          >
            Home
          </Link>
          <span style={{ color: "#ccc" }}>›</span>
          <Link
            to="/devices"
            style={{
              color: "#f457bb",
              textDecoration: "none",
              fontWeight: 500,
            }}
          >
            Devices
          </Link>
          <span style={{ color: "#ccc" }}>›</span>
          <span style={{ color: "#555" }}>
            {isLoading ? "Loading…" : data?.device?.name ?? "Device"}
          </span>
        </nav>

        {isLoading && <DeviceSkeleton />}

        {isError && !isLoading && (
          <NotFoundState
            message={
              (error as Error)?.message === "Device not found"
                ? "This device doesn't exist or has been removed."
                : "Something went wrong loading this device."
            }
          />
        )}

        {data && !isLoading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {/* Inactive warning */}
            {!data.device.is_active && (
              <div
                style={{
                  padding: "12px 20px",
                  borderRadius: 12,
                  background: "rgba(234,179,8,0.1)",
                  border: "1px solid rgba(234,179,8,0.3)",
                  color: "#92400e",
                  fontSize: 14,
                  fontWeight: 500,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <span>⚠️</span>
                This device is marked as inactive and may no longer be commercially available.
              </div>
            )}

            {/* Main device card */}
            <DeviceMetaCard device={data.device} summary={data.summary} />

            {/* Section header */}
            <div>
              <h2
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: "#111",
                  margin: "8px 0 4px",
                }}
              >
                Regulatory Approvals
              </h2>
              <p style={{ fontSize: 13, color: "#888", margin: "0 0 16px" }}>
                Approved indications by country, sourced from FDA and Health Canada databases.
              </p>
            </div>

            {/* USA approvals */}
            <ApprovalSection country="US" approvals={data.us_approvals} />

            {/* Canada approvals */}
            <ApprovalSection country="CA" approvals={data.ca_approvals} />

            {/* Footer note */}
            <div
              style={{
                fontSize: 12,
                color: "#bbb",
                textAlign: "center",
                paddingTop: 8,
              }}
            >
              Data sourced from FDA PMA/510(k) databases and Health Canada MDALL.
              Last updated:{" "}
              {data.device.updated_at
                ? new Date(data.device.updated_at).toLocaleDateString("en-CA")
                : "N/A"}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function NotFoundState({ message }: { message: string }) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "80px 24px",
        background: "rgba(255,255,255,0.75)",
        backdropFilter: "blur(12px)",
        borderRadius: 20,
        border: "1px solid rgba(244,87,187,0.1)",
      }}
    >
      <div style={{ fontSize: 56, marginBottom: 16 }}>🔍</div>
      <h2 style={{ fontSize: 22, fontWeight: 700, color: "#111", margin: "0 0 8px" }}>
        Device Not Found
      </h2>
      <p style={{ color: "#666", fontSize: 14, maxWidth: 400, margin: "0 auto 24px" }}>
        {message}
      </p>
      <Link
        to="/devices"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "10px 24px",
          borderRadius: 24,
          background: "linear-gradient(135deg, #f457bb, #ea105c)",
          color: "#fff",
          textDecoration: "none",
          fontWeight: 600,
          fontSize: 14,
        }}
      >
        Browse All Devices
      </Link>
    </div>
  );
}
