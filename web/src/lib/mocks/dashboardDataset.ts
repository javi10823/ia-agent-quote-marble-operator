/**
 * Dataset del dashboard · Sprint 2.5 switch-to-main.
 *
 * Adaptado de docs/handoff-design/design_files/dashboard-dataset.js.
 * 16 quotes visibles + COUNTS totales (47 quotes con perdidos antiguos).
 *
 * Casos validados (Master §13):
 *   - PRES-2026-018 · Cueto-Heredia · Negro Brasil · USD 2.184
 *   - PRES-2026-017 · Pereyra · Silestone Blanco Norte · ARS 660.890 (USD 1.538)
 *
 * El resto son sintéticos coherentes con catalogos.
 */

export type DashboardStatus = "draft" | "sent" | "expired" | "lost";
export type DashboardCurrency = "ARS" | "USD";
/** Canal de origen · "web" = generado por el cliente desde la web pública
 * (id `web-*`, Quote.source="web") · "operator" = cargado por Marina.
 * Opcional: legacy/mocks sin el campo se derivan del prefijo del id. */
export type DashboardSource = "web" | "operator";

export interface DashboardQuote {
  readonly id: string;
  readonly source?: DashboardSource;
  readonly client: string;
  readonly clientFull: string;
  readonly material: string;
  readonly m2: number;
  readonly currency: DashboardCurrency;
  readonly amount: number;
  readonly amountSecondary: number | null;
  readonly status: DashboardStatus;
  readonly lastActivityDays: number;
  readonly daysToExpire?: number;
  readonly sentDate: string | null;
  readonly expiredDate?: string;
  readonly lostDate?: string;
  readonly visits?: number;
}

export interface DashboardCounts {
  all: number;
  draft: number;
  sent: number;
  expired: number;
  lost: number;
}

