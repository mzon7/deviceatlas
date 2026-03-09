import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { supabase, dbTable } from "../lib/supabase";
import PublicHeader from "../features/shared/components/PublicHeader";

interface Device {
  id: string;
  name: string;
  manufacturer: string | null;
  category: string | null;
  description: string | null;
  is_active: boolean;
  cleared_date: string | null;
  clearance_type: string | null;
}

const PAGE_SIZE = 24;

const CATEGORY_ICONS: Record<string, string> = {
  Cardiovascular: "🫀",
  Neurology: "🧠",
  Orthopedic: "🦴",
  Ophthalmology: "👁️",
  Gastroenterology: "🫁",
  Endocrinology: "⚗️",
  "General Surgery": "🏥",
  "Radiology/Imaging": "🔬",
  Dental: "🦷",
  "Obstetrics/Gynecology": "👶",
  Anesthesiology: "💉",
  Immunology: "🛡️",
  Hematology: "🩸",
  ENT: "👂",
  Diagnostics: "🧪",
  Dermatology: "🩹",
  Urology: "💊",
  Pulmonology: "🫁",
  "Physical Medicine": "🏃",
};

const CATEGORIES = [
  "All",
  "Cardiovascular",
  "Neurology",
  "Ophthalmology",
  "Radiology/Imaging",
  "Dental",
  "Gastroenterology",
  "Diagnostics",
  "Obstetrics/Gynecology",
  "General Surgery",
  "ENT",
  "Immunology",
  "Hematology",
  "Endocrinology",
  "Anesthesiology",
  "Orthopedic",
  "Physical Medicine",
  "Urology",
  "Dermatology",
  "Pulmonology",
];

type ApprovalFilter = "All" | "PMA Approved" | "FDA Cleared" | "Pending";

