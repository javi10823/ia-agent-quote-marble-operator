/**
 * Trazabilidad plegable del sidebar · mockup 18 LITERAL.
 * `<details class="trace-block">` con `.trace-list` (k/v pairs).
 */
"use client";

import type { PdfTrace } from "@/lib/api";

interface Props {
  trace: PdfTrace;
}

export function PdfTraceBlock({ trace }: Props) {
  return (
    <details className="trace-block" data-testid="pdf-trace-block">
      <summary>Trazabilidad</summary>
      <div className="trace-list">
        <span className="k">trace_id</span>
        <span data-testid="trace-id">{trace.traceId}</span>
        <span className="k">prompt_v</span>
        <span>{trace.promptVersion}</span>
        <span className="k">inputs_hash</span>
        <span>{trace.inputsHash}</span>
        <span className="k">snapshot</span>
        <span>{trace.snapshot}</span>
      </div>
    </details>
  );
}