export const DASHBOARD_QUOTES: ReadonlyArray<DashboardQuote> = [
  // ─── ENVIADO (12) ─────────────────────────────────────────────────────
  {
    id: "PRES-2026-018",
    source: "operator",
    client: "Cueto-Heredia",
    clientFull: "Estudio Cueto-Heredia · cocina Belgrano",
    material: "Granito Negro Brasil",
    m2: 8.4,
    currency: "USD",
    amount: 2_184,
    amountSecondary: null,
    status: "sent",
    lastActivityDays: 3,
    daysToExpire: 4,
    sentDate: "12/03",
  },
  {
    id: "PRES-2026-017",
    source: "web",
    client: "Familia Pereyra",
    clientFull: "Familia Pereyra · cocina U + isla",
    material: "Silestone Blanco Norte",
    m2: 6.5,
    currency: "ARS",
    amount: 660_890,
    amountSecondary: 1_538,
    status: "sent",
    lastActivityDays: 6,
    daysToExpire: 1,
    sentDate: "08/03",
  },
  {
    id: "PRES-2026-014",
    client: "Estudio Lacroze",
    clientFull: "Estudio Lacroze Arq. · departamento Recoleta",
    material: "Calacatta Borghini",
    m2: 4.2,
    currency: "USD",
    amount: 3_780,
    amountSecondary: null,
    status: "sent",
    lastActivityDays: 8,
    daysToExpire: 0, // vence hoy
    sentDate: "01/03",
  },
  {
    id: "PRES-2026-013",
    client: "Marina Ortega",
    clientFull: "Marina Ortega · baño suite",
    material: "Travertino Romano",
    m2: 3.1,
    currency: "ARS",
    amount: 312_400,
    amountSecondary: 728,
    status: "sent",
    lastActivityDays: 11,
    daysToExpire: 6,
    sentDate: "24/02",
  },
  {
    id: "PRES-2026-011",
    client: "Estudio Belgrano",
    clientFull: "Estudio Belgrano Arq. · oficina Núñez",
    material: "Granito Verde Ubatuba",
    m2: 12.8,
    currency: "USD",
    amount: 2_944,
    amountSecondary: null,
    status: "sent",
    lastActivityDays: 14,
    daysToExpire: 12,
    sentDate: "18/02",
  },

  // ─── VENCIDO (3) ──────────────────────────────────────────────────────
  {
    id: "PRES-2026-016",
    client: "Familia Mansilla",
    clientFull: "Familia Mansilla · cocina lineal",
    material: "Silestone Blanco Norte",
    m2: 5.4,
    currency: "ARS",
    amount: 548_220,
    amountSecondary: 1_278,
    status: "expired",
    lastActivityDays: 18,
    daysToExpire: -3,
    sentDate: "14/02",
    expiredDate: "11/03",
    visits: 2,
  },
  {
    id: "PRES-2026-012",
    client: "Estudio Vidal",
    clientFull: "Estudio Vidal · departamento Palermo",
    material: "Granito Negro Brasil",
    m2: 7.8,
    currency: "USD",
    amount: 2_028,
    amountSecondary: null,
    status: "expired",
    lastActivityDays: 22,
    daysToExpire: -5,
    sentDate: "08/02",
    expiredDate: "08/03",
    visits: 4,
  },
  {
    id: "PRES-2026-009",
    client: "Familia Storni",
    clientFull: "Familia Storni · ampliación cocina",
    material: "Calacatta Statuario",
    m2: 9.2,
    currency: "USD",
    amount: 4_416,
    amountSecondary: null,
    status: "expired",
    lastActivityDays: 28,
    daysToExpire: -11,
    sentDate: "01/02",
    expiredDate: "01/03",
    visits: 1,
  },

  // ─── DRAFT (4) ────────────────────────────────────────────────────────
  {
    id: "PRES-2026-019",
    client: "Familia Sosa",
    clientFull: "Familia Sosa · cocina + isla",
    material: "Granito Negro Brasil",
    m2: 6.2,
    currency: "USD",
    amount: 1_612,
    amountSecondary: null,
    status: "draft",
    lastActivityDays: 0,
    sentDate: null,
  },
  {
    id: "PRES-2026-015",
    client: "Estudio Hauer",
    clientFull: "Estudio Hauer · loft Villa Crespo",
    material: "Silestone Eternal Calacatta",
    m2: 3.8,
    currency: "ARS",
    amount: 489_320,
    amountSecondary: 1_140,
    status: "draft",
    lastActivityDays: 5,
    sentDate: null,
  },

  // ─── DRAFT extras (Bustos+Roca, antes pending-review · removido Sprint 1.5 #7) ───
  {
    id: "PRES-2026-020",
    client: "Familia Bustos",
    clientFull: "Familia Bustos · baño completo",
    material: "Travertino Romano",
    m2: 4.4,
    currency: "ARS",
    amount: 412_800,
    amountSecondary: 962,
    status: "draft",
    lastActivityDays: 1,
    sentDate: null,
  },
  {
    id: "PRES-2026-010",
    client: "Estudio Roca",
    clientFull: "Estudio Roca Arq. · cocina Olivos",
    material: "Granito Verde Ubatuba",
    m2: 8.6,
    currency: "USD",
    amount: 1_978,
    amountSecondary: null,
    status: "draft",
    lastActivityDays: 2,
    sentDate: null,
  },

  // ─── PERDIDO (26 total — 4 visibles en lista, resto en counter) ───────
  {
    id: "PRES-2026-008",
    client: "Familia Linares",
    clientFull: "Familia Linares · cocina",
    material: "Silestone Blanco Norte",
    m2: 5.1,
    currency: "ARS",
    amount: 518_440,
    amountSecondary: 1_208,
    status: "lost",
    lastActivityDays: 35,
    sentDate: "20/01",
    lostDate: "15/02",
  },
  {
    id: "PRES-2026-007",
    client: "Estudio Ferrer",
    clientFull: "Estudio Ferrer · departamento Caballito",
    material: "Granito Negro Brasil",
    m2: 4.8,
    currency: "USD",
    amount: 1_248,
    amountSecondary: null,
    status: "lost",
    lastActivityDays: 42,
    sentDate: "14/01",
    lostDate: "08/02",
  },
  {
    id: "PRES-2026-005",
    client: "Familia Aguirre",
    clientFull: "Familia Aguirre · cocina chica",
    material: "Granito Verde Ubatuba",
    m2: 3.4,
    currency: "ARS",
    amount: 286_120,
    amountSecondary: 666,
    status: "lost",
    lastActivityDays: 51,
    sentDate: "02/01",
    lostDate: "28/01",
  },
  {
    id: "PRES-2026-003",
    client: "Estudio Marini",
    clientFull: "Estudio Marini · cocina Recoleta",
    material: "Calacatta Borghini",
    m2: 7.2,
    currency: "USD",
    amount: 6_480,
    amountSecondary: null,
    status: "lost",
    lastActivityDays: 68,
    sentDate: "20/12",
    lostDate: "14/01",
  },
];

/** Counters totales · incluye perdidos antiguos no renderizados. */
export const DASHBOARD_COUNTS: DashboardCounts = {
  all: 47,
  draft: 6,
  sent: 12,
  expired: 3,
  lost: 26,
};