const APPROVAL_FILTERS: ApprovalFilter[] = ["All", "PMA Approved", "FDA Cleared", "Pending"];

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export default function DevicesPage() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [approvalFilter, setApprovalFilter] = useState<ApprovalFilter>("All");
  const [page, setPage] = useState(0);

  const debouncedSearch = useDebounce(search, 300);

  // Reset page on filter change
  useEffect(() => { setPage(0); }, [debouncedSearch, category, approvalFilter]);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["devices-list", debouncedSearch, category, approvalFilter, page],
    queryFn: async () => {
      let q = supabase
        .from(dbTable("devices"))
        .select("id, name, manufacturer, category, description, is_active, cleared_date, clearance_type", { count: "exact" })
        .eq("is_active", true)
        .order("name")
        .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1);

      if (debouncedSearch.trim()) {
        q = q.ilike("name", `%${debouncedSearch.trim()}%`);
      }
      if (category !== "All") {
        q = q.eq("category", category);
      }
      if (approvalFilter === "PMA Approved") {
        q = q.eq("clearance_type", "PMA").not("cleared_date", "is", null);
      } else if (approvalFilter === "FDA Cleared") {
        q = q.not("clearance_type", "eq", "PMA").not("cleared_date", "is", null);
      } else if (approvalFilter === "Pending") {
        q = q.is("cleared_date", null);
      }

      const { data, error, count } = await q;
      if (error) throw error;
      return { devices: data ?? [], total: count ?? 0 };
    },
    staleTime: 2 * 60 * 1000,
    placeholderData: (prev) => prev,
  });

  const devices = data?.devices ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const handlePrev = useCallback(() => setPage((p) => Math.max(0, p - 1)), []);
  const handleNext = useCallback(() => setPage((p) => Math.min(totalPages - 1, p + 1)), [totalPages]);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg, #fff0f8 0%, #fff5fb 40%, #fff8fc 100%)",
        position: "relative",
      }}
    >
      <div
        style={{
          position: "fixed",
          top: "5%",
          right: "10%",
          width: 360,
          height: 360,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(244,87,187,0.07) 0%, transparent 70%)",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />

      <PublicHeader />

      <main
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: 1100,
          margin: "0 auto",
          padding: "32px 16px 64px",
        }}
      >
        {/* Hero */}
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <h1
            style={{
              fontSize: 36,
              fontWeight: 800,
              margin: "0 0 12px",
              background: "linear-gradient(135deg, #f457bb 0%, #ea105c 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
              letterSpacing: "-0.02em",
            }}
          >
            Medical Device Database
          </h1>
          <p style={{ fontSize: 15, color: "#777", maxWidth: 520, margin: "0 auto" }}>
            Track regulatory approvals from the FDA and Health Canada across{" "}
            <span style={{ color: "#f457bb", fontWeight: 600 }}>160,000+ medical devices</span>.
          </p>
        </div>

        {/* Search + filters */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 24 }}>
          {/* Search bar */}
          <div style={{ position: "relative" }}>
            <svg
              style={{
                position: "absolute",
                left: 14,
                top: "50%",
                transform: "translateY(-50%)",
                color: "#bbb",
                pointerEvents: "none",
              }}
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              placeholder="Search 160,000+ devices by name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: "100%",
                padding: "12px 16px 12px 40px",
                borderRadius: 28,
                border: "1px solid rgba(244,87,187,0.2)",
                background: "rgba(255,255,255,0.9)",
                backdropFilter: "blur(8px)",
                fontSize: 14,
                color: "#111",
                outline: "none",
                boxSizing: "border-box",
                boxShadow: "0 2px 16px rgba(244,87,187,0.06)",
              }}
              onFocus={(e) => {
                e.target.style.borderColor = "#f457bb";
                e.target.style.boxShadow = "0 0 0 3px rgba(244,87,187,0.12)";
              }}
              onBlur={(e) => {
                e.target.style.borderColor = "rgba(244,87,187,0.2)";
                e.target.style.boxShadow = "0 2px 16px rgba(244,87,187,0.06)";
              }}
            />
          </div>

          {/* Approval status filter */}
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span style={{ fontSize: 11, color: "#aaa", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", flexShrink: 0 }}>
              Status
            </span>
            {APPROVAL_FILTERS.map((af) => {
              const active = approvalFilter === af;
              const { color, bg, label } = getApprovalStyle(af);
              return (
                <button
                  key={af}
                  onClick={() => setApprovalFilter(af)}
                  style={{
                    padding: "6px 13px",
                    borderRadius: 20,
                    border: active ? `1px solid ${color}` : "1px solid rgba(0,0,0,0.09)",
                    background: active ? bg : "rgba(255,255,255,0.85)",
                    color: active ? color : "#555",
                    fontSize: 12,
                    fontWeight: active ? 700 : 400,
                    cursor: "pointer",
                    transition: "all 0.15s",
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                  }}
                >
                  {af !== "All" && <ApprovalDot type={af} size={7} />}
                  {label}
                </button>
              );
            })}
          </div>

          {/* Category pills */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {CATEGORIES.map((cat) => {
              const active = category === cat;
              return (
                <button
                  key={cat}
                  onClick={() => setCategory(cat)}
                  style={{
                    padding: "7px 14px",
                    borderRadius: 20,
                    border: active ? "1px solid #f457bb" : "1px solid rgba(0,0,0,0.09)",
                    background: active
                      ? "linear-gradient(135deg, #f457bb, #ea105c)"
                      : "rgba(255,255,255,0.85)",
                    color: active ? "#fff" : "#555",
                    fontSize: 12,
                    fontWeight: active ? 600 : 400,
                    cursor: "pointer",
                    transition: "all 0.15s",
                    whiteSpace: "nowrap",
                  }}
                >
                  {cat !== "All" && CATEGORY_ICONS[cat] ? `${CATEGORY_ICONS[cat]} ` : ""}
                  {cat}
                </button>
              );
            })}
          </div>
        </div>

        {/* Results meta row */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
            minHeight: 24,
          }}
        >
          <div style={{ fontSize: 12, color: "#aaa" }}>
            {isLoading ? (
              "Loading…"
            ) : (
              <>
                <span style={{ color: "#f457bb", fontWeight: 600 }}>
                  {total.toLocaleString()}
                </span>{" "}
                device{total !== 1 ? "s" : ""}
                {debouncedSearch || category !== "All" || approvalFilter !== "All" ? " found" : " total"}
                {totalPages > 1 && (
                  <span style={{ color: "#ccc" }}>
                    {" "}· page {page + 1} of {totalPages}
                  </span>
                )}
              </>
            )}
          </div>
          {isFetching && !isLoading && (
            <div style={{ fontSize: 11, color: "#bbb" }}>Updating…</div>
          )}
        </div>

        {/* Grid */}
        {isLoading ? (
          <SkeletonGrid />
        ) : devices.length === 0 ? (
          <EmptyState />
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: 14,
            }}
          >
            {devices.map((device) => (
              <DeviceCard key={device.id} device={device} />
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              gap: 12,
              marginTop: 40,
            }}
          >
            <PagButton onClick={handlePrev} disabled={page === 0}>
              ← Previous
            </PagButton>

            <div style={{ display: "flex", gap: 4 }}>
              {pageRange(page, totalPages).map((p) =>
                p === "…" ? (
                  <span key={p + Math.random()} style={{ padding: "6px 4px", color: "#ccc", fontSize: 13 }}>…</span>
                ) : (
                  <button
                    key={p}
                    onClick={() => setPage(p as number)}
                    style={{
                      width: 34,
                      height: 34,
                      borderRadius: 8,
                      border: p === page ? "none" : "1px solid rgba(0,0,0,0.09)",
                      background:
                        p === page
                          ? "linear-gradient(135deg, #f457bb, #ea105c)"
                          : "rgba(255,255,255,0.8)",
                      color: p === page ? "#fff" : "#555",
                      fontSize: 13,
                      fontWeight: p === page ? 700 : 400,
                      cursor: "pointer",
                    }}
                  >
                    {(p as number) + 1}
                  </button>
                )
              )}
            </div>

            <PagButton onClick={handleNext} disabled={page >= totalPages - 1}>
              Next →
            </PagButton>
          </div>
        )}
      </main>
    </div>
  );
}

