/**
 * Selector del client v2 · Sprint 3 api-integration · B3 incremental.
 *
 * Feature flag `NEXT_PUBLIC_API_URL`: si está definida → las 3 funciones
 * wireadas usan el backend real; si no → mocks (default CI + dev local).
 *
 * B3 incremental: solo streamChat + listQuotes + getQuoteMetadata mapean
 * limpio a endpoints REST. createDraftQuote + las 6 sin endpoint quedan
 * SIEMPRE en mock (ver docs/known-issues.md · Sprint 4 las resuelve).
 *
 * El resto del frontend importa `from "@/lib/api"` sin enterarse del switch.
 */
import * as mocks from "./mocks";
import * as real from "./real";

const USE_REAL_API =
  !!process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL.length > 0;

/* ─── Wireadas contra real cuando el flag está activo ────────────── */
export const streamChat = USE_REAL_API ? real.streamChat : mocks.streamChat;
export const listQuotes = USE_REAL_API ? real.listQuotes : mocks.listQuotes;
export const getQuoteMetadata = USE_REAL_API ? real.getQuoteMetadata : mocks.getQuoteMetadata;

/* ─── Siempre en mock (B3 incremental · sin endpoint REST equivalente) ── */
export const createDraftQuote = mocks.createDraftQuote;
export const getContextForQuote = mocks.getContextForQuote;
export const updateContextForQuote = mocks.updateContextForQuote;
export const getDashboardKpis = mocks.getDashboardKpis;
export const getValentinaBriefSummary = mocks.getValentinaBriefSummary;
export const listPiecesForQuote = mocks.listPiecesForQuote;
export const updatePieceForQuote = mocks.updatePieceForQuote;
export const addPieceForQuote = mocks.addPieceForQuote;
export const deletePieceForQuote = mocks.deletePieceForQuote;
export const regenerateDespiece = mocks.regenerateDespiece;

/* ─── Cálculo (paso 4 · siempre mock · Sprint 4 wire chat-driven) ── */
export const getCalculationForQuote = mocks.getCalculationForQuote;
export const triggerCalculation = mocks.triggerCalculation;
export const applyAutoFix = mocks.applyAutoFix;

/* ─── Helpers de test (reset de stores in-memory del mock) ───────── */
export const _resetContextStore = mocks._resetContextStore;
export const _resetPiecesStore = mocks._resetPiecesStore;
export const _resetCalcStore = mocks._resetCalcStore;

/* ─── Tipos + helpers puros + constantes ─────────────────────────── */
export * from "./types";
