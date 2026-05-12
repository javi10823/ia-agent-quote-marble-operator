/**
 * Root layout · Sprint 2.5 switch-to-main.
 *
 * Promovido desde `app/v2/layout.tsx`. Ahora es el único root del proyecto
 * (el legacy AppShell fue eliminado en este sprint).
 *
 * Responsabilidades:
 *   1. <html> + <body> con las 3 CSS vars de next/font/google aplicadas
 *      (Fraunces serif italic + Inter Tight sans + JetBrains Mono).
 *   2. Importa `globals.css` con los tokens del design system.
 *   3. Importa `operator-shared.css` literal (~4710 líneas, copia sin
 *      tocar del handoff — Sprint 1.5 audit-cerrado).
 *
 * Orden crítico de imports CSS: operator-shared.css PRIMERO, globals.css
 * DESPUÉS. operator-shared.css declara su propio :root con string literals
 * para --serif/--sans/--mono; globals.css los re-define apuntando a
 * `var(--font-*)` de next/font. El orden actual hace que el bridge gane
 * el cascade (fix del PR #456).
 *
 * Cleanup a Tailwind utilities diferido a Sprint 5 (ver
 * docs/tech-debt/css-migration.md).
 */
import type { Metadata } from "next";
import { Fraunces, Inter_Tight, JetBrains_Mono } from "next/font/google";
import "./operator-shared.css";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});

const interTight = Inter_Tight({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "D'Angelo — Presupuestos",
  description: "Agente Valentina · Sistema de presupuestos D'Angelo Marmolería",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="es"
      className={`${fraunces.variable} ${interTight.variable} ${jetbrainsMono.variable}`}
    >
      <body className="bg-bg text-ink">{children}</body>
    </html>
  );
}
