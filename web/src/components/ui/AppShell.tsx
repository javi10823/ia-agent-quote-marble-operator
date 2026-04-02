"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { useBreakpoints } from "@/lib/useMediaQuery";
import Sidebar from "./Sidebar";

const PUBLIC_PATHS = ["/login"];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { isMobile } = useBreakpoints();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const isPublic = PUBLIC_PATHS.some(p => pathname.startsWith(p));

  if (isPublic) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Mobile hamburger */}
      {isMobile && (
        <button
          onClick={() => setSidebarOpen(true)}
          aria-label="Abrir menú"
          style={{
            position: "fixed", top: 12, left: 12, zIndex: 30,
            width: 36, height: 36, borderRadius: 8,
            background: "var(--s2)", border: "1px solid var(--b1)",
            color: "var(--t2)", cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
      )}

      <Sidebar
        isMobile={isMobile}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <main className="flex-1 flex flex-col overflow-hidden bg-bg">
        {children}
      </main>
    </div>
  );
}
