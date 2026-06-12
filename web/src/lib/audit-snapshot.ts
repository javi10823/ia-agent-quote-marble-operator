/**
 * Registry module-level del snapshot de UI del paso actual del wizard ·
 * Sprint 4 audit-copy-3-layer-state.
 *
 * Bridge entre la página del paso (que tiene el `ContextResponse` del adapter
 * + el UI state, client-side) y el `AuditCopyButton` (que vive en el Topbar,
 * un árbol de componentes separado bajo `[id]/layout`). Sigue el patrón de
 * `useAuditMode`: estado module-level, sin Zustand/Redux/Context.
 *
 * Caveat anti-stale (decisión Javi): el registry guarda `{ quoteId, snapshot }`.
 * `getSnapshot(currentQuoteId)` devuelve el snapshot SOLO si el quoteId pedido
 * matchea el registrado. Si navegaste a otro quote y la página vieja todavía
 * no desregistró (unmount tardío), `getSnapshot(nuevoId)` devuelve `null` →
 * el audit copy omite las 2 secciones nuevas (backward compat · silent fail).
 */
import type { ContextResponse } from "./api/types";

/** Un field tal como lo muestra la UI (value formateado + chip origin). */
export interface AuditUiRenderField {
  label: string;
  /** Texto exacto que renderea ContextField (`value ?? "—"`, bool → "Sí"/"No"). */
  displayValue: string;
  /** Chip de origen ("BRIEF" | "INFERIDO" | "DEFAULT" | "EDITADO" | "FALTA"). */
  origin: string;
}

/** Una sección del form (Cliente / Proyecto / Detalles) con sus fields. */
export interface AuditUiRenderSection {
  title: string;
  fields: AuditUiRenderField[];
}

/** Snapshot 3-capa del paso actual · capa adapter + capa UI render. */
export interface AuditSnapshot {
  /** Ruta del paso que registró el snapshot (ej. "/contexto"). */
  step: string;
  /** Output del adapter (lo que `getContextForQuote` devolvió). */
  contextResponse: ContextResponse | null;
  /** Lo que la UI efectivamente muestra · null si el paso no lo expone. */
  uiRender: AuditUiRenderSection[] | null;
}

let _state: { quoteId: string | null; snapshot: AuditSnapshot | null } = {
  quoteId: null,
  snapshot: null,
};

/** Registra (o reemplaza) el snapshot del quote activo. */
export function registerSnapshot(quoteId: string, snapshot: AuditSnapshot): void {
  _state = { quoteId, snapshot };
}

/**
 * Desregistra el snapshot. Solo limpia si el quoteId que desregistra es el
 * que está activo — así un unmount tardío de la página vieja NO borra el
 * snapshot que la página nueva ya registró.
 */
export function unregisterSnapshot(quoteId: string): void {
  if (_state.quoteId === quoteId) {
    _state = { quoteId: null, snapshot: null };
  }
}

/** Devuelve el snapshot solo si matchea el quote pedido (anti-stale). */
export function getSnapshot(quoteId: string): AuditSnapshot | null {
  if (!quoteId || _state.quoteId !== quoteId) return null;
  return _state.snapshot;
}

/** Helper de test · resetea el registry. NO usar en runtime. */
export function _resetSnapshotRegistry(): void {
  _state = { quoteId: null, snapshot: null };
}
