/**
 * Banner del estado C/D · mockup 20 (green) + mockup 21 (amber-revision).
 *
 * Variants:
 * - "green" (default · estado C): check ✓ verde · "v1 generado correctamente"
 * - "amber-revision" (estado D): check ✎ ámbar · "Revisión v2 en curso"
 *
 * Reusa `.gen-banner`, `.gen-banner.amber`, `.check`, `.gb-text/sub/spacer/meta`.
 */
"use client";

type Variant = "green" | "amber-revision";

interface Props {
  /** "green" para estado C · "amber-revision" para estado D. */
  variant?: Variant;
  /** Estado C: "Marina" · "03.05.2026 18:42" → "v1 generado correctamente". */
  generatedAtDisplay?: string;
  generatedBy?: string;
  /** Estado D · texto del banner amber (sub explicativo de revisión en curso). */
  revisionSub?: string;
  /** trace_id mostrado a la derecha (común a ambas variantes). */
  traceId: string;
}

export function PdfGenBanner({
  variant = "green",
  generatedAtDisplay,
  generatedBy,
  revisionSub,
  traceId,
}: Props) {
  const isAmber = variant === "amber-revision";
  return (
    <div
      className={`gen-banner${isAmber ? " amber" : ""}`}
      data-testid="pdf-gen-banner"
      data-variant={variant}
    >
      <div className="check" aria-hidden="true">
        {isAmber ? "✎" : "✓"}
      </div>
      <div className="gb-text">
        {isAmber ? (
          <>
            <strong>Revisión v2 en curso.</strong>
            <span className="gb-sub">
              {revisionSub ??
                "v1 sigue siendo la versión oficial · Esto es borrador editable."}
            </span>
          </>
        ) : (
          <>
            <strong>v1 generado correctamente.</strong>
            <span className="gb-sub">
              {generatedBy} · {generatedAtDisplay} · logueado en audit log
            </span>
          </>
        )}
      </div>
      <div className="gb-spacer" />
      <div className="gb-meta" data-testid="gen-banner-trace">
        {isAmber ? `v1 trace · ${traceId}` : `trace_id · ${traceId}`}
      </div>
    </div>
  );
}
