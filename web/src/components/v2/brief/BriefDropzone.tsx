/**
 * Estado A — dropzone vacío del paso 1.
 *
 * Renderiza el hero Valentina (`.brief-hero` + `.vbubble-lg`) +
 * dropzone PDF (`.dropzone` con clases legacy de operator-shared.css).
 * Reusa react-dropzone para drag-and-drop.
 *
 * Validaciones inline: si el usuario suelta múltiples archivos, solo
 * el primer PDF se acepta. Errores de tipo/tamaño se exponen al
 * container via onValidationError.
 */
"use client";

import { useDropzone, type FileRejection } from "react-dropzone";
import { VALIDATION } from "@/lib/v2/api";

interface Props {
  onFile: (file: File) => void;
  onValidationError?: (message: string) => void;
}

export function BriefDropzone({ onFile, onValidationError }: Props) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { "application/pdf": [".pdf"] },
    maxSize: VALIDATION.PLAN_MAX_BYTES,
    maxFiles: 1,
    multiple: false,
    onDrop: (accepted, rejected) => {
      if (rejected.length > 0 && onValidationError) {
        const msg = mapRejection(rejected[0]);
        onValidationError(msg);
        return;
      }
      if (accepted[0]) onFile(accepted[0]);
    },
  });

  return (
    <div className="col brief-stage" data-step="brief" data-state="A">
      <div className="brief-hero">
        <div className="vbubble-lg" />
        <div className="hero-text">
          <div className="eyebrow">Paso 1 de 5 · Brief</div>
          <h2>Subí lo que tengas y arranco</h2>
          <div className="lead">
            Soy <em>Valentina</em>. Si me das el plano y un brief — aunque sea informal — extraigo
            cliente, ambiente, medidas, material y armo el contexto del paso 2 sola.
          </div>
        </div>
      </div>

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
        <div className="dz-sub">PDF · máx. 20 MB · podés sumar hasta 5 fotos del lugar después</div>
      </div>
    </div>
  );
}

function mapRejection(rejection: FileRejection): string {
  const code = rejection.errors[0]?.code;
  if (code === "file-invalid-type") return "El plan debe ser un PDF";
  if (code === "file-too-large") return "El plan supera 20 MB";
  if (code === "too-many-files") return "Solo se acepta un plano (el primer PDF)";
  return rejection.errors[0]?.message ?? "Archivo inválido";
}
