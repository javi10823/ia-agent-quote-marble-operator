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

import type { ContextResponse, Piece, TimelineStep } from "../api";

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

/* ════════════════════════════════════════════════════════════════════════
   Sprint 3 paso-3-despiece · CANONICAL_PIECES por quoteId
   ════════════════════════════════════════════════════════════════════════
   Las 5 piezas que Valentina propone para PRES-2026-018 (mockup
   04-despiece-A-ia-propuso). Confirm-bar canon: "5 piezas · 6.81 m²".
   Dimensiones literales del mockup en cm → guardadas en mm (cm × 10).

   m² unitario = width_mm · depth_mm / 1e6:
     R1 285×62 = 1.77 · R2 240×62 = 1.49 · R3 180×62 = 1.12 ·
     R4 285×8 = 0.23 · R5 220×100 = 2.20  → total 6.81 m² ✓

   Indexado por quoteId desde el inicio (lección Sprint 2.5 fix-up #2 del
   PR #460): NUNCA hardcodear PRES-018, todo lookup pasa por quoteId. */

export const CANONICAL_PIECES_018: Piece[] = [
  {
    id: "R1",
    type: "encimera",
    label: "Mesada perimetral · brazo izq",
    sublabel: "contra pared norte",
    width_mm: 2850,
    depth_mm: 620,
    quantity: 1,
    options: { regrueso_mm: 40 },
    detected_symbols: [{ src: "INGLETE", out: "CORTE45" }],
    origin: "IA",
    confidence: 0.92,
    extracted_from: "plan_p1_z1",
  },
  {
    // R2 = bacha · pieza sobre la que va el chat scoped del mockup 06.
    id: "R2",
    type: "encimera",
    label: "Mesada perimetral · brazo derecho",
    sublabel: "con bacha empotrada",
    width_mm: 2400,
    depth_mm: 620,
    quantity: 1,
    options: { pileta: { tipo: "empotrada", sku: "JOHNSON-C37D" }, regrueso_mm: 40 },
    detected_symbols: [
      { src: "DESAGUE", out: "AGUJEROAPOYO" },
      { src: "INGLETE", out: "CORTE45" },
    ],
    origin: "IA",
    confidence: 0.88,
    extracted_from: "plan_p1_z2",
  },
  {
    id: "R3",
    type: "encimera",
    label: "Mesada perimetral · fondo",
    sublabel: "une R1 y R2",
    width_mm: 1800,
    depth_mm: 620,
    quantity: 1,
    options: { regrueso_mm: 40 },
    detected_symbols: [{ src: "INGLETE×2", out: "CORTE45" }],
    origin: "IA",
    confidence: 0.9,
    extracted_from: "plan_p1_z3",
  },
  {
    id: "R4",
    type: "alzada",
    label: "Alzada salpicadero",
    sublabel: "contra pared · h=8cm corre 285cm",
    width_mm: 2850,
    depth_mm: 80,
    quantity: 1,
    options: { alzada: true, tomas: 2 },
    detected_symbols: [{ src: "2 TOMAS", out: "TOMAS" }],
    origin: "IA",
    confidence: 0.85,
    extracted_from: "plan_p1_z1",
  },
  {
    id: "R5",
    type: "isla",
    label: "Isla central",
    sublabel: "con voladizo 30cm lado comedor",
    width_mm: 2200,
    depth_mm: 1000,
    quantity: 1,
    options: {},
    origin: "IA",
    confidence: 0.83,
    extracted_from: "plan_p1_z4",
  },
];

/** PRES-2026-017 · Familia Pereyra · dataset reducido y DISTINTO al de 018
 *  (el mockup desktop no cubre el despiece de Pereyra — Master §6: Pereyra
 *  sólo aparece en mobile/dashboard). Sirve de regression check de que los
 *  datasources indexan por quoteId (no contaminan con PRES-018). */
