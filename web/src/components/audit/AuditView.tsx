/**
 * Vista pretty del audit log · Sprint 4 audit-trail-copy.
 *
 * Renderiza meta + 3 botones copy (todo / timeline / JSON) + timeline
 * vertical + tabla de calls agregados + JSON breakdown colapsable.
 *
 * Reusa clases legacy `.section-head`, `.col`, `.trace-block`,
 * `.kpi-card`. Coloring de latencia via `data-severity` + inline styles
 * con CSS vars existentes (`--ok` `--warn` `--alert`). Cero CSS nuevo.
 */
"use client";

import { useState } from "react";
import type { AuditLogResponse } from "@/lib/api/types";
import {
  formatAuditCopy,
  latencySeverity,
  type LatencySeverity,
} from "@/lib/utils/format-audit-copy";

interface Props {
  audit: AuditLogResponse;
}

const SEV_COLORS: Record<LatencySeverity, string> = {
  ok: "var(--ok, oklch(0.72 0.18 145))",
  watch: "var(--warn, oklch(0.78 0.16 80))",
  slow: "var(--warn, oklch(0.65 0.18 50))",
  alert: "var(--error, oklch(0.65 0.20 25))",
};

function epochMs(iso: string): number {
  return new Date(iso).getTime();
}

function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms}ms`;
}

function fmtNum(n: number): string {
  return n.toLocaleString("es-AR");
}

export function AuditView({ audit }: Props) {
  const [copied, setCopied] = useState<"all" | "timeline" | "json" | null>(null);

  const handleCopy = async (kind: "all" | "timeline" | "json") => {
    let text: string;
    if (kind === "all") {
      text = formatAuditCopy(audit);
    } else if (kind === "timeline") {
      text = formatAuditCopy(audit, { timelineOnly: true });
    } else {
      text = audit.quote_breakdown ? JSON.stringify(audit.quote_breakdown, null, 2) : "{}";
    }
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      }
    } catch {
      /* best-effort */
    }
    setCopied(kind);
    setTimeout(() => setCopied(null), 1800);
  };

  const createdEpoch = epochMs(audit.meta.created_at);

  return (
    <div className="col" data-testid="audit-view">
      {/* ─── Header ───────────────────────────────────────────────── */}
      <div className="section-head">
        <div>
          <div className="meta">Audit log · debug + iteración</div>
          <h2>{audit.meta.quote_id}</h2>
          <div className="vc-wrap" style={{ fontSize: 12, color: "var(--ink-mute)" }}>
            <span>status: {audit.meta.status}</span>
            {audit.meta.client_name && <span>· {audit.meta.client_name}</span>}
            {audit.meta.material && <span>· {audit.meta.material}</span>}
          </div>
        </div>
        <div className="right">
          <button
            type="button"
            className="btn primary sm"
            onClick={() => handleCopy("all")}
            data-testid="audit-copy-all"
          >
            {copied === "all" ? "✓ Copiado" : "📋 Copiar todo"}
          </button>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => handleCopy("timeline")}
            data-testid="audit-copy-timeline"
          >
            {copied === "timeline" ? "✓ Copiado" : "Copiar timeline"}
          </button>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => handleCopy("json")}
            data-testid="audit-copy-json"
          >
            {copied === "json" ? "✓ Copiado" : "Copiar JSON"}
          </button>
        </div>
      </div>

      {/* ─── Summary chips ───────────────────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: 12,
          marginBottom: 16,
        }}
        data-testid="audit-summary"
      >
        <SummaryChip label="Eventos" value={fmtNum(audit.events_total)} />
        <SummaryChip
          label="Chat duration"
          value={fmtMs(audit.chat_duration_ms)}
          severity={
            audit.chat_duration_ms != null ? latencySeverity(audit.chat_duration_ms) : undefined
          }
          testId="summary-chat-duration"
        />
        <SummaryChip
          label="Tokens (in/out)"
          value={`${fmtNum(audit.tokens.input_tokens)} / ${fmtNum(audit.tokens.output_tokens)}`}
        />
        <SummaryChip label="Cost USD" value={`$${audit.tokens.cost_usd.toFixed(4)}`} />
        <SummaryChip
          label="Errors"
          value={fmtNum(audit.errors.length)}
          severity={audit.errors.length > 0 ? "alert" : "ok"}
          testId="summary-errors"
        />
      </div>

      {/* ─── Input ────────────────────────────────────────────────── */}
      {audit.input_message && (
        <details
          open
          style={{
            border: "1px solid var(--line)",
            borderRadius: 6,
            padding: "10px 14px",
            marginBottom: 14,
          }}
        >
          <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--ink-soft)" }}>
            INPUT · brief_text + plan_files ({audit.plan_files.length})
          </summary>
          <p
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "var(--ink)",
              marginTop: 10,
              whiteSpace: "pre-wrap",
            }}
            data-testid="audit-input-text"
          >
            {audit.input_message}
          </p>
          {audit.plan_files.length > 0 && (
            <p style={{ fontSize: 11, color: "var(--ink-mute)", marginTop: 6 }}>
              plan_files: {audit.plan_files.map((f) => `"${f}"`).join(", ")}
            </p>
          )}
        </details>
      )}

      {/* ─── Tools used + tokens ──────────────────────────────────── */}
      {audit.tools_used.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <h3 style={{ fontSize: 13, color: "var(--ink-soft)", margin: "0 0 8px" }}>
            Tools usados ({audit.tools_used.length})
          </h3>
          <table
            style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}
            data-testid="audit-tools-table"
          >
            <thead>
              <tr style={{ color: "var(--ink-mute)", textAlign: "left" }}>
                <th style={{ padding: "6px 8px" }}>Tool</th>
                <th style={{ padding: "6px 8px", textAlign: "right" }}>Count</th>
                <th style={{ padding: "6px 8px", textAlign: "right" }}>Total time</th>
                <th style={{ padding: "6px 8px", textAlign: "right" }}>Errors</th>
              </tr>
            </thead>
            <tbody>
              {audit.tools_used.map((t) => {
                const sev = latencySeverity(t.total_ms);
                return (
                  <tr
                    key={t.tool_name}
                    style={{ borderTop: "1px solid var(--line)" }}
                    data-testid={`audit-tool-${t.tool_name}`}
                    data-severity={sev}
                  >
                    <td
                      style={{
                        padding: "6px 8px",
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                      }}
                    >
                      {t.tool_name}
                    </td>
                    <td style={{ padding: "6px 8px", textAlign: "right" }}>{t.count}</td>
                    <td
                      style={{
                        padding: "6px 8px",
                        textAlign: "right",
                        color: SEV_COLORS[sev],
                        fontFamily: "var(--mono)",
                      }}
                    >
                      {fmtMs(t.total_ms)}
                    </td>
                    <td
                      style={{
                        padding: "6px 8px",
                        textAlign: "right",
                        color: t.error_count > 0 ? "var(--error)" : "var(--ink-mute)",
                      }}
                    >
                      {t.error_count}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ─── Timeline ─────────────────────────────────────────────── */}
      <h3 style={{ fontSize: 13, color: "var(--ink-soft)", margin: "12px 0 8px" }}>
        Timeline ({audit.events_total} eventos
        {audit.events_truncated ? ` · truncated to ${audit.events.length}` : ""})
      </h3>
      <ol
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          borderLeft: "2px solid var(--line)",
          paddingLeft: 12,
        }}
        data-testid="audit-timeline"
      >
        {audit.events.map((ev, i) => {
          const delta = epochMs(ev.created_at) - createdEpoch;
          const deltaStr = `+${(delta / 1000).toFixed(3)}s`;
          const sev = ev.elapsed_ms != null ? latencySeverity(ev.elapsed_ms) : null;
          return (
            <li
              key={`${ev.event_type}-${i}`}
              style={{
                margin: "4px 0",
                fontSize: 12,
                fontFamily: "var(--mono)",
                color: ev.success ? "var(--ink)" : "var(--error)",
              }}
              data-testid={`audit-event-${i}`}
              data-event-type={ev.event_type}
              data-severity={sev ?? "none"}
            >
              <span style={{ color: "var(--ink-mute)" }}>[{deltaStr}]</span>{" "}
              <span style={{ fontWeight: 600 }}>{ev.event_type}</span>
              {!ev.success && <span style={{ color: "var(--error)" }}> ✗</span>}
              {ev.elapsed_ms != null && (
                <span style={{ color: SEV_COLORS[sev!], marginLeft: 6 }}>
                  · {fmtMs(ev.elapsed_ms)}
                </span>
              )}
              {ev.summary && (
                <span style={{ color: "var(--ink-soft)" }}> · {ev.summary}</span>
              )}
              {ev.error_message && (
                <span style={{ color: "var(--error)" }}> · {ev.error_message}</span>
              )}
            </li>
          );
        })}
      </ol>

      {/* ─── Errors ───────────────────────────────────────────────── */}
      {audit.errors.length > 0 && (
        <div
          style={{
            marginTop: 14,
            padding: "10px 14px",
            border: "1px solid var(--error)",
            borderRadius: 6,
            background: "color-mix(in oklch, var(--error) 8%, transparent)",
          }}
          data-testid="audit-errors"
        >
          <h3 style={{ fontSize: 13, color: "var(--error)", margin: "0 0 8px" }}>
            Errors ({audit.errors.length})
          </h3>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {audit.errors.map((err, i) => (
              <li
                key={i}
                style={{ fontSize: 12, fontFamily: "var(--mono)", margin: "4px 0" }}
              >
                <strong>{err.event_type}</strong>: {err.summary}
                {err.error_message && (
                  <span style={{ color: "var(--error)" }}> — {err.error_message}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ─── Breakdown JSON colapsable ──────────────────────────── */}
      {audit.quote_breakdown && (
        <details
          className="trace-block"
          style={{ marginTop: 18 }}
          data-testid="audit-breakdown-details"
        >
          <summary>quote_breakdown JSON</summary>
          <pre
            style={{
              fontSize: 11,
              padding: 14,
              background: "var(--bg-muted)",
              borderRadius: 4,
              overflowX: "auto",
              fontFamily: "var(--mono)",
            }}
          >
            {JSON.stringify(audit.quote_breakdown, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

interface SummaryChipProps {
  label: string;
  value: string;
  severity?: LatencySeverity;
  testId?: string;
}

function SummaryChip({ label, value, severity, testId }: SummaryChipProps) {
  return (
    <div
      style={{
        border: "1px solid var(--line)",
        borderRadius: 6,
        padding: "10px 12px",
      }}
      data-testid={testId}
      data-severity={severity ?? "none"}
    >
      <div style={{ fontSize: 11, color: "var(--ink-mute)", marginBottom: 4 }}>{label}</div>
      <div
        style={{
          fontSize: 16,
          fontFamily: "var(--mono)",
          color: severity ? SEV_COLORS[severity] : "var(--ink)",
          fontWeight: 600,
        }}
      >
        {value}
      </div>
    </div>
  );
}
