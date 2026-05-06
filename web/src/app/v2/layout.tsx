/**
 * Layout root del v2 — Sprint 2 design system aplicado.
 *
 * Path coexistence (Master §21.7 decisión c1): /v2/* convive con el
 * frontend legacy bajo el mismo Next.js. El root <html>/<body> vive
 * en `src/app/layout.tsx` (legacy). Acá:
 *
 * 1. Cargamos las 3 fonts del handoff via `next/font/google`
 *    (Fraunces serif italic + Inter Tight sans + JetBrains Mono).
 *    Se exponen como CSS vars `--font-serif/sans/mono` aplicadas al
 *    div root del v2.
 *
 * 2. Importamos `globals.css` con los tokens del v2 como CSS vars
 *    (espejo de `docs/handoff-design/design_tokens.ts`).
 *
 * 3. Importamos `operator-shared.css` literal (~4710 líneas, copia
 *    sin tocar del handoff). Trae todos los componentes del design
 *    system del Sprint 1.5 audit-cerrado: chrome shell, etable,
 *    chat, calc-section, mobile, audit, etc.
 *
 * Sprint 2 deliberadamente mantiene este CSS as-is — el cleanup a
 * Tailwind utilities va en Sprint 5 (ver
 * `docs/tech-debt/css-migration.md`).
 */
import { Fraunces, Inter_Tight, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import "./operator-shared.css";

// Fraunces — serif italic para hero "Hola, soy Valentina", importes
// editoriales, acentos tipográficos cálidos. Optical size cubre 13-42px.
const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});

// Inter Tight — UI primaria (títulos UI, body, labels).
const interTight = Inter_Tight({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

// JetBrains Mono — números (medidas, importes USD/ARS, eyebrows
// uppercase tipo "DEL BRIEF").
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-v2-root
      className={`${fraunces.variable} ${interTight.variable} ${jetbrainsMono.variable} bg-bg text-ink`}
    >
      {children}
    </div>
  );
}
