/**
 * Hook que gestiona el form del paso 2 (contexto):
 *   - load inicial via getContextForQuote
 *   - updateField parcial via updateContextForQuote
 *   - flag isDirty (algún field tiene `edited: true`)
 *   - estado loading | idle | saving | error
 *
 * Cancela cualquier load/save pendiente al desmontar (AbortController).
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getContextForQuote,
  updateContextForQuote,
  type ContextData,
  type ContextResponse,
} from "../api";
import type { ContextFormState } from "../types";

export function useContextForm(quoteId: string) {
  const [context, setContext] = useState<ContextResponse | null>(null);
  const [state, setState] = useState<ContextFormState>("loading");
  const [error, setError] = useState<string | null>(null);
  const saveAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let aborted = false;
    const ctrl = new AbortController();
    setState("loading");
    setError(null);
    getContextForQuote(quoteId, { signal: ctrl.signal })
      .then((data) => {
        if (aborted) return;
        setContext(data);
        setState("idle");
      })
      .catch((err) => {
        if (aborted || (err instanceof DOMException && err.name === "AbortError")) {
          return;
        }
        setError(err instanceof Error ? err.message : "Error al cargar el contexto");
        setState("error");
      });
    return () => {
      aborted = true;
      ctrl.abort();
    };
  }, [quoteId]);

  const updateField = useCallback(
    async <K extends keyof ContextData>(key: K, value: ContextData[K]) => {
      saveAbortRef.current?.abort();
      const ctrl = new AbortController();
      saveAbortRef.current = ctrl;
      setState("saving");
      setError(null);
      try {
        const updated = await updateContextForQuote(
          quoteId,
          { [key]: value } as Partial<ContextData>,
          { signal: ctrl.signal },
        );
        setContext(updated);
        setState("idle");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Error al guardar");
        setState("error");
      }
    },
    [quoteId],
  );

  const isDirty = context ? Object.values(context).some((f) => f.edited === true) : false;
  const editedCount = context ? Object.values(context).filter((f) => f.edited === true).length : 0;

  return { context, state, error, updateField, isDirty, editedCount };
}
