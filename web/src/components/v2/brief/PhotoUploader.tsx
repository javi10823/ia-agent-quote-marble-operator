/**
 * Sub-componente del estado B — uploader de hasta 5 fotos opcionales.
 *
 * Reusa clases legacy `.img-row`, `.img-thumb`, `.x-btn` y
 * `.img-thumb.placeholder` de operator-shared.css. Validaciones de
 * tipo/tamaño/cantidad se exponen via onValidationError.
 */
"use client";

import { useDropzone, type FileRejection } from "react-dropzone";
import { VALIDATION } from "@/lib/v2/api";

interface Props {
  photos: File[];
  onChange: (photos: File[]) => void;
  onValidationError?: (message: string) => void;
}

export function PhotoUploader({ photos, onChange, onValidationError }: Props) {
  const remaining = VALIDATION.PHOTOS_MAX_COUNT - photos.length;

  const { getRootProps, getInputProps } = useDropzone({
    accept: { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"] },
    maxSize: VALIDATION.PHOTO_MAX_BYTES,
    maxFiles: remaining,
    multiple: true,
    disabled: remaining <= 0,
    onDrop: (accepted, rejected) => {
      if (rejected.length > 0 && onValidationError) {
        onValidationError(mapRejection(rejected[0]));
      }
      if (accepted.length === 0) return;
      const next = [...photos, ...accepted].slice(0, VALIDATION.PHOTOS_MAX_COUNT);
      onChange(next);
    },
  });

  function removeAt(index: number) {
    onChange(photos.filter((_, i) => i !== index));
  }

  return (
    <div className="brief-textarea-wrap">
      <span className="lbl">Fotos del lugar · opcional (hasta {VALIDATION.PHOTOS_MAX_COUNT})</span>
      <div className="img-row" data-testid="photo-row">
        {photos.map((photo, i) => (
          <div key={`${photo.name}-${i}`} className="img-thumb">
            <span data-testid="photo-name">{photo.name}</span>
            <button
              type="button"
              className="x-btn"
              aria-label={`quitar ${photo.name}`}
              onClick={() => removeAt(i)}
            >
              ✕
            </button>
          </div>
        ))}
        {remaining > 0 && (
          <div
            {...getRootProps()}
            className="img-thumb placeholder"
            data-testid="photo-placeholder"
            role="button"
            tabIndex={0}
          >
            <input {...getInputProps()} data-testid="photo-input" />+
          </div>
        )}
      </div>
    </div>
  );
}

function mapRejection(rejection: FileRejection): string {
  const code = rejection.errors[0]?.code;
  if (code === "file-invalid-type") return "Las fotos deben ser JPG o PNG";
  if (code === "file-too-large") return "Cada foto debe ser menor a 5 MB";
  if (code === "too-many-files") return "Máximo 5 fotos";
  return rejection.errors[0]?.message ?? "Foto inválida";
}
