import { useState } from "react";
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

const CATEGORIES = ["All", "Cardiovascular", "Neurology", "Orthopedic", "Ophthalmology", "Gastroenterology", "General Surgery"];

export default function DevicesPage() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");

  const { data: devices, isLoading } = useQuery<Device[]>({
    queryKey: ["devices-list"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from(dbTable("devices"))
        .select("id, name, manufacturer, category, description, is_active")
        .eq("is_active", true)
        .order("name");
      if (error) throw error;
      return data ?? [];
    },
    staleTime: 5 * 60 * 1000,
  });

  const filtered = (devices ?? []).filter((d) => {
    const matchSearch =
      !search ||
      d.name.toLowerCase().includes(search.toLowerCase()) ||
      (d.manufacturer ?? "").toLowerCase().includes(search.toLowerCase());
    const matchCategory = category === "All" || d.category === category;
    return matchSearch && matchCategory;
  });

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
          maxWidth: 1000,
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
            Track regulatory approvals from the FDA and Health Canada for leading medical devices.
          </p>
        </div>

        {/* Search & filter */}
        <div
          style={{
            display: "flex",
            gap: 12,
            marginBottom: 28,
            flexWrap: "wrap",
          }}
        >
          <div style={{ position: "relative", flex: "1 1 240px", minWidth: 200 }}>
            <svg
              style={{
                position: "absolute",
                left: 12,
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
              placeholder="Search devices or manufacturers…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: "100%",
                padding: "10px 12px 10px 36px",
                borderRadius: 24,
                border: "1px solid rgba(244,87,187,0.2)",
                background: "rgba(255,255,255,0.85)",
                backdropFilter: "blur(8px)",
                fontSize: 13,
                color: "#111",
                outline: "none",
                boxSizing: "border-box",
                transition: "border-color 0.15s",
              }}
              onFocus={(e) => {
                e.target.style.borderColor = "#f457bb";
                e.target.style.boxShadow = "0 0 0 3px rgba(244,87,187,0.1)";
              }}
              onBlur={(e) => {
                e.target.style.borderColor = "rgba(244,87,187,0.2)";
                e.target.style.boxShadow = "none";
              }}
            />
          </div>

          {/* Category filter */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategory(cat)}
                style={{
                  padding: "8px 14px",
                  borderRadius: 20,
                  border: category === cat ? "1px solid #f457bb" : "1px solid rgba(0,0,0,0.1)",
                  background:
                    category === cat
                      ? "linear-gradient(135deg, #f457bb, #ea105c)"
                      : "rgba(255,255,255,0.8)",
                  color: category === cat ? "#fff" : "#555",
                  fontSize: 12,
                  fontWeight: category === cat ? 600 : 400,
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                {cat !== "All" && CATEGORY_ICONS[cat] ? `${CATEGORY_ICONS[cat]} ` : ""}
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Results count */}
        {!isLoading && (
          <div style={{ fontSize: 12, color: "#aaa", marginBottom: 16 }}>
            {filtered.length} device{filtered.length !== 1 ? "s" : ""} found
          </div>
        )}

        {/* Device grid */}
        {isLoading ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 16,
            }}
          >
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                style={{
                  height: 140,
                  borderRadius: 16,
                  background: "rgba(255,255,255,0.7)",
                  border: "1px solid rgba(244,87,187,0.1)",
                  animation: "pulse 1.5s ease-in-out infinite",
                }}
              />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              padding: "60px 24px",
              color: "#aaa",
            }}
          >
            <span style={{ fontSize: 40, display: "block", marginBottom: 12 }}>🔍</span>
            <p style={{ fontSize: 15 }}>No devices match your search.</p>
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 16,
            }}
          >
            {filtered.map((device) => (
              <DeviceCard key={device.id} device={device} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function DeviceCard({ device }: { device: Device }) {
  const icon = CATEGORY_ICONS[device.category ?? ""] ?? "🔬";

  return (
    <Link
      to={`/device/${device.id}`}
      style={{ textDecoration: "none" }}
    >
      <div
        style={{
          background: "rgba(255,255,255,0.75)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          borderRadius: 16,
          border: "1px solid rgba(244,87,187,0.12)",
          padding: "20px",
          cursor: "pointer",
          transition: "all 0.2s",
          height: "100%",
          boxSizing: "border-box",
          boxShadow: "0 2px 12px rgba(0,0,0,0.03)",
        }}
        onMouseEnter={(e) => {
          const el = e.currentTarget as HTMLElement;
          el.style.transform = "translateY(-2px)";
          el.style.boxShadow = "0 8px 32px rgba(244,87,187,0.14)";
          el.style.borderColor = "rgba(244,87,187,0.3)";
        }}
        onMouseLeave={(e) => {
          const el = e.currentTarget as HTMLElement;
          el.style.transform = "translateY(0)";
          el.style.boxShadow = "0 2px 12px rgba(0,0,0,0.03)";
          el.style.borderColor = "rgba(244,87,187,0.12)";
        }}
      >
        {/* Header row */}
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 10 }}>
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: 10,
              background: "linear-gradient(135deg, rgba(244,87,187,0.12), rgba(234,16,92,0.08))",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 20,
              flexShrink: 0,
            }}
          >
            {icon}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontWeight: 600,
                fontSize: 14,
                color: "#111",
                lineHeight: 1.3,
                marginBottom: 2,
              }}
            >
              {device.name}
            </div>
            {device.manufacturer && (
              <div style={{ fontSize: 11, color: "#999" }}>{device.manufacturer}</div>
            )}
          </div>
        </div>

        {/* Description */}
        {device.description && (
          <p
            style={{
              fontSize: 12,
              color: "#666",
              lineHeight: 1.5,
              margin: "0 0 12px",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {device.description}
          </p>
        )}

        {/* Category tag */}
        {device.category && (
          <span
            style={{
              display: "inline-block",
              padding: "3px 10px",
              borderRadius: 12,
              background: "rgba(244,87,187,0.08)",
              color: "#f457bb",
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            {device.category}
          </span>
        )}

        {/* Arrow */}
        <div
          style={{
            marginTop: 12,
            display: "flex",
            justifyContent: "flex-end",
          }}
        >
          <span style={{ fontSize: 12, color: "#f457bb", fontWeight: 500 }}>
            View approvals →
          </span>
        </div>
      </div>
    </Link>
  );
}
