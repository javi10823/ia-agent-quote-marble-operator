/**
 * Audit-tray banner top global · mockup 13.
 *
 * Visible solo cuando `body[data-audit="on"]`. 3 columnas mono-font con
 * metadata IA (model/tokens/latency), trazabilidad (trace_id/prompt_v/temp/
 * cache) y eventos en sesión (timestamp+name+detail).
 *
 * Mock-only · datos via getAuditSnapshot con fallback gracioso a em-dash
 * para IDs desconocidos (decisión Javi D). Tree view del trace_id queda
 * disabled con TODO Sprint 4 (decisión Javi G).
 */
"use client";

import { useEffect, useState } from "react";
import type { AuditSnapshot } from "@/lib/api";
import { getAuditSnapshot } from "@/lib/api";
import { useAuditMode } from "@/lib/hooks/useAuditMode";

interface Props {
  quoteId: string;
}

export function AuditTray({ quoteId }: Props) {
  const { auditOn } = useAuditMode();
  const [snapshot, setSnapshot] = useState<AuditSnapshot | null>(null);

  useEffect(() => {
    if (!auditOn) return;
    let aborted = false;
    const ctrl = new AbortController();
    getAuditSnapshot(quoteId, { signal: ctrl.signal })
      .then((s) => {
        if (!aborted) setSnapshot(s);
      })
      .catch(() => {
        // Fallback gracioso ya está en el mock · si igual rompe, no mostrar tray.
      });
    return () => {
      aborted = true;
      ctrl.abort();
    };
  }, [auditOn, quoteId]);

  if (!auditOn || !snapshot) return null;

  return (
    <div className="audit-tray" data-testid="audit-tray">
      <div className="col">
        <h4>· Última llamada IA</h4>
        <div className="kv">
          <span className="k">model</span>
          <span className="v">{snapshot.lastCall.model}</span>
        </div>
        <div className="kv">
          <span className="k">scope</span>
          <span className="v">{snapshot.lastCall.scope}</span>
        </div>
        <div className="kv">
          <span className="k">tokens</span>
          <span className="v">
            in {snapshot.lastCall.tokensIn.toLocaleString("es-AR")} · out{" "}
            {snapshot.lastCall.tokensOut.toLocaleString("es-AR")}
          </span>
        </div>
        <div className="kv">
          <span className="k">latency</span>
          <span className="v">{(snapshot.lastCall.latencyMs / 1000).toFixed(1)}s</span>
        </div>
      </div>
      <div className="col">
        <h4>· Trazabilidad</h4>
        <div className="kv">
          <span className="k">trace_id</span>
          <span className="v">
            {snapshot.trace.traceId} ·{" "}
            <a
              href="#"
              aria-disabled="true"
              title="ver tree — Sprint 4 (versioning + drawer)"
              onClick={(e) => e.preventDefault()}
              data-testid="trace-tree-disabled"
              style={{ opacity: 0.55, cursor: "not-allowed" }}
            >
              ver tree
            </a>
          </span>
        </div>
        <div className="kv">
          <span className="k">prompt_v</span>
          <span className="v">{snapshot.trace.promptVersion}</span>
        </div>
        <div className="kv">
          <span className="k">temp</span>
          <span className="v">{snapshot.trace.temperature}</span>
        </div>
        <div className="kv">
          <span className="k">cache</span>
          <span className="v">prompt cache hit ({snapshot.trace.cacheHitPct}%)</span>
        </div>
      </div>
      <div className="col">
        <h4>· Eventos en sesión</h4>
        {snapshot.events.length === 0 ? (
          <div className="kv">
            <span className="k">—</span>
            <span className="v">sin eventos</span>
          </div>
        ) : (
          snapshot.events.map((ev, i) => (
            <div className="kv" key={`${ev.timestamp}-${i}`}>
              <span className="k">{ev.timestamp}</span>
              <span className="v">
                {ev.name}
                {ev.detail ? ` (${ev.detail})` : ""}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
