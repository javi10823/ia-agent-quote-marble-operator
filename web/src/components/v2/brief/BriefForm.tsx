/**
 * Estado B — form completo del paso 1 (mockup 00-paso1-B-subido).
 *
 * Renderiza:
 *   - hero Valentina (texto distinto: "Tengo todo lo que necesito")
 *   - dropzone `.loaded` con metadata del PDF + acciones reemplazar/quitar
 *   - textarea brief libre
 *   - PhotoUploader (hasta 5 fotos opcionales)
 *   - brief-cta con helper + botón primario "Procesar con Valentina →"
 *
 * Validaciones inline expuestas via mensaje en `.brief-cta .helper`
 * cuando `error` está seteado.
 */
"use client";

import { useState } from "react";
import { VALIDATION } from "@/lib/v2/api";
import type { BriefFormData } from "@/lib/v2/types";
import { PhotoUploader } from "./PhotoUploader";

interface Props {
  form: BriefFormData;
  onChange: (form: BriefFormData) => void;
  onSubmit: () => void;
  onResetPlan: () => void;
  error: string | null;
}

export function BriefForm({ form, onChange, onSubmit, onResetPlan, error }: Props) {
  const [localError, setLocalError] = useState<string | null>(null);
  const displayedError = error ?? localError;
  const remainingChars = VALIDATION.BRIEF_MAX_CHARS - form.briefText.length;
  const briefOver = form.briefText.length > VALIDATION.BRIEF_MAX_CHARS;
  const canSubmit = !!form.planFile && !briefOver;

  return (
    <div className="col brief-stage" data-step="brief" data-state="B">
      <div className="brief-hero">
        <div className="vbubble-lg" />
        <div className="hero-text">
          <div className="eyebrow">Paso 1 de 5 · Brief</div>
          <h2>Tengo todo lo que necesito</h2>
          <div className="lead">
            Cuando le des dale, voy a leer el plano, extraer medidas, identificar ambiente y armar
            el contexto del paso 2. Te aviso si encuentro algo raro.
          </div>
        </div>
      </div>

      {/* Dropzone .loaded con metadata del PDF */}
      {form.planFile && (
        <div className="dropzone loaded" data-testid="brief-plan-loaded" role="status">
          <div className="dz-thumb">
            <span>PDF</span>
          </div>
          <div className="dz-meta">
            <span className="name" data-testid="brief-plan-name">
              {form.planFile.name}
            </span>
            <span className="info">{formatSize(form.planFile.size)}</span>
          </div>
          <div className="dz-actions">
            <button
              type="button"
              className="dz-x destructive"
              onClick={onResetPlan}
              data-testid="brief-plan-reset"
            >
              ✕ Quitar
            </button>
          </div>
        </div>
      )}

      {/* Textarea brief libre */}
      <div className="brief-textarea-wrap">
        <span className="lbl">
          Brief libre <span style={{ color: "var(--ink-mute)" }}>· opcional</span>
        </span>
        <textarea
          data-testid="brief-text"
          placeholder="Pegá acá el WhatsApp del cliente, mensaje del estudio, mail con el pedido, lo que tengas. Yo extraigo lo importante."
          value={form.briefText}
          onChange={(e) => {
            setLocalError(null);
            onChange({ ...form, briefText: e.target.value });
          }}
          maxLength={VALIDATION.BRIEF_MAX_CHARS + 200}
          rows={6}
        />
        <span
          className="font-mono"
          style={{
            fontSize: 11,
            color: briefOver ? "var(--error)" : "var(--ink-mute)",
            display: "block",
            marginTop: 4,
          }}
          data-testid="brief-char-counter"
        >
          {remainingChars} caracteres restantes
        </span>
      </div>

      {/* Photo uploader */}
      <PhotoUploader
        photos={form.photos}
        onChange={(photos) => {
          setLocalError(null);
          onChange({ ...form, photos });
        }}
        onValidationError={setLocalError}
      />

      {/* CTA bar */}
      <div className="brief-cta">
        <span
          className="helper"
          data-testid="brief-helper"
          style={displayedError ? { color: "var(--error)" } : undefined}
        >
          {displayedError ? (
            displayedError
          ) : (
            <>
              <em>Valentina</em> tarda ~12 segundos en procesar un plano de este tamaño.
            </>
          )}
        </span>
        <button
          type="button"
          className={`btn primary${canSubmit ? "" : " disabled"}`}
          disabled={!canSubmit}
          onClick={onSubmit}
          data-testid="brief-submit"
        >
          Procesar con Valentina →
        </button>
      </div>
    </div>
  );
}

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(1).replace(".", ",")} MB`;
  const kb = bytes / 1024;
  return `${Math.round(kb)} KB`;
}
