export default function DeviceSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      {/* Meta card skeleton */}
      <div
        style={{
          background: "rgba(255,255,255,0.7)",
          backdropFilter: "blur(12px)",
          borderRadius: "16px",
          border: "1px solid rgba(244,87,187,0.15)",
          padding: "28px",
        }}
      >
        <div className="flex flex-col md:flex-row md:items-start gap-6">
          {/* Icon placeholder */}
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: "14px",
              background: "rgba(244,87,187,0.1)",
              flexShrink: 0,
            }}
          />
          <div className="flex-1 space-y-3">
            <div style={{ height: 28, width: "60%", background: "rgba(244,87,187,0.1)", borderRadius: 8 }} />
            <div style={{ height: 18, width: "35%", background: "rgba(0,0,0,0.06)", borderRadius: 6 }} />
            <div style={{ height: 14, width: "80%", background: "rgba(0,0,0,0.05)", borderRadius: 6 }} />
            <div style={{ height: 14, width: "70%", background: "rgba(0,0,0,0.05)", borderRadius: 6 }} />
            <div className="flex gap-3 mt-4">
              <div style={{ height: 32, width: 120, background: "rgba(244,87,187,0.12)", borderRadius: 20 }} />
              <div style={{ height: 32, width: 120, background: "rgba(234,16,92,0.1)", borderRadius: 20 }} />
            </div>
          </div>
        </div>
      </div>

      {/* Approval sections skeleton */}
      {[1, 2].map((i) => (
        <div
          key={i}
          style={{
            background: "rgba(255,255,255,0.7)",
            backdropFilter: "blur(12px)",
            borderRadius: "16px",
            border: "1px solid rgba(244,87,187,0.1)",
            padding: "24px",
          }}
        >
          <div style={{ height: 22, width: "20%", background: "rgba(244,87,187,0.12)", borderRadius: 6, marginBottom: 20 }} />
          {[1, 2, 3].map((j) => (
            <div key={j} style={{ height: 16, background: "rgba(0,0,0,0.05)", borderRadius: 6, marginBottom: 12 }} />
          ))}
        </div>
      ))}
    </div>
  );
}
