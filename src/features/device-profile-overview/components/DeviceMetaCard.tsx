import type { Device, DeviceProfileSummary, EnrichmentMethod } from "../lib/useDeviceProfile";

interface DeviceMetaCardProps {
  device: Device;
  summary: DeviceProfileSummary;
}

const CATEGORY_ICONS: Record<string, string> = {
  Cardiovascular: "🫀",
  Neurology: "🧠",
  Orthopedic: "🦴",
  Ophthalmology: "👁️",
  Gastroenterology: "🫁",
  Endocrinology: "⚗️",
  "General Surgery": "🏥",
};

export default function DeviceMetaCard({ device, summary }: DeviceMetaCardProps) {
  const icon = CATEGORY_ICONS[device.category ?? ""] ?? "🔬";

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.75)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderRadius: 20,
        border: "1px solid rgba(244,87,187,0.18)",
        boxShadow: "0 4px 32px rgba(244,87,187,0.07), 0 1px 4px rgba(0,0,0,0.04)",
        padding: "32px",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Subtle glow accent */}
      <div
        style={{
          position: "absolute",
          top: -60,
          right: -60,
          width: 200,
          height: 200,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(244,87,187,0.08) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />

      <div className="flex flex-col md:flex-row md:items-start gap-6">
        {/* Device icon */}
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: 18,
            background: "linear-gradient(135deg, rgba(244,87,187,0.12), rgba(234,16,92,0.08))",
            border: "1px solid rgba(244,87,187,0.2)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 32,
            flexShrink: 0,
          }}
        >
          {icon}
        </div>

        {/* Device info */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-start gap-2 mb-1">
            <h1
              style={{
                fontSize: 26,
                fontWeight: 700,
                color: "#111",
                lineHeight: 1.2,
                margin: 0,
              }}
            >
              {device.name}
            </h1>
            {!device.is_active && (
              <span
                style={{
                  padding: "2px 10px",
                  borderRadius: 20,
                  fontSize: 11,
                  fontWeight: 600,
                  background: "rgba(239,68,68,0.1)",
                  color: "#dc2626",
                  alignSelf: "center",
                }}
              >
                INACTIVE
              </span>
            )}
          </div>

          {/* Manufacturer & Category */}
          <div
            style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", marginBottom: 12 }}
          >
            {device.manufacturer && (
              <span style={{ fontSize: 14, color: "#666", display: "flex", alignItems: "center", gap: 4 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
                  <polyline points="9 22 9 12 15 12 15 22"/>
                </svg>
                {device.manufacturer}
              </span>
            )}
            {device.category && (
              <span style={{ fontSize: 14, color: "#666", display: "flex", alignItems: "center", gap: 4 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/>
                  <line x1="7" y1="7" x2="7.01" y2="7"/>
                </svg>
                {device.category}
              </span>
            )}
          </div>

          {/* Description */}
          {device.description && (
            <p
              style={{
                fontSize: 14,
                lineHeight: 1.65,
                color: "#444",
                margin: "0 0 8px 0",
                maxWidth: 680,
              }}
            >
              {device.description}
            </p>
          )}

          {/* Data quality badge */}
          {device.enrichment_method && (
            <div style={{ marginBottom: 16 }}>
              <EnrichmentBadge method={device.enrichment_method} source={device.indications_source} />
            </div>
          )}

          {/* Approval summary chips */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            <ApprovalChip
              flag="🇺🇸"
              label="FDA (USA)"
              count={summary.us_approved_count}
              total={summary.us_count}
              color="#f457bb"
            />
            <ApprovalChip
              flag="🇨🇦"
              label="Health Canada"
              count={summary.ca_approved_count}
              total={summary.ca_count}
              color="#ea105c"
            />
            {(summary.eu_count ?? 0) > 0 && (
              <ApprovalChip
                flag="🇪🇺"
                label="EU (EUDAMED)"
                count={summary.eu_approved_count ?? 0}
                total={summary.eu_count ?? 0}
                color="#003399"
              />
            )}
            {(summary.uk_count ?? 0) > 0 && (
              <ApprovalChip
                flag="🇬🇧"
                label="UK (MHRA)"
                count={summary.uk_approved_count ?? 0}
                total={summary.uk_count ?? 0}
                color="#012169"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface ApprovalChipProps {
  flag: string;
  label: string;
  count: number;
  total: number;
  color: string;
}

interface EnrichmentBadgeProps {
  method: EnrichmentMethod;
  source: string | null;
}

function EnrichmentBadge({ method, source }: EnrichmentBadgeProps) {
  if (!method || method === "not_enriched") return null;

  const isFDA = method === "fda_classification";
  const label = isFDA ? "FDA-grounded data" : "AI-inferred data";
  const tooltip = isFDA
    ? source ?? "Disease states sourced from FDA Product Classification"
    : "Indications inferred by AI from device trade name only";
  const color = isFDA ? "#16a34a" : "#d97706";
  const bg = isFDA ? "rgba(22,163,74,0.07)" : "rgba(217,119,6,0.07)";
  const border = isFDA ? "rgba(22,163,74,0.2)" : "rgba(217,119,6,0.2)";
  const icon = isFDA ? "✓" : "~";

  return (
    <div
      title={tooltip}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "3px 10px",
        borderRadius: 20,
        background: bg,
        border: `1px solid ${border}`,
        fontSize: 11,
        fontWeight: 600,
        color,
        cursor: "default",
      }}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </div>
  );
}

function ApprovalChip({ flag, label, count, total, color }: ApprovalChipProps) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 16px",
        borderRadius: 24,
        background: `rgba(${color === "#f457bb" ? "244,87,187" : "234,16,92"},0.08)`,
        border: `1px solid ${color}30`,
        fontSize: 13,
        fontWeight: 500,
      }}
    >
      <span style={{ fontSize: 16 }}>{flag}</span>
      <span style={{ color: "#333" }}>{label}</span>
      <span
        style={{
          background: color,
          color: "#fff",
          borderRadius: 12,
          padding: "1px 8px",
          fontSize: 12,
          fontWeight: 700,
        }}
      >
        {count}
        {total > count ? `/${total}` : ""} approved
      </span>
    </div>
  );
}
