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
/* Sprint 4 paso-1-real · wire del brief upload contra el backend Railway
   (POST /api/quotes → POST /api/quotes/{id}/chat con SSE drained internamente). */
export const createDraftQuote = USE_REAL_API ? real.createDraftQuote : mocks.createDraftQuote;

/* Sprint 4 paso-2-context-wire-real · wire del paso 2 contexto contra el
   backend Railway (GET /api/quotes/{id} + adapter sobre quote_breakdown).
   Cuando NEXT_PUBLIC_API_URL está definida → real client.getContextForQuote
   con bearer SSR + adapter `breakdownToContext()`. Sin env var → mock canon. */
export const getContextForQuote = USE_REAL_API ? real.getContextForQuote : mocks.getContextForQuote;

/* ─── Siempre en mock (B3 incremental · sin endpoint REST equivalente) ── */
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

/* ─── Observability · Sprint 3 observability-per-row · mockup 13 ── */
export const getAuditSnapshot = mocks.getAuditSnapshot;

/* ─── Paso 5 PDF · Sprint 4 paso-5-pdf-preview · mockup 18 ── */
export const getPdfTrace = mocks.getPdfTrace;

/* ─── Paso 5 estado C · Sprint 4 paso-5-c-generado · mockup 20
   Wire real con sub-PR paso-5-pdf-real-wire · cierra el MVP loop. */
export const triggerPdfGeneration = USE_REAL_API
  ? real.triggerPdfGeneration
  : mocks.triggerPdfGeneration;
export const getPdfGeneratedInfo = USE_REAL_API
  ? real.getPdfGeneratedInfo
  : mocks.getPdfGeneratedInfo;

/* ─── Paso 5 estado D · Sprint 4 paso-5-d-revision-v2 · mockup 21
   `triggerPdfV2Generation` wirea contra POST /quotes/{id}/regenerate.
   `getPdfV2DiffData` SIGUE en mock · backend no expone diff v1 vs v2
   todavía (sub-PR posterior `paso-5-v2-diff-real`). */
export const getPdfV2DiffData = mocks.getPdfV2DiffData;
export const triggerPdfV2Generation = USE_REAL_API
  ? real.triggerPdfV2Generation
  : mocks.triggerPdfV2Generation;

/* ─── Audit trail copy · Sprint 4 audit-trail-copy ────────────────── */
export const getAuditLog = USE_REAL_API ? real.getAuditLog : mocks.getAuditLog;

/* ─── Catálogo · viewer + Dux importer + backups · sub-PR 22.2.b ───
   Los 8 endpoints catalog mapean limpio a REST → wire real con el flag
   activo · mocks deterministas en CI/dev. */
export const listCatalogs = USE_REAL_API ? real.listCatalogs : mocks.listCatalogs;
export const getCatalog = USE_REAL_API ? real.getCatalog : mocks.getCatalog;
export const listBackups = USE_REAL_API ? real.listBackups : mocks.listBackups;
export const restoreBackup = USE_REAL_API ? real.restoreBackup : mocks.restoreBackup;
export const importPreview = USE_REAL_API ? real.importPreview : mocks.importPreview;
export const importApply = USE_REAL_API ? real.importApply : mocks.importApply;

/* ─── Catalog config · sub-PR 22.2.a config-ui-page ──────────────── */
export const getCatalogConfig = USE_REAL_API ? real.getCatalogConfig : mocks.getCatalogConfig;
export const updateCatalogConfig = USE_REAL_API
  ? real.updateCatalogConfig
  : mocks.updateCatalogConfig;
export const _resetCatalogConfigStore = mocks._resetCatalogConfigStore;

/* ─── Helpers de test (reset de stores in-memory del mock) ───────── */
export const _resetContextStore = mocks._resetContextStore;
export const _resetPiecesStore = mocks._resetPiecesStore;
export const _resetCalcStore = mocks._resetCalcStore;
export const _resetGeneratedStore = mocks._resetGeneratedStore;

/* ─── Tipos + helpers puros + constantes ─────────────────────────── */
export * from "./types";
