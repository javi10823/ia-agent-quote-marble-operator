/**
 * Container del paso 1 — coordina los 3 estados visuales (A/B/C).
 *
 * Stateflow:
 *   - sin planFile → estado A (BriefDropzone)
 *   - con planFile, hook idle/error → estado B (BriefForm)
 *   - hook submitting → estado C (BriefProcessing)
 *
 * Decisión: el form (planFile + photos + briefText) vive en este
 * container, NO en el hook. Así sobrevive al ciclo cancel→retry sin
 * perder lo que el usuario tipeó. El hook solo coordina submit/cancel/
 * navigation.
 */
"use client";

import { useState } from "react";
import type { BriefFormData } from "@/lib/types";
import { useBriefUpload } from "@/lib/hooks/useBriefUpload";
import { BriefForm } from "./BriefForm";
import { BriefProcessing } from "./BriefProcessing";

const EMPTY_FORM: BriefFormData = {
  planFile: null,
  photos: [],
  briefText: "",
  cliente: "",
  ambiente: "",
  plazo: "",
};

export function BriefView() {
  const { state, error, submit, submitManual, cancel } = useBriefUpload();
  const [form, setForm] = useState<BriefFormData>(EMPTY_FORM);
  const [dropzoneError, setDropzoneError] = useState<string | null>(null);

  if (state === "submitting") {
    return <BriefProcessing onCancel={cancel} planName={form.planFile?.name} />;
  }

  // Sprint 4 paso-1-chips-brief-libre: el form (chips + brief + plan + fotos)
  // siempre se renderea en BriefForm. Antes el switch A↔B dependía de
  // `form.planFile` pero el mockup oficial pide chips + brief libre +
  // dropzone juntos en ambos estados. Diferencia A vs B = lead + tagline
  // + dropzone vacío vs `.loaded`. BriefForm cubre ambos sin componente
  // separado.
  return (
    <BriefForm
      form={form}
      onChange={setForm}
      onSubmit={() => submit(form)}
      onSubmitManual={() => submitManual()}
      onResetPlan={() => setForm({ ...form, planFile: null })}
      onValidationError={setDropzoneError}
      submitError={error}
      dropzoneError={dropzoneError}
    />
  );
}
