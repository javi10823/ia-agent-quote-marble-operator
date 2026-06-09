/**
 * Unit tests · Sprint 4 audit-trail-copy · format function.
 *
 * Cubre el formato LITERAL definido en el bundle FASE 1 (sección 1.11)
 * para que el plain text del clipboard sea parseable por Master/Claude
 * Code y útil para debug rápido.
 */
import { describe, expect, test } from "vitest";
import { formatAuditCopy, latencySeverity } from "@/lib/utils/format-audit-copy";
import type { AuditLogResponse } from "@/lib/api/types";

const BASE_TS = "2026-05-03T18:42:00.000Z";

function buildAudit(overrides: Partial<AuditLogResponse> = {}): AuditLogResponse {
  return {
    meta: {
      quote_id: "PRES-2026-018",
      status: "sent",
      client_name: "Cueto-Heredia",
      project: "cocina U + isla",
      material: "Silestone Blanco Norte",
      total_ars: 660739,
      total_usd: 1538,
      created_at: BASE_TS,
      updated_at: "2026-05-03T19:00:00.000Z",
    },
    input_message: "Hola Marina, te paso el plano...",
    plan_files: ["plano.pdf"],
    events: [],
    events_total: 0,
    events_truncated: false,
    chat_duration_ms: null,
    tokens: {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
      cost_usd: 0,
      iterations: 0,
      models_used: [],
    },
    tools_used: [],
    errors: [],
    ...overrides,
  };
}

describe("formatAuditCopy · header + INPUT", () => {
  test("header literal con quote_id + status + client + material + totales", () => {
    const out = formatAuditCopy(buildAudit());
    expect(out).toContain("QUOTE AUDIT · PRES-2026-018");
    expect(out).toContain("status: sent");
    expect(out).toContain("client: Cueto-Heredia");
    expect(out).toContain("project: cocina U + isla");
    expect(out).toContain("material: Silestone Blanco Norte");
    expect(out).toMatch(/total: \$\d+\.?\d* ARS \+ USD \d+\.?\d*/);
  });

  test("INPUT con brief_text y plan_files", () => {
    const out = formatAuditCopy(buildAudit());
    expect(out).toContain("INPUT");
    expect(out).toContain('brief_text: "Hola Marina, te paso el plano..."');
    expect(out).toContain('plan_files: ["plano.pdf"]');
  });

  test("INPUT degrada gracioso cuando no hay brief_text", () => {
    const out = formatAuditCopy(buildAudit({ input_message: null, plan_files: [] }));
    expect(out).toContain("brief_text: (none)");
    expect(out).toContain("plan_files: []");
  });
});

describe("formatAuditCopy · timeline", () => {
  test("eventos con delta relativo y elapsed", () => {
    const audit = buildAudit({
      events: [
        {
          created_at: BASE_TS,
          event_type: "quote.created",
          source: "router",
          summary: "Quote created",
          payload: {},
          success: true,
        },
        {
          created_at: "2026-05-03T18:42:12.456Z",
          event_type: "agent.tool_result",
          source: "agent",
          summary: "read_plan ok",
          payload: { tool_name: "read_plan" },
          success: true,
          elapsed_ms: 11566,
        },
      ],
      events_total: 2,
    });
    const out = formatAuditCopy(audit);
    expect(out).toContain("EVENTS (timeline · 2 total)");
    expect(out).toContain("[+0.000s] quote.created");
    expect(out).toContain("[+12.456s] agent.tool_result");
    expect(out).toContain("elapsed=11.57s");
  });

  test("evento con error muestra ✗ y error_message", () => {
    const out = formatAuditCopy(
      buildAudit({
        events: [
          {
            created_at: BASE_TS,
            event_type: "agent.tool_result",
            source: "agent",
            summary: "read_plan failed",
            payload: {},
            success: false,
            error_message: "OCR fallido",
          },
        ],
        events_total: 1,
      }),
    );
    expect(out).toContain("agent.tool_result ✗");
    expect(out).toContain('error="OCR fallido"');
  });

  test("truncation muestra '... +N más'", () => {
    const out = formatAuditCopy(
      buildAudit({
        events: [
          {
            created_at: BASE_TS,
            event_type: "quote.created",
            source: "router",
            summary: "",
            payload: {},
            success: true,
          },
        ],
        events_total: 250,
        events_truncated: true,
      }),
    );
    expect(out).toContain("EVENTS (timeline · 250 total · trunc to 1)");
    expect(out).toContain("... +249 más (usar ?full=true)");
  });
});

