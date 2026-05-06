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
import type { BriefFormData } from "@/lib/v2/types";
import { useBriefUpload } from "@/lib/v2/hooks/useBriefUpload";
import { BriefDropzone } from "./BriefDropzone";
import { BriefForm } from "./BriefForm";
import { BriefProcessing } from "./BriefProcessing";

const EMPTY_FORM: BriefFormData = {
  planFile: null,
  photos: [],
  briefText: "",
};

export function BriefView() {
  const { state, error, submit, cancel } = useBriefUpload();
  const [form, setForm] = useState<BriefFormData>(EMPTY_FORM);
  const [dropzoneError, setDropzoneError] = useState<string | null>(null);

  if (state === "submitting") {
    return <BriefProcessing onCancel={cancel} planName={form.planFile?.name} />;
  }

  if (form.planFile) {
    return (
      <BriefForm
        form={form}
        onChange={setForm}
        onSubmit={() => submit(form)}
        onResetPlan={() => setForm({ ...form, planFile: null })}
        error={error}
      />
    );
  }

  return (
    <>
      <BriefDropzone
        onFile={(file) => {
          setDropzoneError(null);
          setForm({ ...form, planFile: file });
        }}
        onValidationError={setDropzoneError}
      />
      {dropzoneError && (
        <p
          data-testid="brief-dropzone-error"
          className="font-mono"
          style={{
            color: "var(--error)",
            fontSize: 12,
            marginTop: 12,
            paddingLeft: 4,
          }}
        >
          {dropzoneError}
        </p>
      )}
    </>
  );
}