export const CANONICAL_PIECES_017: Piece[] = [
  {
    id: "R1",
    type: "encimera",
    label: "Mesada en U · tramo A",
    sublabel: "contra pared",
    width_mm: 3000,
    depth_mm: 600,
    quantity: 1,
    options: {},
    origin: "IA",
    confidence: 0.86,
    extracted_from: "plan_p1_z1",
  },
  {
    id: "R2",
    type: "encimera",
    label: "Mesada en U · tramo B",
    sublabel: "con pileta empotrada",
    width_mm: 1600,
    depth_mm: 600,
    quantity: 1,
    options: { pileta: { tipo: "empotrada" } },
    detected_symbols: [{ src: "DESAGUE", out: "AGUJEROAPOYO" }],
    origin: "IA",
    confidence: 0.84,
    extracted_from: "plan_p1_z2",
  },
  {
    id: "R3",
    type: "isla",
    label: "Isla",
    sublabel: "libre 4 lados",
    width_mm: 1800,
    depth_mm: 900,
    quantity: 1,
    options: {},
    origin: "IA",
    confidence: 0.8,
    extracted_from: "plan_p1_z3",
  },
];

/** Fallback para los quotes restantes del dataset (sin canon de piezas).
 *  Vacío a propósito → `listPiecesForQuote` devuelve status:'failed' y la UI
 *  cae al empty state (mockup 16). */
export const CANONICAL_PIECES_GENERIC: Piece[] = [];

export const PIECES_BY_QUOTE_ID: Record<string, Piece[]> = {
  "PRES-2026-018": CANONICAL_PIECES_018, // Cueto-Heredia (case desktop completo)
  "PRES-2026-017": CANONICAL_PIECES_017, // Pereyra (regression datasources por quoteId)
};

/** Timeline canon de las 4 pasadas de Valentina sobre PRES-2026-018
 *  (mockup 04-despiece-A · 4 pasadas + 3 símbolos detectados). */
export const CANONICAL_TIMELINE_018: TimelineStep[] = [
  {
    step: 1,
    label: "Inventario",
    state: "done",
    detail: "cocina U + isla · 1 pileta empotrada · 1 alzada · 1 zócalo",
  },
  {
    step: 2,
    label: "Paredes y libres",
    state: "done",
    detail: "3 brazos perimetrales (R1·R2·R3) · isla libre 4 lados (R5)",
  },
  {
    step: 3,
    label: "Medidas",
    state: "done",
    detail: "cotas en mm convertidas a cm · INGLETE/DESAGUE/TOMAS detectados",
  },
  {
    step: 4,
    label: "Verificación",
    state: "done",
    detail: "5 piezas confirmadas · 6.81 m²",
  },
];

export const TIMELINE_BY_QUOTE_ID: Record<string, TimelineStep[]> = {
  "PRES-2026-018": CANONICAL_TIMELINE_018,
};

/** Timeline mostrado durante la carga inicial (skeleton) — pasada 4 corriendo. */
export const DESPIECE_LOADING_TIMELINE: TimelineStep[] = [
  { step: 1, label: "Inventario", state: "done" },
  { step: 2, label: "Paredes y libres", state: "done" },
  { step: 3, label: "Medidas", state: "done" },
  { step: 4, label: "Verificación", state: "running", detail: "cruzando con catálogo…" },
];

/* ════════════════════════════════════════════════════════════════════════
   Sprint 3 paso-4-calculo · CANONICAL_CALCULATION_*
   ════════════════════════════════════════════════════════════════════════
   Cifras LITERALES del mockup 07-paso4-A-v4.html (Master §13 + decisión D
   PR #461: las cifras canon son design references; mocks usan estos
   valores fijos del mockup, NO los del motor real). */

import type { CalculationResult, MaterialRow, LaborRowData } from "../api/types";

/** PRES-2026-018 · Cueto-Heredia · Silestone Blanco Norte (mockup 07-paso4-A-v4). */
const MATERIAL_018: MaterialRow[] = [
  {
    label: "Silestone Blanco Norte 20mm",
    sub: "6,50 m² reales del trabajo · USD 249 c/IVA · piezas en paso 3",
    qty: "6,50 m²",
    unit: "USD 249",
    total: "USD 1.619",
    variant: "default",
    audit: [
      { kind: "SOURCE", text: "Brief (texto) + catalog/silestone.json sku SILESTONENORTE" },
      { kind: "REGLA", text: "Material importado en USD; IVA ya incluido en lista" },
      { kind: "CALC", text: "6,50 m² × USD 249 = USD 1.619" },
    ],
  },
  {
    label: "Descuento arquitecta",
    sub: "Cueto-Heredia · architects.json · 5% sobre material importado",
    qty: "−5%",
    unit: "—",
    total: "−USD 81",
    variant: "discount",
    audit: [
      {
        kind: "SOURCE",
        text: "catalog/architects.json · firm Cueto-Heredia · discount imported 5%",
      },
      { kind: "REGLA", text: "Sólo aplica sobre material importado, nunca sobre MO ni flete" },
      { kind: "CALC", text: "USD 1.619 × −5% = −USD 81" },
    ],
  },
];

