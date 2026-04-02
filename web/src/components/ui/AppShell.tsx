"use client";

import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import { QuotesProvider } from "@/lib/quotes-context";

const PUBLIC_PATHS = ["/login"];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPublic = PUBLIC_PATHS.some(p => pathname.startsWith(p));

  if (isPublic) {
    return <>{children}</>;
  }

  return (
    <QuotesProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-hidden bg-bg">
          {children}
        </main>
      </div>
    </QuotesProvider>
  );
}
