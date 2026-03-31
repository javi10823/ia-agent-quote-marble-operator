import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/ui/Sidebar";

export const metadata: Metadata = {
  title: "D'Angelo — Presupuestos",
  description: "Agente Valentina · Sistema de presupuestos D'Angelo Marmolería",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
          <Sidebar />
          <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--bg)" }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
