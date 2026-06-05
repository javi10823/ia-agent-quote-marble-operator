/**
 * Estado del sidebar live-edit del paso 5 PDF · Sprint 4 paso-5-pdf-preview.
 *
 * Seedea con `datosPdf` del CalculationResult + `envioSeed` derivado de
 * paso-2 (cliente+localidad). Sin persist al backend en este sub-PR
 * (decisión Javi C visual-only). Sprint 5 wirea persistencia + diff.
 *
 * Live-edit: el state controla los inputs + el PDF inline lee del mismo
 * state · cambios se reflejan instantáneo. Si user borra → quedan vacíos
 * (NO fallback a default · decisión Javi explícita).
 */
"use client";

import { useState, useCallback } from "react";

export interface PdfFormState {
  vigenciaDias: string;
  anticipoPct: string;
  plazo: string;
  envio: string;
  notas: string;
}

export interface PdfFormSeed {
  vigenciaDias?: string;
  anticipoPct?: string;
  plazo?: string;
  envio?: string;
  notas?: string;
}

export function usePdfForm(seed: PdfFormSeed = {}) {
  const [state, setState] = useState<PdfFormState>({
    vigenciaDias: seed.vigenciaDias ?? "7",
    anticipoPct: seed.anticipoPct ?? "50",
    plazo: seed.plazo ?? "30 días desde confirmación de medidas en obra.",
    envio: seed.envio ?? "",
    notas: seed.notas ?? "",
  });

  const update = useCallback(<K extends keyof PdfFormState>(key: K, value: PdfFormState[K]) => {
    setState((prev) => ({ ...prev, [key]: value }));
  }, []);

  return { state, update };
}
