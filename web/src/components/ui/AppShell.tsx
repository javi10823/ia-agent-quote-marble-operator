"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import Sidebar, { MobileTopBar } from "./Sidebar";
import GlobalDebugBanner from "./GlobalDebugBanner";
import { QuotesProvider } from "@/lib/quotes-context";
import { ToastProvider } from "@/lib/toast-context";

const PUBLIC_PATHS = ["/login"];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPublic = PUBLIC_PATHS.some(p => pathname.startsWith(p));
  const [drawerOpen, setDrawerOpen] = useState(false);

  if (isPublic) {
    return <>{children}</>;
  }

  return (
    <ToastProvider>
      <QuotesProvider>
        <div className="flex flex-col h-screen overflow-hidden">
          {/* Banner global del modo debug — sticky top, full-width.
              Solo se renderiza si el modo está activo (status.enabled). */}
          <GlobalDebugBanner />
          <div className="flex flex-1 overflow-hidden">
            <Sidebar isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} />
            <div className="flex-1 flex flex-col overflow-hidden bg-bg min-w-0">
              <MobileTopBar onMenuClick={() => setDrawerOpen(true)} />
              <main className="flex-1 flex flex-col overflow-hidden">
                {children}
              </main>
            </div>
          </div>
        </div>
      </QuotesProvider>
    </ToastProvider>
  );
}
