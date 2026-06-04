/**
 * Hook del paso 4 · Cálculo. Mocks-first (Sprint 4 wire chat-driven).
 *
 * Carga `getCalculationForQuote` al mount + expone recalc + auto-fix
 * (estado B) + toggles UI (audit/iva/tipoCliente). Fallback gracioso
 * para IDs desconocidos en mocks.ts (sin crash).
 *
 * Toggles SON visual-only en este PR (no afectan cifras — decisión Javi
 * #2/#3). Sprint 4 los conecta al recompute.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  applyAutoFix,
  getCalculationForQuote,
  triggerCalculation,
  type CalcToggles,
  type CalculationResult,
} from "../api";

type State = "loading" | "ok" | "error";

export function useCalculo(quoteId: string) {
  const [data, setData] = useState<CalculationResult | null>(null);
  const [state, setState] = useState<State>("loading");
  const [error, setError] = useState<string | null>(null);
  const [toggles, setToggles] = useState<CalcToggles>({
    // Sprint 3 obs-per-row fix-up #1: `auditOn` removido del state local
    // (ahora vive en useAuditMode global · TopBar).
    ivaVisible: true,
    tipoCliente: "particular",
  });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let aborted = false;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setState("loading");
    getCalculationForQuote(quoteId, { signal: ctrl.signal })
      .then((r) => {
        if (aborted) return;
        setData(r);
        setState(r.status === "error" ? "error" : "ok");
      })
      .catch((err) => {
        if (aborted || (err instanceof DOMException && err.name === "AbortError")) return;
        setError(err instanceof Error ? err.message : "Error al cargar el cálculo");
        setState("error");
      });
    return () => {
      aborted = true;
      ctrl.abort();
    };
  }, [quoteId]);

  const recalculate = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setState("loading");
    try {
      const r = await triggerCalculation(quoteId, { signal: ctrl.signal });
      setData(r);
      setState(r.status === "error" ? "error" : "ok");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Error al recalcular");
      setState("error");
    }
  }, [quoteId]);

  const applyFix = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setState("loading");
    try {
      const r = await applyAutoFix(quoteId, { signal: ctrl.signal });
      setData(r);
      setState("ok");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Error al aplicar fix");
      setState("error");
    }
  }, [quoteId]);

  const setToggle = useCallback(<K extends keyof CalcToggles>(key: K, value: CalcToggles[K]) => {
    setToggles((prev) => ({ ...prev, [key]: value }));
  }, []);

  return { data, state, error, toggles, recalculate, applyFix, setToggle };
}