const LABOR_018: LaborRowData[] = [
  {
    sku: "COLOCACION",
    label: "Colocación",
    sub: "6,50 m² · cuarzo 20mm usa SKU estándar (no DEKTON)",
    qty: "6,50",
    basePrice: "$49.698",
    iva: "×1,21",
    total: "$390.875",
    audit: [
      { kind: "SOURCE", text: "labor.json sku COLOCACION · $49.698 s/IVA / m²" },
      { kind: "CALC", text: "6,50 m² × $49.698 × 1,21 = $390.875" },
    ],
  },
  {
    sku: "PEGADOPILETA",
    label: "Pegado pileta empotrada",
    sub: "1 unid · cliente trae la pileta",
    qty: "1",
    basePrice: "$53.840",
    iva: "×1,21",
    total: "$65.146",
    audit: [
      { kind: "SOURCE", text: "labor.json sku PEGADOPILETA" },
      { kind: "CALC", text: "$53.840 × 1,21 = $65.146" },
    ],
  },
  {
    sku: "ANAFE",
    label: "Anafe (corte y cargas)",
    sub: "1 unid · detectado en plano (símbolo)",
    qty: "1",
    basePrice: "$35.617",
    iva: "×1,21",
    total: "$43.097",
    audit: [
      { kind: "SOURCE", text: "labor.json sku ANAFE" },
      { kind: "CALC", text: "$35.617 × 1,21 = $43.097" },
    ],
  },
  {
    sku: "REGRUESO",
    label: "Regrueso frontal",
    sub: "4,98 ml · cuarzo 20mm usa REGRUESO (no FALDON+CORTE45)",
    qty: "4,98 ml",
    basePrice: "$13.810",
    iva: "×1,21",
    total: "$83.216",
    audit: [
      { kind: "SOURCE", text: "labor.json sku REGRUESO" },
      {
        kind: "REGLA",
        text: "Para cuarzo 20mm cuenta REGRUESO; FALDON+CORTE45 sólo en otros espesores",
      },
      { kind: "CALC", text: "4,98 ml × $13.810 × 1,21 = $83.216" },
    ],
  },
  {
    sku: "TOMAS",
    label: "Tomas (perforación)",
    sub: "2 unid · auto: alzada + zócalo >10cm",
    qty: "2",
    basePrice: "$6.461",
    iva: "×1,21",
    total: "$15.636",
    audit: [
      { kind: "SOURCE", text: "labor.json sku TOMAS" },
      {
        kind: "REGLA",
        text: "+1 por alzada (auto) · +1 por zócalo >10cm (auto, regla altura) = 2 unid",
      },
      { kind: "CALC", text: "$6.461 × 2 × 1,21 = $15.636" },
    ],
  },
];

