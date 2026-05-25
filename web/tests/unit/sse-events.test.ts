/**
 * Unit tests · Sprint 3 api-integration · FASE 3.
 *
 * Verifican los 4 event types SSE nuevos (action / context_analysis /
 * dual_read_result / zone_selector) emitidos por el mock `streamChat` +
 * el helper `parseSSEContent` (doble parse del JSON-string-en-content que
 * usa el backend real para los card events).
 *
 * Por qué unit y no E2E: estos events actualizan STATE del hook
 * (lastAction / lastCard) sin UI que los renderee todavía — la UI de las
 * cards llega en Sprint 4. Un E2E no puede asertar DOM inexistente sin
 * modificar componentes (prohibido). El unit test cubre la lógica real.
 */
import { describe, expect, test } from "vitest";
import { streamChat, parseSSEContent, type ChatStreamChunk } from "@/lib/api";

async function collect(stream: ReadableStream<ChatStreamChunk>): Promise<ChatStreamChunk[]> {
  const reader = stream.getReader();
  const out: ChatStreamChunk[] = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    out.push(value);
  }
  return out;
}

describe("streamChat mock · event types SSE", () => {
  test("action + dual_read_result al pedir lectura del plano", async () => {
    const events = await collect(
      streamChat("PRES-2026-018", "leé el plano y las medidas", "contexto"),
    );
    const types = events.map((e) => e.type);
    expect(types).toContain("action");
    expect(types).toContain("dual_read_result");
    // siempre termina con texto + done
    expect(types).toContain("text");
    expect(types.at(-1)).toBe("done");
  });

  test("context_analysis en scope contexto al pedir análisis", async () => {
    const events = await collect(streamChat("PRES-2026-018", "analizá el contexto", "contexto"));
    const card = events.find((e) => e.type === "context_analysis");
    expect(card).toBeDefined();
    // content es JSON string → parseSSEContent lo expande a objeto
    const payload = parseSSEContent<{ data_known: string[] }>(card!);
    expect(typeof payload).toBe("object");
    expect((payload as { data_known: string[] }).data_known).toContain("cliente");
  });

  test("zone_selector al preguntar por una zona del plano", async () => {
    const events = await collect(
      streamChat("PRES-2026-018", "¿en qué zona está la bacha?", "despiece"),
    );
    const card = events.find((e) => e.type === "zone_selector");
    expect(card).toBeDefined();
    const payload = parseSSEContent<{ page_num: number; instruction: string }>(card!);
    expect((payload as { page_num: number }).page_num).toBe(1);
  });

  test("done siempre cierra el stream (sin card triggers)", async () => {
    const events = await collect(streamChat("PRES-2026-018", "hola", "contexto"));
    expect(events.at(-1)?.type).toBe("done");
    expect(events.some((e) => e.type === "text")).toBe(true);
  });

  test("parseSSEContent devuelve string crudo si no es JSON", () => {
    const chunk: ChatStreamChunk = { type: "action", content: "📐 Leyendo medidas…" };
    expect(parseSSEContent(chunk)).toBe("📐 Leyendo medidas…");
  });
});