// ─── Approval helpers ──────────────────────────────────────────────────────────

function getApprovalStatus(device: Device): ApprovalFilter {
  if (!device.cleared_date) return "Pending";
  if (device.clearance_type === "PMA") return "PMA Approved";
  return "FDA Cleared";
}

function getApprovalStyle(type: ApprovalFilter | "Pending") {
  switch (type) {
    case "PMA Approved":
      return { color: "#059669", bg: "rgba(5,150,105,0.08)", label: "PMA Approved" };
    case "FDA Cleared":
      return { color: "#2563eb", bg: "rgba(37,99,235,0.08)", label: "FDA Cleared" };
    case "Pending":
      return { color: "#d97706", bg: "rgba(217,119,6,0.08)", label: "Pending" };
    default:
      return { color: "#555", bg: "transparent", label: "All" };
  }
}

function ApprovalDot({ type, size = 8 }: { type: ApprovalFilter; size?: number }) {
  const { color } = getApprovalStyle(type);
  return (
    <span
      style={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
      }}
    />
  );
}

function ApprovalStamp({ device }: { device: Device }) {
  const status = getApprovalStatus(device);
  const { color, bg, label } = getApprovalStyle(status);
  const year = device.cleared_date ? new Date(device.cleared_date).getFullYear() : null;

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "3px 8px",
        borderRadius: 10,
        background: bg,
        border: `1px solid ${color}22`,
      }}
    >
      <ApprovalDot type={status} size={6} />
      <span style={{ fontSize: 10, fontWeight: 700, color, letterSpacing: "0.02em" }}>
        {label}{year ? ` · ${year}` : ""}
      </span>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function DeviceCard({ device }: { device: Device }) {
  const icon = CATEGORY_ICONS[device.category ?? ""] ?? "🔬";
  const hasRealDesc =
    device.description &&
    !device.description.includes("FDA-cleared Class II") &&
    device.description.length > 40;

  return (
    <Link to={`/device/${device.id}`} style={{ textDecoration: "none" }}>
      <div
        style={{
          background: "rgba(255,255,255,0.78)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          borderRadius: 16,
          border: "1px solid rgba(244,87,187,0.12)",
          padding: "18px",
          cursor: "pointer",
          transition: "all 0.2s",
          boxSizing: "border-box",
          boxShadow: "0 2px 10px rgba(0,0,0,0.03)",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          minHeight: 140,
        }}
        onMouseEnter={(e) => {
          const el = e.currentTarget as HTMLElement;
          el.style.transform = "translateY(-2px)";
          el.style.boxShadow = "0 8px 28px rgba(244,87,187,0.13)";
          el.style.borderColor = "rgba(244,87,187,0.28)";
        }}
        onMouseLeave={(e) => {
          const el = e.currentTarget as HTMLElement;
          el.style.transform = "translateY(0)";
          el.style.boxShadow = "0 2px 10px rgba(0,0,0,0.03)";
          el.style.borderColor = "rgba(244,87,187,0.12)";
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              background: "linear-gradient(135deg, rgba(244,87,187,0.1), rgba(234,16,92,0.07))",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 18,
              flexShrink: 0,
            }}
          >
            {icon}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontWeight: 600,
                fontSize: 13,
                color: "#111",
                lineHeight: 1.35,
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {device.name}
            </div>
            {device.manufacturer && (
              <div
                style={{
                  fontSize: 11,
                  color: "#999",
                  marginTop: 2,
                  overflow: "hidden",
                  whiteSpace: "nowrap",
                  textOverflow: "ellipsis",
                }}
              >
                {device.manufacturer}
              </div>
            )}
          </div>
        </div>

        {hasRealDesc && (
          <p
            style={{
              fontSize: 11.5,
              color: "#666",
              lineHeight: 1.5,
              margin: 0,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {device.description}
          </p>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "auto", gap: 6, flexWrap: "wrap" }}>
          <ApprovalStamp device={device} />
          {device.category && (
            <span
              style={{
                padding: "2px 8px",
                borderRadius: 10,
                background: "rgba(244,87,187,0.07)",
                color: "#f457bb",
                fontSize: 10,
                fontWeight: 600,
              }}
            >
              {device.category}
            </span>
          )}
          <span style={{ fontSize: 11, color: "#f457bb", fontWeight: 500, marginLeft: "auto" }}>
            View →
          </span>
        </div>
      </div>
    </Link>
  );
}

function SkeletonGrid() {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
        gap: 14,
      }}
    >
      {Array.from({ length: 12 }).map((_, i) => (
        <div
          key={i}
          style={{
            height: 140,
            borderRadius: 16,
            background: "rgba(255,255,255,0.7)",
            border: "1px solid rgba(244,87,187,0.08)",
            animation: "pulse 1.5s ease-in-out infinite",
          }}
        />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div style={{ textAlign: "center", padding: "60px 24px", color: "#aaa" }}>
      <span style={{ fontSize: 40, display: "block", marginBottom: 12 }}>🔍</span>
      <p style={{ fontSize: 15 }}>No devices match your search.</p>
    </div>
  );
}

function PagButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "8px 18px",
        borderRadius: 20,
        border: "1px solid rgba(244,87,187,0.2)",
        background: disabled ? "rgba(255,255,255,0.5)" : "rgba(255,255,255,0.9)",
        color: disabled ? "#ccc" : "#f457bb",
        fontSize: 13,
        fontWeight: 500,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "all 0.15s",
      }}
    >
      {children}
    </button>
  );
}

/** Generate a compact page range like [0,1,2,'…',46] */
function pageRange(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i);
  const pages: (number | "…")[] = [];
  const add = (n: number) => { if (!pages.includes(n)) pages.push(n); };
  add(0);
  if (current > 2) pages.push("…");
  for (let i = Math.max(1, current - 1); i <= Math.min(total - 2, current + 1); i++) add(i);
  if (current < total - 3) pages.push("…");
  add(total - 1);
  return pages;
}
