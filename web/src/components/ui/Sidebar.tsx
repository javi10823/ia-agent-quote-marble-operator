"use client";

import { useRouter, usePathname } from "next/navigation";

export default function Sidebar() {
  const router = useRouter();
  const path = usePathname();

  async function handleNew() {
    const res = await fetch("/api/quotes", { method: "POST" });
    const { id } = await res.json();
    router.push(`/quote/${id}`);
  }

  return (
    <nav style={{
      width: 212,
      flexShrink: 0,
      background: "var(--s1)",
      borderRight: "1px solid var(--b1)",
      display: "flex",
      flexDirection: "column",
      padding: "18px 10px 20px",
      height: "100vh",
    }}>
      {/* Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "2px 8px 22px" }}>
        <div style={{
          width: 26, height: 26, borderRadius: 6,
          background: "var(--acc)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 12, fontWeight: 600, color: "#fff", letterSpacing: -0.5,
        }}>D</div>
        <span style={{ fontSize: 13, fontWeight: 500, letterSpacing: "-0.02em", color: "var(--t1)" }}>
          D'Angelo
        </span>
      </div>

      {/* Nav */}
      <span style={sectionStyle}>Principal</span>
      <NavItem
        icon={<GridIcon />}
        label="Presupuestos"
        badge="34"
        active={path === "/"}
        onClick={() => router.push("/")}
      />

      <span style={{ ...sectionStyle, marginTop: 14 }}>Sistema</span>
      <NavItem
        icon={<GearIcon />}
        label="Catálogo"
        active={path === "/config"}
        onClick={() => router.push("/config")}
      />

      {/* Separator */}
      <div style={{ height: 1, background: "var(--b1)", margin: "12px 0" }} />

      {/* CTA */}
      <div style={{ marginTop: "auto" }}>
        <button onClick={handleNew} style={{
          width: "100%", padding: "10px 12px",
          background: "var(--acc)", border: "none", borderRadius: 8,
          color: "#fff", fontSize: 13, fontWeight: 500,
          fontFamily: "inherit", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
          transition: "all 0.15s",
          letterSpacing: "-0.01em",
        }}
          onMouseEnter={e => {
            (e.target as HTMLButtonElement).style.background = "#3a7aff";
            (e.target as HTMLButtonElement).style.transform = "translateY(-1px)";
            (e.target as HTMLButtonElement).style.boxShadow = "0 8px 24px rgba(79,143,255,.30)";
          }}
          onMouseLeave={e => {
            (e.target as HTMLButtonElement).style.background = "var(--acc)";
            (e.target as HTMLButtonElement).style.transform = "";
            (e.target as HTMLButtonElement).style.boxShadow = "";
          }}
        >
          <PlusIcon /> Nuevo presupuesto
        </button>
      </div>
    </nav>
  );
}

function NavItem({ icon, label, badge, active, onClick }: {
  icon: React.ReactNode;
  label: string;
  badge?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: 8, borderRadius: 6,
      fontSize: 12, fontWeight: 400,
      color: active ? "var(--acc)" : "var(--t2)",
      cursor: "pointer", border: "none",
      background: active ? "rgba(79,143,255,.11)" : "transparent",
      width: "100%", textAlign: "left",
      transition: "all .1s", fontFamily: "inherit",
    }}>
      <span style={{ opacity: active ? 1 : 0.65, flexShrink: 0 }}>{icon}</span>
      {label}
      {badge && (
        <span style={{
          marginLeft: "auto", fontSize: 10, fontWeight: 500,
          padding: "1px 7px", borderRadius: 999,
          background: "rgba(255,255,255,.07)", color: "var(--t3)",
          fontFamily: "'Geist Mono', monospace",
        }}>{badge}</span>
      )}
    </button>
  );
}

const sectionStyle: React.CSSProperties = {
  fontSize: 10, fontWeight: 500, color: "var(--t4)",
  textTransform: "uppercase", letterSpacing: "0.10em",
  padding: "0 8px 5px",
};

function GridIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
      <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  );
}
