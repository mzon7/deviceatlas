interface CertificationBadgeProps {
  type: "CE" | "UKCA";
  size?: "sm" | "md";
}

export default function CertificationBadge({ type, size = "md" }: CertificationBadgeProps) {
  const isSmall = size === "sm";
  const config = {
    CE: {
      label: "CE",
      sublabel: "EU Certified",
      color: "#003399",
      bg: "rgba(0,51,153,0.06)",
      border: "rgba(0,51,153,0.2)",
    },
    UKCA: {
      label: "UKCA",
      sublabel: "UK Conformity",
      color: "#012169",
      bg: "rgba(1,33,105,0.06)",
      border: "rgba(1,33,105,0.2)",
    },
  }[type];

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: isSmall ? 5 : 8,
        background: config.bg,
        border: `1.5px solid ${config.border}`,
        borderRadius: isSmall ? 8 : 10,
        padding: isSmall ? "4px 8px" : "6px 12px",
      }}
    >
      <div
        style={{
          width: isSmall ? 24 : 32,
          height: isSmall ? 24 : 32,
          borderRadius: "50%",
          border: `2px solid ${config.color}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: isSmall ? 8 : 10,
            fontWeight: 900,
            color: config.color,
            letterSpacing: "-0.5px",
            fontFamily: "serif",
          }}
        >
          {type}
        </span>
      </div>
      {!isSmall && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: config.color }}>{type} Marked</div>
          <div style={{ fontSize: 10, color: "#888" }}>{config.sublabel}</div>
        </div>
      )}
    </div>
  );
}
