/**
 * Design tokens — source of truth para lugares que NO pueden leer CSS vars.
 *
 * Los tokens principales viven como CSS variables en `src/app/globals.css` y
 * se exponen como utility classes de Tailwind en `tailwind.config.ts`
 * (`bg-acc`, `text-t1`, etc.). Úsalos primero.
 *
 * Este módulo es el **fallback** para contextos donde las CSS vars no
 * funcionan:
 *   - Temas de editor (CodeMirror): recibe hex literal, no computa CSS.
 *   - `stroke`/`fill` inline en SVG JSX que no heredan currentColor.
 *   - Librerías third-party que aceptan solo string hex.
 *
 * **IMPORTANTE:** si cambiás un valor acá, cambialo también en
 * `globals.css`. Son dos copias del mismo dato a propósito — una para
 * el browser runtime (CSS var) y otra para TypeScript build time.
 */

export const COLORS = {
  /* Superficies (dark, "pizarra & acero") */
  bg: "#070b10",
  s1: "#0a0e13",
  s2: "#111720",
  s3: "#1a2230",

  /* Bordes y líneas sutiles — tint crema fría */
  b1: "rgba(232,237,229,0.06)",
  b2: "rgba(232,237,229,0.12)",
  b3: "rgba(232,237,229,0.18)",

  /* Tinta */
  t1: "#e8ede5",
  t2: "rgba(232,237,229,0.66)",
  t3: "rgba(232,237,229,0.42)",
  t4: "rgba(232,237,229,0.22)",

  /* Acento "añil sobrio" (WCAG AA large text con white) */
  acc: "#5f7da0",
  acc2: "rgba(95,125,160,0.14)",
  acc3: "rgba(95,125,160,0.22)",
  accInk: "#0f1318",
  accHover: "#4d678a",
  accShadow: "rgba(95,125,160,0.30)",

  /* Estado */
  grn: "#5cb38f",
  grn2: "rgba(92,179,143,0.14)",
  amb: "#d9a25a",
  amb2: "rgba(217,162,90,0.14)",
  red: "#d46b60",
} as const;

export type ColorToken = keyof typeof COLORS;