describe("formatAuditCopy · CALLS + tokens", () => {
  test("CALLS con chat_duration + tools + tokens + models", () => {
    const out = formatAuditCopy(
      buildAudit({
        chat_duration_ms: 25012,
        tools_used: [
          { tool_name: "read_plan", count: 1, total_ms: 11566, error_count: 0 },
          { tool_name: "catalog_lookup", count: 8, total_ms: 1840, error_count: 1 },
        ],
        tokens: {
          input_tokens: 12847,
          output_tokens: 3421,
          cache_read_tokens: 8200,
          cache_write_tokens: 0,
          cost_usd: 0.087,
          iterations: 4,
          models_used: ["opus", "sonnet"],
        },
      }),
    );
    expect(out).toContain("CALLS");
    expect(out).toContain("POST /api/quotes/{id}/chat · 25.01s");
    expect(out).toContain("· read_plan (1×, 11.57s)");
    expect(out).toContain("· catalog_lookup (8×, 1.84s) · errors=1");
    expect(out).toContain("12.847 in / 3.421 out");
    expect(out).toContain("cache_read=8.200");
    expect(out).toContain("cost_usd=$0.0870");
    expect(out).toContain("models: opus, sonnet");
  });
});

describe("formatAuditCopy · QUOTE_BREAKDOWN + ERRORS + footer", () => {
  test("incluye breakdown JSON por default", () => {
    const out = formatAuditCopy(
      buildAudit({ quote_breakdown: { sectors: [{ id: "S1" }], total_ars: 1000 } }),
    );
    expect(out).toContain("QUOTE_BREAKDOWN (snapshot)");
    expect(out).toContain('"total_ars": 1000');
  });

  test("includeBreakdown=false omite la sección", () => {
    const out = formatAuditCopy(buildAudit({ quote_breakdown: { x: 1 } }), {
      includeBreakdown: false,
    });
    expect(out).not.toContain("QUOTE_BREAKDOWN");
  });

  test("timelineOnly omite CALLS + BREAKDOWN + ERRORS + footer", () => {
    const out = formatAuditCopy(
      buildAudit({
        events: [
          {
            created_at: BASE_TS,
            event_type: "quote.created",
            source: "router",
            summary: "",
            payload: {},
            success: true,
          },
        ],
        events_total: 1,
        chat_duration_ms: 1000,
        quote_breakdown: { x: 1 },
      }),
      { timelineOnly: true },
    );
    expect(out).toContain("EVENTS");
    expect(out).not.toContain("CALLS");
    expect(out).not.toContain("QUOTE_BREAKDOWN");
    expect(out).not.toContain("End audit");
  });

  test("ERRORS none cuando errors.length=0", () => {
    const out = formatAuditCopy(buildAudit());
    expect(out).toContain("ERRORS (0)");
    expect(out).toContain("none");
  });

  test("ERRORS lista con error_message", () => {
    const out = formatAuditCopy(
      buildAudit({
        errors: [
          {
            created_at: "2026-05-03T18:42:10.000Z",
            event_type: "agent.tool_result",
            source: "agent",
            summary: "read_plan failed",
            payload: {},
            success: false,
            error_message: "OCR fallido",
          },
        ],
      }),
    );
    expect(out).toContain("ERRORS (1)");
    expect(out).toContain("[+10.000s] agent.tool_result · read_plan failed");
    expect(out).toContain('error="OCR fallido"');
  });

  test("footer con counts + total duration", () => {
    const out = formatAuditCopy(
      buildAudit({
        events: [
          {
            created_at: BASE_TS,
            event_type: "quote.created",
            source: "router",
            summary: "",
            payload: {},
            success: true,
          },
          {
            created_at: "2026-05-03T18:42:25.000Z",
            event_type: "docs.generated",
            source: "agent",
            summary: "",
            payload: {},
            success: true,
          },
        ],
        events_total: 2,
        tools_used: [{ tool_name: "x", count: 1, total_ms: 100, error_count: 0 }],
      }),
    );
    expect(out).toContain("End audit · 2 events · 1 tool types · 0 errors · total +25.000s");
  });
});

describe("latencySeverity thresholds", () => {
  test("< 5s → ok", () => {
    expect(latencySeverity(4999)).toBe("ok");
  });
  test("5-15s → watch", () => {
    expect(latencySeverity(5000)).toBe("watch");
    expect(latencySeverity(14999)).toBe("watch");
  });
  test("15-30s → slow", () => {
    expect(latencySeverity(15000)).toBe("slow");
    expect(latencySeverity(29999)).toBe("slow");
  });
  test(">=30s → alert", () => {
    expect(latencySeverity(30000)).toBe("alert");
    expect(latencySeverity(60000)).toBe("alert");
  });
});
