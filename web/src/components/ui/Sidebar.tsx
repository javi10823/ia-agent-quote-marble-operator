"use client";

import { useState, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { logout } from "@/lib/auth";
import { useQuotes } from "@/lib/quotes-context";
import clsx from "clsx";

export default function Sidebar({ isOpen, onClose }: { isOpen?: boolean; onClose?: () => void }) {
  const router = useRouter();
  const path = usePathname();
  const { quotes, addQuote } = useQuotes();

  async function handleNew() {
    try {
      const id = await addQuote();
      onClose?.();
      router.push(`/quote/${id}`);
    } catch { /* toast already shown by context */ }
  }

  function navigate(to: string) {
    onClose?.();
    router.push(to);
  }

  const sidebarContent = (
    <nav className="w-[212px] shrink-0 bg-s1 border-r border-b1 flex flex-col px-2.5 pt-[18px] pb-5 h-full">
      {/* Logo */}
      <div onClick={() => navigate("/")} className="flex items-center gap-2.5 px-2 pt-0.5 pb-5 cursor-pointer">
        <div className="w-[26px] h-[26px] rounded-md bg-acc flex items-center justify-center text-xs font-semibold text-white -tracking-[0.5px]">D</div>
        <span className="text-[13px] font-medium -tracking-[0.02em] text-t1">D&apos;Angelo</span>
      </div>

      {/* Nav */}
      <span className="text-[10px] font-medium text-t4 uppercase tracking-[0.10em] px-2 pb-1">Principal</span>
      <NavItem icon={<GridIcon />} label="Presupuestos" badge={String(quotes.length)} unreadCount={quotes.filter(q => !q.is_read).length} active={path === "/"} onClick={() => navigate("/")} />

      <span className="text-[10px] font-medium text-t4 uppercase tracking-[0.10em] px-2 pb-1 mt-3.5">Sistema</span>
      <NavItem icon={<GearIcon />} label="Catálogo" active={path === "/config"} onClick={() => navigate("/config")} />
      <NavItem icon={<SettingsIcon />} label="Configuración" active={path === "/settings"} onClick={() => navigate("/settings")} />

      <div className="h-px bg-b1 my-3" />

      <div className="mt-auto">
        <button onClick={handleNew} className="w-full py-2.5 px-3 bg-acc border-none rounded-lg text-white text-[13px] font-medium font-sans cursor-pointer flex items-center justify-center gap-[7px] -tracking-[0.01em] transition-all duration-150 hover:bg-[#3a7aff] hover:-translate-y-px hover:shadow-[0_8px_24px_rgba(79,143,255,.30)]">
          <PlusIcon /> Nuevo presupuesto
        </button>
        <button onClick={async () => { await logout(); router.push("/login"); }} className="w-full py-[7px] px-2 bg-transparent border-none rounded-md text-t3 text-[11px] font-normal font-sans cursor-pointer flex items-center justify-center gap-1.5 transition-colors duration-150 hover:text-t2 mt-2.5">
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
    <div className="md:hidden flex items-center gap-3 px-4 py-3 bg-s1 border-b border-b1 shrink-0">
      <button onClick={onMenuClick} className="bg-transparent border-none text-t2 cursor-pointer p-1">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>
      <div className="w-[22px] h-[22px] rounded-md bg-acc flex items-center justify-center text-[10px] font-semibold text-white">D</div>
      <span className="text-[13px] font-medium text-t1">D&apos;Angelo</span>
    </div>
  );
}

function NavItem({ icon, label, badge, unreadCount, active, onClick }: {
  icon: React.ReactNode; label: string; badge?: string; unreadCount?: number; active: boolean; onClick: () => void;
}) {
  return (
    <button onClick={onClick} className={clsx(
      "flex items-center gap-2 p-2 rounded-md text-xs font-normal cursor-pointer border-none w-full text-left transition-all duration-100 font-sans",
      active ? "text-acc bg-acc/[0.11]" : "text-t2 bg-transparent hover:bg-white/[0.04]",
    )}>
      <span className={clsx("shrink-0", active ? "opacity-100" : "opacity-65")}>{icon}</span>
      {label}
      {unreadCount ? (
        <span className="ml-auto text-[10px] font-semibold px-[7px] py-px rounded-full bg-acc text-white font-mono">{unreadCount}</span>
      ) : badge ? (
        <span className="ml-auto text-[10px] font-medium px-[7px] py-px rounded-full bg-white/[0.07] text-t3 font-mono">{badge}</span>
      ) : null}
    </button>
  );
}

function GridIcon() {
  return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>;
}
function GearIcon() {
  return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z"/><circle cx="12" cy="12" r="3"/></svg>;
}
function PlusIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>;
}
function SettingsIcon() {
  return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>;
}
function LogoutIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>;
}
