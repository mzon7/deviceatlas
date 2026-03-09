import { Link } from "react-router-dom";

export default function PublicHeader() {
  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        background: "rgba(255,255,255,0.85)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(244,87,187,0.12)",
        boxShadow: "0 1px 12px rgba(244,87,187,0.06)",
      }}
    >
      <div
        style={{
          maxWidth: 1000,
          margin: "0 auto",
          padding: "0 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          height: 60,
        }}
      >
        {/* Logo */}
        <Link
          to="/"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            textDecoration: "none",
          }}
        >
          <img
            src="/logo.png"
            alt="Device Atlas"
            style={{
              width: 34,
              height: 34,
              borderRadius: 10,
              objectFit: "cover",
              boxShadow: "0 2px 8px rgba(244,87,187,0.35)",
            }}
          />
          <span
            style={{
              fontWeight: 800,
              fontSize: 17,
              background: "linear-gradient(135deg, #f457bb, #ea105c)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
              letterSpacing: "-0.02em",
            }}
          >
            Device Atlas
          </span>
        </Link>

        {/* Nav links */}
        <nav style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <NavLink to="/devices">Devices</NavLink>
          <NavLink to="/login">Sign in</NavLink>
        </nav>
      </div>
    </header>
  );
}

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      style={{
        padding: "6px 14px",
        borderRadius: 20,
        fontSize: 13,
        fontWeight: 500,
        color: "#555",
        textDecoration: "none",
        transition: "all 0.15s",
      }}
      onMouseEnter={(e) => {
        (e.target as HTMLElement).style.background = "rgba(244,87,187,0.08)";
        (e.target as HTMLElement).style.color = "#f457bb";
      }}
      onMouseLeave={(e) => {
        (e.target as HTMLElement).style.background = "transparent";
        (e.target as HTMLElement).style.color = "#555";
      }}
    >
      {children}
    </Link>
  );
}
