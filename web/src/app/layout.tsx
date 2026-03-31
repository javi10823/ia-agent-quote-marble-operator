import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "D'Angelo — Presupuestos",
  description: "Agente Valentina · Sistema de presupuestos D'Angelo Marmolería",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