export const CANONICAL_CALCULATION_018: CalculationResult = {
  quoteId: "PRES-2026-018",
  status: "ok",
  bannerSummary:
    "✓ Calculado · Silestone Blanco Norte 20mm · 6,50 m² · Total $660.890 ARS + USD 1.538",
  bannerAdjustments: [
    { text: "−5% descuento arquitecta Cueto-Heredia sobre material importado" },
    { text: "+TOMAS automático: 1 por alzada + 1 por zócalo >10cm" },
    { text: "REGRUESO en lugar de FALDON+CORTE45 (cuarzo 20mm)" },
  ],
  material: { rows: MATERIAL_018, subtotal: "USD 1.538" },
  merma: {
    status: "aplica",
    chipLabel: "APLICA",
    sub: "ceil(6,50 / 2,10) = 4 medias placas → 8,40 m² · desperdicio 1,90 m² ≥ 1 m² → aplica sobrante",
    rows: [
      {
        label: "Sobrante facturado",
        sub: "0,95 m² (mitad del desperdicio) · valor proporcional al m²",
        qty: "0,95 m²",
        unit: "USD 249",
        total: "USD 237",
        audit: [
          {
            kind: "REGLA",
            text: "Sobrante = desperdicio/2 cuando desperdicio ≥ 1 m² (sintéticos)",
          },
          { kind: "CALC", text: "(8,40 − 6,50)/2 × USD 249 = USD 237" },
        ],
      },
    ],
    sobranteToggle: {
      label: "Ofrecer sobrante al cliente como pieza adicional",
      defaultChecked: false,
    },
    stockToggle: {
      label: "Stock confirmado en taller (descuenta de stock.json)",
      defaultChecked: true,
    },
  },
  labor: { rows: LABOR_018, subtotal: "$597.970" },
  piletas: {
    chipLabel: "N/A — pileta empotrada (la trae el cliente)",
    variant: "na",
    sub: "MO de pegado ya contabilizada en sección 03 (PEGADOPILETA)",
  },
  flete: {
    zona: "Rosario",
    qty: "1 viaje",
    basePrice: "$ 52.000",
    total: "$ 62.920",
    audit: [
      { kind: "SOURCE", text: "delivery-zones.json zona Rosario · ENVIOROS $52.000 s/IVA" },
      { kind: "REGLA", text: "Particular · 1 viaje (no edificio)" },
      { kind: "CALC", text: "$52.000 × 1,21 = $62.920" },
    ],
  },
  totals: {
    ars: { value: "$660.890", meta: "MO + flete · IVA 21% incluido" },
    usd: { value: "USD 1.538", meta: "6,50 m² × USD 249 − 5% arq." },
  },
  datosPdf: {
    plazo: "3 semanas desde confirmación de medidas",
    anticipoPct: "50",
    saldo: "contra entrega · transferencia / efectivo",
    envio: "Belgrano · CABA · coordinar día con Marina",
    notas: "Cueto-Heredia · arquitecta · 5% importado aplicado",
    vigenciaDias: "15",
  },
};

/** PRES-2026-017 · Pereyra (mismo shape, datos distintos para verificar params.id). */
export const CANONICAL_CALCULATION_017: CalculationResult = {
  ...CANONICAL_CALCULATION_018,
  quoteId: "PRES-2026-017",
  bannerSummary:
    "✓ Calculado · Silestone Blanco Norte 20mm · 6,50 m² · Total $660.890 ARS + USD 1.538",
  bannerAdjustments: [
    { text: "Sin descuento arquitecta (Pereyra es particular)" },
    { text: "+TOMAS automático: 1 por alzada" },
  ],
  datosPdf: {
    plazo: "4 semanas",
    anticipoPct: "40",
    saldo: "contra entrega",
    envio: "Rosario · zona sur",
    notas: "Familia Pereyra · particular",
    vigenciaDias: "15",
  },
};

/** Fallback gracioso para IDs desconocidos (lección Sprint 3 día 3: SIN crash). */
export const CANONICAL_CALCULATION_GENERIC: CalculationResult = {
  quoteId: "—",
  status: "pending",
  bannerSummary: "Cálculo pendiente · vení desde el paso 3 para generar el desglose",
  bannerAdjustments: [],
  material: { rows: [], subtotal: "—" },
  merma: { status: "na", chipLabel: "—", sub: "sin datos" },
  labor: { rows: [], subtotal: "—" },
  piletas: { chipLabel: "—", variant: "na" },
  flete: { zona: "—", qty: "—", basePrice: "—", total: "—" },
  totals: {
    ars: { value: "—", meta: "sin datos" },
    usd: { value: "—", meta: "sin datos" },
  },
  datosPdf: { plazo: "—", anticipoPct: "—", saldo: "—", envio: "—", notas: "—", vigenciaDias: "—" },
};

/** Variante estado B · post-PATCH (cambio de material upstream → merma fantasma). */
export const CANONICAL_CALCULATION_018_PATCH_ERROR: CalculationResult = {
  ...CANONICAL_CALCULATION_018,
  status: "error",
  merma: {
    status: "error",
    chipLabel: "ERROR",
    sub: "merma del cálculo anterior quedó huérfana tras cambio de material",
    errorRow: {
      label: "Merma Silestone (huérfana)",
      detail: "0,95 m² × USD 249 = USD 237 · proviene del cálculo previo, no debería estar acá",
      fixLabel: "✕ Eliminar merma",
    },
  },
  totals: {
    ars: { value: "$660.890", meta: "MO + flete" },
    usd: { value: "USD 1.538", meta: "material importado" },
    warnDetail: "+ merma fantasma USD 237 (eliminar antes de confirmar)",
  },
  patchError: {
    traceId: "q-2026-0287",
    msg: "Detecté una merma fantasma del cálculo anterior. Cambiaste el material y la línea de sobrante quedó huérfana. Puedo eliminarla con un click, o querés ver el diff con la versión 1 primero.",
  },
};

