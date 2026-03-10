import type { Approval } from "../../device-profile-overview/lib/useDeviceProfile";
import StatusBadge from "../../device-profile-overview/components/StatusBadge";
import CertificationBadge from "./CertificationBadge";

interface EUApprovalSectionProps {
  approvals: Approval[];
}

const COLOR = "#003399";
const LIGHT_BG = "rgba(0,51,153,0.03)";
const BORDER = "rgba(0,51,153,0.12)";
const HEADER_BG = "rgba(0,51,153,0.05)";

function eudamedLink(basicUdi: string | null) {
  if (!basicUdi) return null;
  return `https://ec.europa.eu/tools/eudamed/#/screen/search-device?basicUdi=${encodeURIComponent(basicUdi)}`;
}

export default function EUApprovalSection({ approvals }: EUApprovalSectionProps) {
  const hasIndications = approvals.some((a) => a.disease_state != null);

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
        <span style={{ fontSize: 22 }}>🇪🇺</span>
        <span style={{ fontWeight: 700, fontSize: 16, color: "#111" }}>
          European Union (EUDAMED)
        </span>
        <CertificationBadge type="CE" size="sm" />
        {approvals.length > 0 && (
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
            CE Marked
          </span>
        )}
      </div>

      {approvals.length === 0 ? (
        <div style={{ textAlign: "center", padding: "32px 0", color: "#999", fontSize: 14 }}>
          <span style={{ fontSize: 32, display: "block", marginBottom: 8 }}>📋</span>
          No EU CE marking data found for this device.
        </div>
      ) : (
        <div style={{ padding: "20px 24px" }}>
          {/* CE marking info panel */}
          <div
            style={{
              background: LIGHT_BG,
              border: `1px solid ${BORDER}`,
              borderRadius: 12,
              padding: "16px 20px",
              marginBottom: hasIndications ? 20 : 0,
              display: "flex",
              flexWrap: "wrap",
              gap: 24,
              alignItems: "center",
            }}
          >
            <div>
              <div style={{ fontSize: 10, color: "#888", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                EU Status
              </div>
              <StatusBadge status="Approved" />
            </div>
            <div>
              <div style={{ fontSize: 10, color: "#888", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                Regulatory Framework
              </div>
              <span style={{ fontSize: 13, color: "#333", fontWeight: 500 }}>EU MDR 2017/745</span>
            </div>
            {approvals[0]?.source_ref && (
              <div>
                <div style={{ fontSize: 10, color: "#888", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                  Basic UDI-DI
                </div>
                <a
                  href={eudamedLink(approvals[0].source_ref) ?? "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    fontFamily: "monospace",
                    fontSize: 11,
                    background: "rgba(0,51,153,0.08)",
                    padding: "3px 8px",
                    borderRadius: 4,
                    color: COLOR,
                    textDecoration: "none",
                    border: `1px solid ${BORDER}`,
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  {approvals[0].source_ref}
                  <span style={{ fontSize: 10 }}>↗</span>
                </a>
              </div>
            )}
            <div style={{ marginLeft: "auto" }}>
              <a
                href="https://ec.europa.eu/tools/eudamed"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontSize: 12,
                  color: COLOR,
                  textDecoration: "none",
                  fontWeight: 500,
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                View on EUDAMED ↗
              </a>
            </div>
          </div>

          {/* Indications table (if Grok has enriched) */}
          {hasIndications && (
            <>
              <div style={{ fontSize: 12, color: "#888", marginBottom: 12, fontWeight: 500 }}>
                Approved Indications (inherited from FDA data or Grok-enriched)
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: LIGHT_BG }}>
                      <th style={thStyle}>Disease / Indication</th>
                      <th style={thStyle}>Status</th>
                      <th style={thStyle}>UDI Reference</th>
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
                            <a
                              href={eudamedLink(approval.source_ref) ?? "#"}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ fontFamily: "monospace", fontSize: 11, color: COLOR }}
                            >
                              {approval.source_ref}
                            </a>
                          ) : (
                            <span style={{ color: "#ccc" }}>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
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
