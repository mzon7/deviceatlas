import type { Approval } from "../../device-profile-overview/lib/useDeviceProfile";
import StatusBadge from "../../device-profile-overview/components/StatusBadge";
import CertificationBadge from "./CertificationBadge";

interface UKApprovalSectionProps {
  approvals: Approval[];
}

const COLOR = "#012169";
const LIGHT_BG = "rgba(1,33,105,0.03)";
const BORDER = "rgba(1,33,105,0.12)";
const HEADER_BG = "rgba(1,33,105,0.05)";

function formatDate(d: string | null) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return d;
  }
}

export default function UKApprovalSection({ approvals }: UKApprovalSectionProps) {
  const hasData = approvals.length > 0;

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.75)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderRadius: 16,
        border: `1px solid ${BORDER}`,
        boxShadow: "0 2px 16px rgba(0,0,0,0.03)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "18px 24px",
          borderBottom: `1px solid ${BORDER}`,
          background: HEADER_BG,
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: 22 }}>🇬🇧</span>
        <span style={{ fontWeight: 700, fontSize: 16, color: "#111" }}>
          United Kingdom (MHRA)
        </span>
        <CertificationBadge type="UKCA" size="sm" />
        {hasData && (
          <span
            style={{
              marginLeft: "auto",
              background: COLOR,
              color: "#fff",
              borderRadius: 12,
              padding: "2px 10px",
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            UKCA Marked
          </span>
        )}
      </div>

      {!hasData ? (
        /* No bulk API — show informational placeholder */
        <div style={{ padding: "24px" }}>
          <div
            style={{
              background: LIGHT_BG,
              border: `1px solid ${BORDER}`,
              borderRadius: 12,
              padding: "20px 24px",
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
              <div style={{ fontSize: 28, flexShrink: 0 }}>ℹ️</div>
              <div>
                <div style={{ fontWeight: 600, color: "#111", fontSize: 14, marginBottom: 6 }}>
                  UK MHRA Data Coming Soon
                </div>
                <div style={{ fontSize: 13, color: "#555", lineHeight: 1.6, marginBottom: 16 }}>
                  The UK Medicines and Healthcare products Regulatory Agency (MHRA) does not
                  currently provide a bulk data API for device registrations. UK data will be
                  added when a machine-readable source becomes available.
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                  <a
                    href="https://www.gov.uk/check-if-a-medical-device-is-registered"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      fontSize: 12,
                      color: COLOR,
                      textDecoration: "none",
                      fontWeight: 600,
                      border: `1.5px solid ${BORDER}`,
                      borderRadius: 8,
                      padding: "6px 12px",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      background: "rgba(255,255,255,0.8)",
                    }}
                  >
                    Check MHRA Register ↗
                  </a>
                  <a
                    href="https://www.gov.uk/guidance/register-medical-devices-for-use-in-great-britain"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      fontSize: 12,
                      color: "#555",
                      textDecoration: "none",
                      border: "1.5px solid rgba(0,0,0,0.1)",
                      borderRadius: 8,
                      padding: "6px 12px",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      background: "rgba(255,255,255,0.8)",
                    }}
                  >
                    UK Registration Guide ↗
                  </a>
                </div>
              </div>
            </div>
          </div>

          {/* UK regulatory context */}
          <div
            style={{
              marginTop: 16,
              padding: "14px 20px",
              background: "rgba(255,255,255,0.6)",
              borderRadius: 10,
              border: "1px solid rgba(0,0,0,0.06)",
              fontSize: 12,
              color: "#777",
              lineHeight: 1.7,
            }}
          >
            <strong style={{ color: "#444" }}>About UK Device Regulation:</strong> Post-Brexit,
            medical devices sold in Great Britain require UKCA marking (equivalent to EU CE marking).
            Devices with CE marking issued before 30 June 2023 may still be valid in the UK under
            transitional provisions. Northern Ireland continues to accept CE marking under the
            Windsor Framework.
          </div>
        </div>
      ) : (
        /* Has UK approval data */
        <div style={{ padding: "20px 24px" }}>
          <div
            style={{
              background: LIGHT_BG,
              border: `1px solid ${BORDER}`,
              borderRadius: 12,
              padding: "16px 20px",
              marginBottom: 20,
              display: "flex",
              flexWrap: "wrap",
              gap: 24,
              alignItems: "center",
            }}
          >
            <div>
              <div style={{ fontSize: 10, color: "#888", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                UK Status
              </div>
              <StatusBadge status="Approved" />
            </div>
            <div>
              <div style={{ fontSize: 10, color: "#888", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                Framework
              </div>
              <span style={{ fontSize: 13, color: "#333", fontWeight: 500 }}>UK MDR 2002 (as amended)</span>
            </div>
            {approvals[0]?.source_ref && (
              <div>
                <div style={{ fontSize: 10, color: "#888", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                  Reference
                </div>
                <span style={{ fontFamily: "monospace", fontSize: 11, background: "rgba(1,33,105,0.08)", padding: "3px 8px", borderRadius: 4, color: COLOR }}>
                  {approvals[0].source_ref}
                </span>
              </div>
            )}
            {approvals[0]?.approval_date && (
              <div>
                <div style={{ fontSize: 10, color: "#888", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                  Date
                </div>
                <span style={{ fontSize: 13, color: "#333" }}>{formatDate(approvals[0].approval_date)}</span>
              </div>
            )}
          </div>

          {approvals.some((a) => a.disease_state) && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ background: LIGHT_BG }}>
                    <th style={thStyle}>Disease / Indication</th>
                    <th style={thStyle}>Status</th>
                    <th style={thStyle}>Reference</th>
                  </tr>
                </thead>
                <tbody>
                  {approvals.filter((a) => a.disease_state).map((approval, idx) => (
                    <tr
                      key={approval.id}
                      style={{
                        borderTop: "1px solid rgba(0,0,0,0.04)",
                        background: idx % 2 === 0 ? "transparent" : "rgba(0,0,0,0.01)",
                      }}
                    >
                      <td style={tdStyle}>
                        <span style={{ fontWeight: 500, color: "#111" }}>
                          {approval.disease_state?.name ?? "—"}
                        </span>
                      </td>
                      <td style={tdStyle}>
                        <StatusBadge status={approval.status} />
                      </td>
                      <td style={tdStyle}>
                        {approval.source_ref ? (
                          <span style={{ fontFamily: "monospace", fontSize: 11, color: COLOR }}>
                            {approval.source_ref}
                          </span>
                        ) : (
                          <span style={{ color: "#ccc" }}>—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: "10px 16px",
  textAlign: "left",
  fontWeight: 600,
  color: "#555",
  fontSize: 11,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const tdStyle: React.CSSProperties = {
  padding: "12px 16px",
  verticalAlign: "top",
};
