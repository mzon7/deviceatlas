import type { Approval } from "../lib/useDeviceProfile";
import StatusBadge from "./StatusBadge";

interface ApprovalSectionProps {
  country: "US" | "CA";
  approvals: Approval[];
}

const COUNTRY_CONFIG = {
  US: {
    flag: "🇺🇸",
    label: "United States (FDA)",
    color: "#f457bb",
    lightBg: "rgba(244,87,187,0.04)",
    borderColor: "rgba(244,87,187,0.12)",
    headerBg: "rgba(244,87,187,0.06)",
  },
  CA: {
    flag: "🇨🇦",
    label: "Canada (Health Canada)",
    color: "#ea105c",
    lightBg: "rgba(234,16,92,0.04)",
    borderColor: "rgba(234,16,92,0.12)",
    headerBg: "rgba(234,16,92,0.06)",
  },
};

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleDateString("en-CA", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export default function ApprovalSection({ country, approvals }: ApprovalSectionProps) {
  const cfg = COUNTRY_CONFIG[country];

  if (approvals.length === 0) {
    return (
      <div
        style={{
          background: "rgba(255,255,255,0.65)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          borderRadius: 16,
          border: `1px solid ${cfg.borderColor}`,
          padding: "28px",
          boxShadow: "0 2px 16px rgba(0,0,0,0.03)",
        }}
      >
        <SectionHeader cfg={cfg} count={0} />
        <div
          style={{
            textAlign: "center",
            padding: "32px 0",
            color: "#999",
            fontSize: 14,
          }}
        >
          <span style={{ fontSize: 32, display: "block", marginBottom: 8 }}>📋</span>
          No approved indications found for this country.
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.75)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderRadius: 16,
        border: `1px solid ${cfg.borderColor}`,
        boxShadow: "0 2px 16px rgba(0,0,0,0.03)",
        overflow: "hidden",
      }}
    >
      <SectionHeader cfg={cfg} count={approvals.length} />

      {/* Desktop table */}
      <div className="hidden md:block" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: cfg.lightBg }}>
              <th style={thStyle}>Disease / Indication</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Approval Date</th>
              <th style={thStyle}>Reference</th>
              <th style={thStyle}>Last Updated</th>
            </tr>
          </thead>
          <tbody>
            {approvals.map((approval, idx) => (
              <tr
                key={approval.id}
                style={{
                  borderTop: "1px solid rgba(0,0,0,0.04)",
                  background: idx % 2 === 0 ? "transparent" : "rgba(0,0,0,0.01)",
                  transition: "background 0.15s",
                }}
              >
                <td style={tdStyle}>
                  <div style={{ fontWeight: 500, color: "#111" }}>
                    {approval.disease_state?.name ?? "—"}
                  </div>
                  {approval.disease_state?.description && (
                    <div style={{ fontSize: 11, color: "#888", marginTop: 2, maxWidth: 280 }}>
                      {approval.disease_state.description.slice(0, 80)}
                      {approval.disease_state.description.length > 80 ? "…" : ""}
                    </div>
                  )}
                </td>
                <td style={tdStyle}>
                  <StatusBadge status={approval.status} />
                </td>
                <td style={tdStyle}>
                  <span style={{ color: "#555" }}>{formatDate(approval.approval_date)}</span>
                </td>
                <td style={tdStyle}>
                  {approval.source_ref ? (
                    <span
                      style={{
                        fontFamily: "monospace",
                        fontSize: 11,
                        background: "rgba(0,0,0,0.04)",
                        padding: "2px 6px",
                        borderRadius: 4,
                        color: "#555",
                      }}
                    >
                      {approval.source_ref}
                    </span>
                  ) : (
                    <span style={{ color: "#ccc" }}>—</span>
                  )}
                </td>
                <td style={tdStyle}>
                  <span style={{ color: "#999", fontSize: 12 }}>
                    {formatDate(approval.updated_at)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden" style={{ padding: "8px 16px 16px" }}>
        {approvals.map((approval) => (
          <div
            key={approval.id}
            style={{
              padding: "14px 16px",
              borderRadius: 12,
              background: "rgba(255,255,255,0.8)",
              border: `1px solid ${cfg.borderColor}`,
              marginBottom: 8,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                marginBottom: 8,
              }}
            >
              <span style={{ fontWeight: 600, color: "#111", fontSize: 14 }}>
                {approval.disease_state?.name ?? "—"}
              </span>
              <StatusBadge status={approval.status} />
            </div>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              <LabelValue label="Approval Date" value={formatDate(approval.approval_date)} />
              {approval.source_ref && (
                <LabelValue label="Reference" value={approval.source_ref} mono />
              )}
            </div>
          </div>
        ))}
      </div>
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
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "12px 16px",
  verticalAlign: "top",
};

function SectionHeader({
  cfg,
  count,
}: {
  cfg: (typeof COUNTRY_CONFIG)[keyof typeof COUNTRY_CONFIG];
  count: number;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "18px 24px",
        borderBottom: "1px solid rgba(0,0,0,0.05)",
        background: cfg.headerBg,
      }}
    >
      <span style={{ fontSize: 22 }}>{cfg.flag}</span>
      <span style={{ fontWeight: 700, fontSize: 16, color: "#111" }}>{cfg.label}</span>
      {count > 0 && (
        <span
          style={{
            marginLeft: "auto",
            background: cfg.color,
            color: "#fff",
            borderRadius: 12,
            padding: "2px 10px",
            fontSize: 12,
            fontWeight: 700,
          }}
        >
          {count} indication{count !== 1 ? "s" : ""}
        </span>
      )}
    </div>
  );
}

function LabelValue({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "#aaa", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>
        {label}
      </div>
      <div
        style={{
          fontSize: 13,
          color: "#333",
          fontFamily: mono ? "monospace" : undefined,
        }}
      >
        {value}
      </div>
    </div>
  );
}
