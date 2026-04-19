"use client";

import { useRouter, usePathname } from "next/navigation";
import { logout } from "@/lib/auth";
import { useQuotes } from "@/lib/quotes-context";
import clsx from "clsx";

export default function Sidebar({ isOpen, onClose }: { isOpen?: boolean; onClose?: () => void }) {
  const router = useRouter();
  const path = usePathname();
  const { quotes } = useQuotes();

  function navigate(to: string) {
    onClose?.();
    router.push(to);
  }

  const unread = quotes.filter(q => !q.is_read).length;
  const sidebarContent = (
    <nav className="w-[200px] shrink-0 bg-bg flex flex-col px-4 pt-6 pb-6 h-full">
      {/* Logo — Fraunces italic, badge con acento suave */}
      <div onClick={() => navigate("/")} className="flex items-center gap-3 pb-8 cursor-pointer group">
        <div className="w-[34px] h-[34px] rounded-lg bg-gradient-to-br from-acc/90 to-acc-hover flex items-center justify-center text-[13px] font-semibold text-white -tracking-[0.5px] shadow-[0_4px_12px_var(--acc-shadow)]">D</div>
        <span className="font-serif italic text-[19px] font-medium -tracking-[0.01em] text-t1 leading-none">D&apos;Angelo</span>
      </div>

      {/* Nav items — sin labels de sección, tipografía editorial */}
      <NavItem icon={<InboxIcon />} label="Presupuestos" count={quotes.length} unreadCount={unread} active={path === "/"} onClick={() => navigate("/")} />
      <NavItem icon={<BookIcon />} label="Catálogo" active={path === "/config"} onClick={() => navigate("/config")} />
      <NavItem icon={<CogIcon />} label="Configuración" active={path === "/settings"} onClick={() => navigate("/settings")} />

      {/* Footer — sólo logout. El CTA "+Nuevo presupuesto" vive en el
          header del dashboard (arriba-derecha) según diseño v2. */}
      <div className="mt-auto">
        <button onClick={async () => { await logout(); router.push("/login"); }} className="w-full py-2 px-2 bg-transparent border-none rounded-md text-t3 text-[12px] font-normal font-sans cursor-pointer flex items-center gap-2 transition-colors duration-150 hover:text-t2">
          <LogoutIcon /> Cerrar sesión
        </button>
      </div>
    </nav>
  );

  return (
    <>
      {/* Desktop: static sidebar */}
      <div className="hidden md:flex h-screen">{sidebarContent}</div>

      {/* Mobile: drawer overlay */}
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

// Mobile top bar component
export function MobileTopBar({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <div className="md:hidden flex items-center gap-3 px-4 py-3 bg-bg border-b border-b1 shrink-0">
      <button onClick={onMenuClick} className="bg-transparent border-none text-t2 cursor-pointer p-1">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>
      <div className="w-[24px] h-[24px] rounded-md bg-gradient-to-br from-acc/90 to-acc-hover flex items-center justify-center text-[11px] font-semibold text-white">D</div>
      <span className="font-serif italic text-[15px] font-medium text-t1 leading-none">D&apos;Angelo</span>
    </div>
  );
}

function NavItem({ icon, label, count, unreadCount, active, onClick }: {
  icon: React.ReactNode; label: string; count?: number; unreadCount?: number; active: boolean; onClick: () => void;
}) {
  return (
    <button onClick={onClick} className={clsx(
      "flex items-center gap-3 px-3 py-[9px] rounded-md text-[13px] cursor-pointer border-none w-full text-left transition-colors duration-100 font-sans mb-0.5",
      active ? "text-t1 bg-white/[0.035]" : "text-t2 bg-transparent hover:bg-white/[0.025]",
    )}>
      <span className={clsx("shrink-0", active ? "text-acc" : "text-t3")}>{icon}</span>
      <span className={clsx("flex-1", active ? "font-medium" : "font-normal")}>{label}</span>
      {unreadCount ? (
        <span className="text-[10px] font-semibold px-[7px] py-px rounded-full bg-acc text-white font-mono">{unreadCount}</span>
      ) : count != null ? (
        <span className="text-[11px] text-t4 font-mono tabular-nums">{count}</span>
      ) : null}
    </button>
  );
}

// Iconos de trazo fino — estilo editorial, no "blocky".
function InboxIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3 14l2-8h14l2 8"/><path d="M3 14h6l1 2h4l1-2h6v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4z"/></svg>;
}
function BookIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2V5zM4 19a2 2 0 012-2h13"/></svg>;
}
function CogIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>;
}
function LogoutIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>;
}
