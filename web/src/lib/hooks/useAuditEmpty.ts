/**
 * `useAuditEmpty(quoteId)` · Sprint 3 obs-per-row fix-up #2.
 *
 * Hook compartido que devuelve `true` cuando el snapshot del quote es vacío
 * (fallback genérico para quotes desconocidos del backend real). Usado por
 * AuditTray, IaAuditBanner y ChatAuditNote para esconder cuando no hay datos.
 *
 * Cache module-level evita N fetches paralelos cuando 3 componentes montan
 * para el mismo quoteId. El cache se rellena con la respuesta del mock —
 * Sprint 4 invalidará cuando el backend cambie el snapshot en runtime.
 *
 * Estado inicial: `null` (loading) · esconde por safety mientras carga.
 * Cuando llega el snapshot: `true`/`false` según el flag isEmpty.
 */
"use client";

import { useEffect, useState } from "react";
import { getAuditSnapshot } from "@/lib/api";

const _cache = new Map<string, boolean>();
const _inflight = new Map<string, Promise<boolean>>();

async function loadIsEmpty(quoteId: string): Promise<boolean> {
  if (_cache.has(quoteId)) return _cache.get(quoteId) as boolean;
  const existing = _inflight.get(quoteId);
  if (existing) return existing;
  const p = getAuditSnapshot(quoteId).then((snap) => {
    const isEmpty = !!snap.isEmpty;
    _cache.set(quoteId, isEmpty);
    _inflight.delete(quoteId);
    return isEmpty;
  });
  _inflight.set(quoteId, p);
  return p;
}

/** Helper para tests que quieran reset del cache entre runs. */
export function _resetAuditEmptyCache() {
  _cache.clear();
  _inflight.clear();
}

export function useAuditEmpty(quoteId: string): boolean | null {
  const [isEmpty, setIsEmpty] = useState<boolean | null>(() => {
    return _cache.has(quoteId) ? (_cache.get(quoteId) as boolean) : null;
  });

  useEffect(() => {
    if (_cache.has(quoteId)) {
      setIsEmpty(_cache.get(quoteId) as boolean);
      return;
    }
    let aborted = false;
    loadIsEmpty(quoteId)
      .then((v) => {
        if (!aborted) setIsEmpty(v);
      })
      .catch(() => {
        // En caso de error tratamos como empty (esconder por safety).
        if (!aborted) setIsEmpty(true);
      });
    return () => {
      aborted = true;
    };
  }, [quoteId]);

  return isEmpty;
}
