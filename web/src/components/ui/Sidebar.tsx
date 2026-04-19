"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { logout, getCurrentUsername, prettyFirstName } from "@/lib/auth";
import { useQuotes } from "@/lib/quotes-context";
import clsx from "clsx";

// Sidebar exacto según `dash-airy.jsx → AirySidebar`. Ancho 180px, border-right
// sutil. Header logo con BrandMark 28 + "D'Angelo" Fraunces italic 15. Nav
// items: padding 10px 10px, radius 6, mb 2. Activo tiene barra accent a la
// IZQUIERDA (absolute left -10, w 2). Footer con avatar J 28x28 round + nombre
// + "Cerrar sesión" en texto chico.
export default function Sidebar({ isOpen, onClose }: { isOpen?: boolean; onClose?: () => void }) {
  const router = useRouter();
  const path = usePathname();
  const { quotes } = useQuotes();

  function navigate(to: string) {
    onClose?.();
    router.push(to);
  }

  // getCurrentUsername() lee localStorage — NO se puede llamar en render
  // porque el SSR no tiene window → hidratación mismatch (React error #418/#425).
  // Lo leemos después del mount. Fallback "Operador" mientras tanto.
  const [name, setName] = useState("Operador");
  useEffect(() => {
    const n = prettyFirstName(getCurrentUsername());
    if (n) setName(n);
  }, []);

  const sidebarContent = (
    <nav
      className="w-[180px] shrink-0 bg-bg flex flex-col h-full"
      style={{ borderRight: "1px solid var(--b1)" }}
    >
      {/* Logo section — padding 22px 18px 14px + border-bottom */}
      <div
        onClick={() => navigate("/")}
        className="flex items-center gap-2.5 cursor-pointer"
        style={{ padding: "22px 18px 14px", borderBottom: "1px solid var(--b1)" }}
      >
        <BrandMark size={28} />
        <span
          className="font-serif italic text-t1"
          style={{ fontSize: 15, fontWeight: 500, letterSpacing: "-0.2px", lineHeight: 1 }}
        >
          D&apos;Angelo
        </span>
      </div>

      {/* Nav — padding 12px 10px */}
      <div className="flex-1" style={{ padding: "12px 10px" }}>
        <NavRow icon={<InboxIcon />} label="Presupuestos" count={quotes.length} active={path === "/"} onClick={() => navigate("/")} />
        <NavRow icon={<BookIcon />} label="Catálogo" active={path === "/config"} onClick={() => navigate("/config")} />
        <NavRow icon={<CogIcon />} label="Configuración" active={path === "/settings"} onClick={() => navigate("/settings")} />
      </div>

      {/* Footer — avatar + nombre + cerrar sesión */}
      <div
        className="flex items-center gap-2"
        style={{ padding: "12px 14px 18px", borderTop: "1px solid var(--b1)" }}
      >
        <div
          className="shrink-0 grid place-items-center font-serif text-t1"
          style={{
            width: 28, height: 28, borderRadius: 999,
            background: "var(--s3)",
            fontSize: 12, fontWeight: 600,
          }}
        >
          {name.charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-t1 truncate" style={{ fontSize: 12 }}>{name}</div>
          <button
            onClick={async () => { await logout(); router.push("/login"); }}
            className="text-t3 cursor-pointer bg-transparent border-none p-0 hover:text-t2"
            style={{ fontSize: 10.5 }}
          >
            Cerrar sesión
          </button>
        </div>
      </div>
    </nav>
  );

  return (
    <>
      <div className="hidden md:flex h-screen">{sidebarContent}</div>
      {isOpen && (
        <div className="md:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
          <div className="absolute left-0 top-0 h-full animate-[slideIn_0.2s_ease]">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
}

export function MobileTopBar({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <div className="md:hidden flex items-center gap-3 px-4 py-3 bg-bg border-b border-b1 shrink-0">
      <button onClick={onMenuClick} className="bg-transparent border-none text-t2 cursor-pointer p-1">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>
      <BrandMark size={22} />
      <span className="font-serif italic text-[15px] font-medium text-t1 leading-none">D&apos;Angelo</span>
    </div>
  );
}

// ── Nav item ───────────────────────────────────────────────────────────────
function NavRow({ icon, label, count, active, onClick }: {
  icon: React.ReactNode; label: string; count?: number; active: boolean; onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        "flex items-center cursor-pointer relative",
        active ? "text-t1" : "text-t2",
      )}
      style={{
        gap: 12,
        padding: "10px 10px",
        borderRadius: 6,
        marginBottom: 2,
        background: "transparent",
      }}
    >
      {/* Accent bar a la IZQUIERDA del item activo, fuera del padding interno */}
      {active && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: -10, top: 8, bottom: 8, width: 2,
            background: "var(--acc)",
            borderRadius: 2,
          }}
        />
      )}
      <span
        className="inline-flex"
        style={{ color: active ? "var(--acc)" : "var(--t3)" }}
      >
        {icon}
      </span>
      <span style={{ flex: 1, fontSize: 13, fontWeight: active ? 500 : 400 }}>
        {label}
      </span>
      {count != null && (
        <span
          className="font-mono"
          style={{ fontSize: 11, color: "var(--t3)", fontVariantNumeric: "tabular-nums" }}
        >
          {count}
        </span>
      )}
    </div>
  );
}

// ── BrandMark — esfera gradient con "D", matches design badge ──────────────
function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <div
      className="shrink-0 grid place-items-center text-white font-semibold"
      style={{
        width: size, height: size, borderRadius: 8,
        background: "linear-gradient(135deg, var(--acc) 0%, var(--acc-hover) 100%)",
        fontSize: size > 26 ? 12 : 10,
        letterSpacing: "-0.5px",
        boxShadow: "0 4px 12px var(--acc-shadow)",
      }}
    >
      D
    </div>
  );
}

// ── Icons con trazo 1.4 editorial ──────────────────────────────────────────
function InboxIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3 14l2-8h14l2 8"/><path d="M3 14h6l1 2h4l1-2h6v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4z"/></svg>;
}
function BookIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2V5zM4 19a2 2 0 012-2h13"/></svg>;
}
function CogIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>;
}
