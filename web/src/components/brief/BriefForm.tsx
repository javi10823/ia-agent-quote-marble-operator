/**
 * Paso 1 brief form · Sprint 4 paso-1-chips-brief-libre · LITERAL mockups
 * oficiales `00-paso1-A-vacio.html` y `00-paso1-B-subido.html`.
 *
 * Sprint 4 (este sub-PR): el componente cubre estados A (vacío) y B
 * (PDF subido) en un único render con la misma estructura:
 *   1. `.brief-hero` con eyebrow + h2 + lead (copy difiere A vs B)
 *   2. `.brief-chips` con 3 inputs (Cliente / Ambiente / Plazo) opcionales
 *   3. `.brief-textarea-wrap` con "Brief libre" (label dinámico en B)
 *   4. `.dropzone` vacío en A o `.dropzone.loaded` con metadata en B
 *   5. PhotoUploader (solo cuando hay planFile cargado · estado B)
 *   6. `.brief-cta` con helper dinámico + buttons (ghost manual + primary)
 *
 * CTA habilita con `planFile || briefText.length >= 50 || (cliente && ambiente)`.
 * Helper dinámico 3-way según el estado del form:
 *   · vacío → LITERAL del mockup A: "Necesito al menos el plano..."
 *   · sin plan AND (textarea ≥50 OR chips llenos) → "Sin plano voy a..."
 *   · planFile presente → LITERAL del mockup B: "Valentina tarda ~12 segundos..."
 *
 * Chips `.from-ia` + `.ia-mark`: visual-only en este sub-PR · NO se activa
 * hoy (esperando wire SSE de extracción en vivo del sub-PR `paso-1-sse-stream`).
 *
 * Reusa clases legacy `.brief-hero`, `.brief-chips`, `.brief-chip`,
 * `.brief-textarea-wrap`, `.dropzone[.loaded]`, `.brief-cta`, `.dz-*`, `.lbl`,
 * `.link-inline`, `.eyebrow`, `.lead`, `.vbubble-lg`, `.hero-text`. Cero
 * cambios a `operator-shared.css`.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { VALIDATION } from "@/lib/api";
import type { BriefFormData } from "@/lib/types";
import { PhotoUploader } from "./PhotoUploader";

interface Props {
  form: BriefFormData;
  onChange: (form: BriefFormData) => void;
  /** Submit principal · click "Procesar con Valentina →". */
  onSubmit: () => void;
  /** Submit "Cargar a mano →" del mockup · crea draft sin plan + redirect. */
  onSubmitManual: () => void;
  /** Click "✕ Quitar" del dropzone.loaded · pide confirm() destructivo. */
  onResetPlan: () => void;
  /** Validation errors del dropzone PDF + photos. */
  onValidationError: (msg: string | null) => void;
  /** Error post-submit del hook (createDraftQuote). */
  submitError: string | null;
  /** Error inline del drop de PDF (size/mime). */
  dropzoneError: string | null;
}

