/**
 * Datos canon del presupuesto Cueto-Heredia (Master §13).
 *
 * Sprint 2 chrome-refactor: hardcodeamos las cifras canónicas para
 * que el chrome shell rendee con datos consistentes con los mockups
 * del handoff. NO hay fetch, NO hay state — esto es purely visual.
 *
 * Las cifras vienen de Master §13 (sección "Cifras canon Cueto-
 * Heredia"). Lo que no está en Master se anota como `placeholder
 * Sprint 2` para que el reviewer sepa qué es sintético.
 */

export const CANONICAL_QUOTE = {
  id: "PRES-2026-018",
  client: {
    name: "Cueto-Heredia",
    architect: "Cueto-Heredia Arquitectas",
    discount: 5, // % importado · Master §13
  },
  project: {
    address: "PROYECTO RESIDENCIAL", // placeholder Sprint 2 (sin PII)
    type: "particular" as const,
  },
  material: {
    sku: "SILESTONENORTE",
    name: "Silestone Blanco Norte",
    surface: 6.5, // m² · Master §13
    priceUSD: 249, // c/IVA por m² (mockup) · Master §13 nota: difiere de catálogo (USD 519)
  },
  totals: {
    materialUSD: 1538, // Master §13
    laborARS: 597970, // placeholder Sprint 2 (derivado del total)
    freightARS: 62920, // placeholder Sprint 2 (derivado del total)
    grandTotalARS: 660890, // Master §13 · cifra canon
  },
  status: "draft" as const,
  createdAt: "2026-05-04",
} as const;

export type CanonicalQuote = typeof CANONICAL_QUOTE;

/**
 * Los 5 pasos del flow de presupuesto (Master §6).
 * `id` matchea el segmento de URL (`/quotes/[id]/[step]`).
 */
export const STEPS = [
  { id: "brief", label: "Brief", order: 1 },
  { id: "contexto", label: "Contexto", order: 2 },
  { id: "despiece", label: "Despiece", order: 3 },
  { id: "calculo", label: "Cálculo", order: 4 },
  { id: "pdf", label: "PDF", order: 5 },
] as const;

export type StepId = (typeof STEPS)[number]["id"];

/**
 * Helper: extrae el step actual desde un pathname.
 * Pathname esperado: `/quotes/[id]/[step]` (o cualquier variante
 * que contenga uno de los segmentos canónicos).
 */
export function getCurrentStep(pathname: string): StepId {
  if (pathname.includes("/contexto")) return "contexto";
  if (pathname.includes("/despiece")) return "despiece";
  if (pathname.includes("/calculo")) return "calculo";
  if (pathname.includes("/pdf")) return "pdf";
  return "brief"; // default · paso 1 si no matchea ninguno
}

/* ════════════════════════════════════════════════════════════════════════
   Sprint 2 paso-2-contexto · CANONICAL_CONTEXT
   ════════════════════════════════════════════════════════════════════════
   Espejo de Master §13 cifras canon Cueto-Heredia + mockup 01-A
   (11 campos visibles en el grid del paso 2). Los `origin` reflejan el
   path de extracción que Valentina usaría: BRIEF (texto/PDF directo) o
   INFERIDO (cruzando catálogos / reglas). */

import type { ContextResponse } from "../api";

export const CANONICAL_CONTEXT: ContextResponse = {
  cliente: { value: "Cueto-Heredia Arquitectura", origin: "BRIEF" },
  contacto: { value: "estudio@cueto-heredia.ar", origin: "INFERIDO" },
  localidad: { value: "Belgrano · CABA", origin: "BRIEF" },
  plazo: { value: "3 semanas", origin: "BRIEF" },
  tipologia: { value: "cocina U + isla", origin: "BRIEF" },
  tipo_obra: { value: "particular", origin: "INFERIDO" },
  material: { value: "Silestone Blanco Norte 20mm", origin: "BRIEF" },
  pileta: { value: "empotrada · Franke FX110-50 (cliente)", origin: "BRIEF" },
  zocalo: { value: "contra pared · 12 cm", origin: "BRIEF" },
  regrueso: { value: "frontal · 4 cm", origin: "INFERIDO" },
  anafe: { value: true, origin: "INFERIDO" },
};
