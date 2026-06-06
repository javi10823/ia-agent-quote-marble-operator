/**
 * Banner verde "v1 generado correctamente" del estado C · mockup 20 LITERAL.
 * Reusa `.gen-banner` + `.check` + `.gb-text/sub/spacer/meta` de operator-shared.css.
 */
"use client";

interface Props {
  generatedAtDisplay: string;
  generatedBy: string;
  traceId: string;
}

export function PdfGenBanner({ generatedAtDisplay, generatedBy, traceId }: Props) {
  return (
    <div className="gen-banner" data-testid="pdf-gen-banner">
      <div className="check" aria-hidden="true">
        ✓
      </div>
      <div className="gb-text">
        <strong>v1 generado correctamente.</strong>
        <span className="gb-sub">
          {generatedBy} · {generatedAtDisplay} · logueado en audit log
        </span>
      </div>
      <div className="gb-spacer" />
      <div className="gb-meta" data-testid="gen-banner-trace">
        trace_id · {traceId}
      </div>
    </div>
  );
}