export function BriefForm({
  form,
  onChange,
  onSubmit,
  onSubmitManual,
  onResetPlan,
  onValidationError,
  submitError,
  dropzoneError,
}: Props) {
  const [localError, setLocalError] = useState<string | null>(null);
  const displayedError = submitError ?? dropzoneError ?? localError;
  const briefLen = form.briefText.length;
  const briefOver = briefLen > VALIDATION.BRIEF_MAX_CHARS;
  const remainingChars = VALIDATION.BRIEF_MAX_CHARS - briefLen;
  const hasChips = !!form.cliente.trim() && !!form.ambiente.trim();
  const hasMinBrief = briefLen >= 50;
  // Sprint 4 paso-1-chips-brief-libre: divergencia documentada · CTA habilita
  // con planFile || briefText≥50 || (cliente+ambiente). Patrón Master § 4:
  // "IA propone, humano decide" cubre el text-only flow.
  const canSubmit = !briefOver && (!!form.planFile || hasMinBrief || hasChips);

  // Estado A (vacío) vs B (PDF subido)
  const isStateB = !!form.planFile;

  // dz-meta info dinámica: "{N,N} MB · subido a las {hh:mm}". La hora se
  // calcula client-side al settear el plan · evita drift entre renders.
  const [planLoadedAt, setPlanLoadedAt] = useState<string>("");
  const planNameRef = useRef<string | null>(null);
  useEffect(() => {
    if (form.planFile && form.planFile.name !== planNameRef.current) {
      const now = new Date();
      const hh = String(now.getHours()).padStart(2, "0");
      const mm = String(now.getMinutes()).padStart(2, "0");
      setPlanLoadedAt(`${hh}:${mm}`);
      planNameRef.current = form.planFile.name;
    } else if (!form.planFile) {
      planNameRef.current = null;
      setPlanLoadedAt("");
    }
  }, [form.planFile]);

  // Helper dinámico 3-way (item 17 del bundle FASE 1)
  let helperContent: React.ReactNode;
  if (form.planFile) {
    helperContent = (
      <>
        <em>Valentina</em> tarda ~12 segundos en procesar un plano de este tamaño.
      </>
    );
  } else if (hasMinBrief || hasChips) {
    helperContent = "Sin plano voy a intentar igual pero será aproximado.";
  } else {
    helperContent = (
      <>
        Necesito al menos el <em>plano en PDF</em> para arrancar. ¿No tenés?{" "}
        <a
          href="#"
          className="link-inline"
          onClick={(e) => {
            e.preventDefault();
            onSubmitManual();
          }}
          data-testid="brief-manual-helper-link"
        >
          cargá a mano →
        </a>
      </>
    );
  }

  // Dropzone PDF (estado A) — react-dropzone hidden input
  const { getRootProps, getInputProps, isDragActive, open: openFilePicker } = useDropzone({
    accept: { "application/pdf": [".pdf"] },
    maxSize: VALIDATION.PLAN_MAX_BYTES,
    maxFiles: 1,
    multiple: false,
    noClick: isStateB, // en estado B el dropzone se vuelve "loaded" card · botón "Reemplazar" abre file picker manualmente
    noKeyboard: isStateB,
    onDrop: (accepted, rejected) => {
      if (rejected.length > 0) {
        onValidationError(mapPdfRejection(rejected[0]));
        return;
      }
      if (accepted[0]) {
        onValidationError(null);
        onChange({ ...form, planFile: accepted[0] });
      }
    },
  });

  function handleResetPlan() {
    // confirm() literal del title del mockup B
    if (
      typeof window !== "undefined" &&
      window.confirm("¿Quitar el PDF? Se perderá lo extraído por Valentina.")
    ) {
      onResetPlan();
    }
  }

  return (
    <div className="col brief-stage" data-step="brief" data-state={isStateB ? "B" : "A"}>
      {/* ─── Hero ───────────────────────────────────────────── */}
      <div className="brief-hero">
        <div className="vbubble-lg" />
        <div className="hero-text">
          <div className="eyebrow">Paso 1 de 5 · Brief</div>
          <h2>{isStateB ? "Tengo todo lo que necesito" : "Subí lo que tengas y arranco"}</h2>
          <div className="lead">
            {isStateB ? (
              "Cuando le des dale, voy a leer el plano, extraer medidas, identificar ambiente y armar el contexto del paso 2. Te aviso si encuentro algo raro."
            ) : (
              <>
                Soy <em>Valentina</em>. Si me das el plano y un brief — aunque sea informal —
                extraigo cliente, ambiente, medidas, material y armo el contexto del paso 2 sola.
                <br />
                <br />
                ¿No tenés plano todavía?{" "}
                <a
                  href="#"
                  className="link-inline"
                  onClick={(e) => {
                    e.preventDefault();
                    onSubmitManual();
                  }}
                  data-testid="brief-manual-hero-link"
                >
                  cargá a mano →
                </a>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ─── Brief chips (Cliente / Ambiente / Plazo) ──────── */}
      <div className="brief-chips" data-testid="brief-chips">
        <BriefChip
          label="Cliente"
          value={form.cliente}
          placeholder="opcional · ej. Cueto-Heredia"
          fromIa={false}
          onChange={(v) => onChange({ ...form, cliente: v })}
          testId="brief-chip-cliente"
        />
        <BriefChip
          label="Ambiente"
          value={form.ambiente}
          placeholder="opcional · ej. cocina"
          fromIa={false}
          onChange={(v) => onChange({ ...form, ambiente: v })}
          testId="brief-chip-ambiente"
        />
        <BriefChip
          label="Plazo"
          value={form.plazo}
          placeholder="opcional · ej. 3 semanas"
          fromIa={false}
          onChange={(v) => onChange({ ...form, plazo: v })}
          testId="brief-chip-plazo"
        />
      </div>

      {/* ─── Brief libre textarea ─────────────────────────── */}
      <div className="brief-textarea-wrap">
        <span className="lbl">
          {isStateB && planLoadedAt
            ? `Brief libre · WhatsApp del estudio (${planLoadedAt})`
            : "Brief libre"}
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

      {/* ─── Dropzone (vacío en A · .loaded en B) ─────────── */}
      {isStateB ? (
        <div
          className="dropzone loaded"
          data-testid="brief-plan-loaded"
          role="status"
          {...getRootProps()}
        >
          {/* Hidden input siempre montado · reusado por "Reemplazar" */}
          <input {...getInputProps()} data-testid="brief-dropzone-input" />
          <div className="dz-thumb">
            <span>PDF</span>
          </div>
          <div className="dz-meta">
            <span className="name" data-testid="brief-plan-name">
              {form.planFile!.name}
            </span>
            <span className="info">{formatSize(form.planFile!.size)}{planLoadedAt ? ` · subido a las ${planLoadedAt}` : ""}</span>
          </div>
          <div className="dz-actions">
            <button
              type="button"
              className="dz-x"
              onClick={(e) => {
                e.stopPropagation();
                openFilePicker();
              }}
              data-testid="brief-plan-replace"
            >
              Reemplazar
            </button>
            <span className="dz-sep" />
            <button
              type="button"
              className="dz-x destructive"
              onClick={(e) => {
                e.stopPropagation();
                handleResetPlan();
              }}
              title="Pide confirmación: '¿Quitar el PDF? Se perderá lo extraído por Valentina.'"
              data-testid="brief-plan-reset"
            >
              ✕ Quitar
            </button>
          </div>
        </div>
      ) : (
        <div
          {...getRootProps()}
          className={`dropzone ${isDragActive ? "is-dragging" : ""}`}
          data-testid="brief-dropzone"
        >
          <input {...getInputProps()} data-testid="brief-dropzone-input" />
          <div className="dz-icon">↑</div>
          <div className="dz-title">
            {isDragActive ? "Soltá el plano acá" : "Arrastrá el plano (PDF) o hacé click para elegir"}
          </div>
          <div className="dz-sub">
            PDF · máx. 10 MB · podés sumar hasta 5 fotos del lugar después
          </div>
        </div>
      )}

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

      {/* ─── Photo uploader (solo en estado B) ────────────── */}
      {isStateB && (
        <PhotoUploader
          photos={form.photos}
          onChange={(photos) => {
            setLocalError(null);
            onChange({ ...form, photos });
          }}
          onValidationError={setLocalError}
        />
      )}

      {/* ─── CTA bar ──────────────────────────────────────── */}
      <div className="brief-cta">
        <span
          className="helper"
          data-testid="brief-helper"
          style={displayedError ? { color: "var(--error)" } : undefined}
        >
          {displayedError ?? helperContent}
        </span>
        <button
          type="button"
          className="btn ghost"
          onClick={onSubmitManual}
          data-testid="brief-submit-manual"
        >
          Cargar a mano →
        </button>
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

/* ─── Sub-componente `.brief-chip` · LITERAL del mockup ─────────────── */

interface BriefChipProps {
  label: string;
  value: string;
  placeholder: string;
  /** true cuando el valor fue precargado por Valentina · activa `.from-ia` +
   * `.ia-mark` con `title` LITERAL del mockup. Visual-only en este sub-PR
   * (esperando wire SSE del `paso-1-sse-stream`). */
  fromIa: boolean;
  onChange: (v: string) => void;
  testId: string;
}

function BriefChip({ label, value, placeholder, fromIa, onChange, testId }: BriefChipProps) {
  return (
    <div className={`brief-chip${fromIa ? " from-ia" : ""}`} data-testid={testId}>
      <span className="lbl">{label}</span>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        data-testid={`${testId}-input`}
      />
      {fromIa && (
        <span className="ia-mark" title="Extraído del WhatsApp por Valentina">
          IA
        </span>
      )}
    </div>
  );
}

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(1).replace(".", ",")} MB`;
  const kb = bytes / 1024;
  return `${Math.round(kb)} KB`;
}

function mapPdfRejection(rejection: FileRejection): string {
  const code = rejection.errors[0]?.code;
  if (code === "file-invalid-type") return "El plan debe ser un PDF";
  if (code === "file-too-large") return "El plan supera 10 MB";
  if (code === "too-many-files") return "Solo se acepta un plano (el primer PDF)";
  return rejection.errors[0]?.message ?? "Archivo inválido";
}