export const CALCULATIONS_BY_QUOTE_ID: Record<string, CalculationResult> = {
  "PRES-2026-018": CANONICAL_CALCULATION_018,
  "PRES-2026-017": CANONICAL_CALCULATION_017,
};

// ─── Sprint 3 error-states · mockup 17 (chat scoped flagged) ─────────
// Preset literal del mockup 17-chat-error-ia.html (4 mensajes sobre R5
// zócalo perimetral · el último de Valentina es flagged como inútil).
export const CHAT_FLAGGED_PRESET_018: import("../api/types").ChatFlaggedPreset = {
  sessionInfo: "4 mensajes · primer turno hace 8 min",
  sessionContext: "CHAT ABIERTO SOBRE R5 · ZÓCALO PERIMETRAL · HACE 8 MIN",
  pieceRefId: "R5",
  composerPrefill:
    "¿Y el regrueso del zócalo? Necesito saber si va con regrueso 4cm o 2cm para presupuestar bien.",
  messages: [
    {
      id: "flag-m1",
      role: "user",
      content:
        "R5 lo dejé en 12cm porque el cliente quiere zócalo alto. Eso me suma TOMAS según vos, ¿qué pasa si lo bajo a 8cm?",
      timestamp: "14:15",
      relativeTs: "14:15 · hace 8 min",
    },
    {
      id: "flag-m2",
      role: "valentina",
      content:
        'Si bajás R5 a 8cm ya no aplica la regla ">10cm = 1 TOMAS automático". Te queda solo la TOMAS de la alzada (R3). El cálculo del paso 4 baja en $7.818 (1 TOMAS menos). Ojo: zócalos <10cm pueden quedar visualmente cortos contra muebles altos. Decisión del cliente.',
      timestamp: "14:16",
      relativeTs: "14:16 · hace 7 min",
    },
    {
      id: "flag-m3",
      role: "user",
      content:
        "¿Y el regrueso del zócalo? Necesito saber si va con regrueso 4cm o 2cm para presupuestar bien.",
      timestamp: "14:22",
      relativeTs: "14:22 · hace 1 min",
    },
    {
      id: "flag-m4",
      role: "valentina",
      content:
        "El regrueso es una técnica de marmolería que consiste en pegar dos piezas para dar mayor espesor visual al canto. En general se usa en mesadas para dar más presencia al frente. Hay distintos espesores disponibles según el material.",
      timestamp: "14:23",
      relativeTs: "14:23 · hace 30s",
      flagged: true,
    },
  ],
};

// ─── Sprint 4 paso-5-pdf-preview · mockup 18 ─────────────────────────────
// Traces canónicos del bloque Trazabilidad. Literales del mockup 18.
export const CANONICAL_PDF_TRACE_018: import("../api/types").PdfTrace = {
  traceId: "op-2026-0847-a3f9c1",
  promptVersion: "v0.4.2 · contexto+despiece+pricing",
  inputsHash: "sha256:8b4a…d72e",
  snapshot: "materials.json @ 03.05 · architects.json @ 02.05",
};
export const CANONICAL_PDF_TRACE_017: import("../api/types").PdfTrace = {
  traceId: "op-2026-0792-c4e2b8",
  promptVersion: "v0.4.2 · contexto+despiece+pricing",
  inputsHash: "sha256:7c1f…9a82",
  snapshot: "materials.json @ 02.04 · architects.json @ 02.04",
};
export const CANONICAL_PDF_TRACE_GENERIC: import("../api/types").PdfTrace = {
  traceId: "—",
  promptVersion: "—",
  inputsHash: "—",
  snapshot: "—",
};
export const PDF_TRACE_BY_QUOTE_ID: Record<string, import("../api/types").PdfTrace> = {
  "PRES-2026-018": CANONICAL_PDF_TRACE_018,
  "PRES-2026-017": CANONICAL_PDF_TRACE_017,
};
