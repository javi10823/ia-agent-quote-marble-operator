/**
 * Hook que coordina el state machine del paso 1 (mockups 00 A/B/C).
 *
 * Estados:
 *   - idle: estado A o B (depende de si el form tiene planFile o no,
 *     manejado por el container).
 *   - submitting: estado C (procesando) — UI muestra skeleton +
 *     status-bar + botón cancelar.
 *   - error: cancel/error de validación o fallo del mock — UI vuelve
 *     a estado B con mensaje.
 *
 * Cancelación: `cancel()` aborta el AbortController. La promise del
 * mock client rechaza con AbortError, capturado abajo, y volvemos a
 * `idle` (el container preserva el form, así que el usuario sigue
 * en estado B).
 */
"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, createDraftQuote } from "../api";
import type { BriefFormData, BriefUploadState } from "../types";

export function useBriefUpload() {
  const router = useRouter();
  const [state, setState] = useState<BriefUploadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function submit(form: BriefFormData) {
    if (!form.planFile) return;
    setState("submitting");
    setError(null);
    abortRef.current = new AbortController();

    try {
      const result = await createDraftQuote(
        {
          planFile: form.planFile,
          photos: form.photos.length > 0 ? form.photos : undefined,
          briefText: form.briefText || undefined,
        },
        { signal: abortRef.current.signal },
      );
      router.push(`/v2/quotes/${result.id}/contexto`);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // Cancelación voluntaria → vuelta a estado B (form preservado)
        setState("idle");
        return;
      }
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Error inesperado. Intentá de nuevo.");
      }
      setState("error");
    }
  }

  function cancel() {
    abortRef.current?.abort();
  }

  function reset() {
    setError(null);
    setState("idle");
  }

  return { state, error, submit, cancel, reset };
}
