/**
 * Helpers de fallback del Qhead · Sprint 3 qhead-empty-title.
 *
 * MINOR #10 del audit CFC PR #465 ("título muestra '— — —'") consolidó la
 * lección operativa del Sprint 3: cuando un campo viene em-dash desde el
 * backend (o desde el SSR-fallback `ssrFallbackHeader`), NO renderearlo
 * literal — derivar un fallback inteligente o ocultar el campo.
 *
 * Mismo principio aplicado al PR #466 fix-up #2 (esconder AuditTray cuando
 * snapshot es genérico).
 */
import type { QuoteHeader } from "@/lib/api";

/** Considera "válido" cualquier string no vacío y distinto de em-dash. */
function isValid(s: unknown): s is string {
  if (typeof s !== "string") return false;
  const t = s.trim();
  return t !== "" && t !== "—";
}

/**
 * Título principal del Qhead. 4 niveles de fallback:
 * 1. `clientFull` + ` — ` + `client` cuando ambos válidos y distintos.
 * 2. `clientFull` solo válido.
 * 3. `client` solo válido.
 * 4. `"Presupuesto " + idCorto` (primeros 12 chars del ID para acortar UUIDs).
 *
 * Nunca devuelve em-dash literal: siempre algo legible para Marina.
 */
export function getQuoteDisplayName(quote: QuoteHeader): string {
  const a = isValid(quote.clientFull) ? quote.clientFull.trim() : null;
  const b = isValid(quote.client) ? quote.client.trim() : null;

  if (a && b && a !== b) return `${a} — ${b}`;
  if (a) return a;
  if (b) return b;

  const id = quote.id ?? "";
  return id ? `Presupuesto ${shortenId(id)}` : "Presupuesto sin nombre";
}

/**
 * Acorta IDs estilo UUID (`web-<8hex>-…` o el UUID v4 estándar) al primer
 * segmento legible. IDs canónicos cortos (`PRES-2026-018`) se mantienen
 * intactos para no truncar arbitrariamente texto del usuario.
 */
function shortenId(id: string): string {
  // Patrón `prefix-` (1+ letras) `<8hex>` que cubre `web-9543be47-…`.
  const prefixed = id.match(/^([a-z]+-[0-9a-f]{8})/i);
  if (prefixed) return prefixed[1];
  // UUID v4 puro `xxxxxxxx-xxxx-…` → primeros 8 hex.
  const uuid = id.match(/^([0-9a-f]{8})-[0-9a-f]{4}-/i);
  if (uuid) return uuid[1];
  // IDs muy largos sin patrón claro: ellipsis. Threshold > 20 para no
  // tocar canon (PRES-2026-018-ERROR es 19 chars).
  if (id.length > 20) return id.slice(0, 12) + "…";
  return id;
}

/**
 * Sub del Qhead · `{id} · {material} · {m2} m²`. Ocultá campos cuando son
 * em-dash. Siempre muestra el `id` (es el único garantizado por el routing).
 *
 * Casos posibles:
 *  - material + m² válidos → "ID · material · 6,50 m²"
 *  - material válido / m² no → "ID · material"
 *  - material no / m² válido → "ID · 6,50 m²"
 *  - ambos no → "ID"
 *
 * Recibe el `surfaceFmt` pre-formateado (el componente ya formateaba con
 * toLocaleString) para no duplicar la lógica de formato.
 */
export function getQuoteDisplaySub(quote: QuoteHeader, surfaceFmt: string): string {
  const parts: string[] = [quote.id];
  if (isValid(quote.material)) parts.push(quote.material.trim());
  if (isValid(surfaceFmt)) parts.push(`${surfaceFmt} m²`);
  return parts.join(" · ");
}
