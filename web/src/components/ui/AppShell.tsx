"use client";

import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";

const PUBLIC_PATHS = ["/login"];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPublic = PUBLIC_PATHS.some(p => pathname.startsWith(p));

  if (isPublic) {
    return <>{children}</>;
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar />
      <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--bg)" }}>
        {children}
      </main>
    </div>
  );
}
