interface StatusBadgeProps {
  status: string;
}

const STATUS_STYLES: Record<string, { bg: string; color: string; dot: string }> = {
  Approved: {
    bg: "rgba(34,197,94,0.12)",
    color: "#16a34a",
    dot: "#22c55e",
  },
  Pending: {
    bg: "rgba(234,179,8,0.12)",
    color: "#ca8a04",
    dot: "#eab308",
  },
  Retired: {
    bg: "rgba(107,114,128,0.12)",
    color: "#6b7280",
    dot: "#9ca3af",
  },
  Declined: {
    bg: "rgba(239,68,68,0.12)",
    color: "#dc2626",
    dot: "#ef4444",
  },
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] ?? {
    bg: "rgba(107,114,128,0.1)",
    color: "#6b7280",
    dot: "#9ca3af",
  };

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 10px",
        borderRadius: 20,
        fontSize: 12,
        fontWeight: 600,
        background: style.bg,
        color: style.color,
        letterSpacing: "0.02em",
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: style.dot,
          display: "inline-block",
        }}
      />
      {status}
    </span>
  );
}
