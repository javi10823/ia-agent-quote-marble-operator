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

/* ════════════════════════════════════════════════════════════════════════
   Sprint 2.5 fix-up · contextos canon adicionales por quoteId
   ════════════════════════════════════════════════════════════════════════
   Fix BLOCKER detectado en Visual Check del PR #460:
   `/quotes/PRES-2026-017/contexto` cargaba datos de Cueto-Heredia porque
   `getContextForQuote()` devolvía siempre `CANONICAL_CONTEXT`. Ahora el
   mock indexa por quoteId via CONTEXT_BY_QUOTE_ID + fallback genérico.

   CANONICAL_CONTEXT (Cueto-Heredia · PRES-2026-018) NO se modifica para
   preservar regression del paso 2 del Sprint 2. */

/** PRES-2026-017 · Familia Pereyra · Silestone Blanco Norte (Master §13). */
export const CANONICAL_CONTEXT_PEREYRA: ContextResponse = {
  cliente: { value: "Familia Pereyra", origin: "BRIEF" },
  contacto: { value: null, origin: "FALTA" },
  localidad: { value: "Rosario · zona sur", origin: "BRIEF" },
  plazo: { value: null, origin: "FALTA" },
  tipologia: { value: "cocina U + isla", origin: "BRIEF" },
  tipo_obra: { value: "particular", origin: "INFERIDO" },
  material: { value: "Silestone Blanco Norte", origin: "BRIEF" },
  pileta: { value: "empotrada", origin: "INFERIDO" },
  zocalo: { value: "contra pared · 5 cm", origin: "DEFAULT" },
  regrueso: { value: "frontal · 4 cm", origin: "INFERIDO" },
  anafe: { value: false, origin: "INFERIDO" },
};

/** Fallback para quotes del dataset sin canon definido. */
export const CANONICAL_CONTEXT_GENERIC: ContextResponse = {
  cliente: { value: null, origin: "FALTA" },
  contacto: { value: null, origin: "FALTA" },
  localidad: { value: null, origin: "FALTA" },
  plazo: { value: null, origin: "FALTA" },
  tipologia: { value: null, origin: "FALTA" },
  tipo_obra: { value: "particular", origin: "DEFAULT" },
  material: { value: null, origin: "FALTA" },
  pileta: { value: null, origin: "FALTA" },
  zocalo: { value: "contra pared · 5 cm", origin: "DEFAULT" },
  regrueso: { value: null, origin: "FALTA" },
  anafe: { value: false, origin: "DEFAULT" },
};

/** Lookup canon por quoteId. Quotes no listadas caen al GENERIC. */
export const CONTEXT_BY_QUOTE_ID: Record<string, ContextResponse> = {
  "PRES-2026-018": CANONICAL_CONTEXT, // Cueto-Heredia (mantiene comportamiento previo)
  "PRES-2026-017": CANONICAL_CONTEXT_PEREYRA, // Pereyra (fix BLOCKER PR #460)
};

/* ════════════════════════════════════════════════════════════════════════
   Sprint 2.5 fix-up #2 · Banner Valentina del paso 2 por quoteId
   ════════════════════════════════════════════════════════════════════════
   El banner pristine "Valentina extrajo del brief: …" estaba hardcodeado
   a Cueto-Heredia en ContextForm. Lo movemos a un lookup por quoteId.
   El componente recibe el string ya resuelto via prop. */

export const BRIEF_SUMMARY_BY_QUOTE_ID: Record<string, string> = {
  "PRES-2026-018":
    "cliente Cueto-Heredia (match arquitecta · −5%) · cocina con pileta empotrada · zócalo 12cm activa TOMAS automático",
  "PRES-2026-017":
    "cliente Familia Pereyra · cocina U + isla en Rosario · Silestone Blanco Norte con pileta empotrada",
};

export const BRIEF_SUMMARY_GENERIC =
  "extraje los datos del brief — revisalos y editá lo que haga falta";
