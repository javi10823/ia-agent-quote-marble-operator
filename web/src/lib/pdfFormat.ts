/**
 * Helpers puros del paso 5 PDF · Sprint 4 paso-5-pdf-preview.
 *
 * Formato canónico del filename + fecha del PDF según mockup 18:
 * `Cueto-Heredia Arquitectura - Silestone Blanco Norte - 03.05.2026.pdf`
 *
 * Date determinístico para tests (lección Sprint 3 PR #466): aceptamos
 * `Date | string` override y SOLO usamos `new Date()` cuando no se pasa
 * argumento.
 */

/** Formato `dd.mm.yyyy` (español rioplatense del mockup). */
export function formatPdfDate(d: Date = new Date()): string {
  const day = String(d.getDate()).padStart(2, "0");
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const year = d.getFullYear();
  return `${day}.${month}.${year}`;
}

interface FilenameInput {
  client: string;
  material: string;
  date?: Date;
  ext: "pdf" | "xlsx";
}

/**
 * Filename auto-generado: `${client} - ${material} - ${dd.mm.yyyy}.${ext}`
 *
 * - Trim de espacios y normalización a single-space.
 * - Si client/material son em-dash o vacíos, omite el token (no genera
 *   `" - "` al inicio · matchea la lección del PR #467 helper qhead).
 * - Date default = hoy; aceptamos override para tests determinísticos.
 */
export function getPdfFilename({ client, material, date, ext }: FilenameInput): string {
  const parts = [client, material]
    .map((s) => (typeof s === "string" ? s.trim() : ""))
    .filter((s) => s.length > 0 && s !== "—")
    .map((s) => s.replace(/\s+/g, " "));
  parts.push(formatPdfDate(date));
  return `${parts.join(" - ")}.${ext}`;
}

/**
 * Seed value del textarea "Datos de envío" del sidebar.
 * Auto-fill desde paso-2 (cliente + localidad). El user puede editar libre.
 * Si falta un campo, lo omitimos (mismo principio que getPdfFilename).
 */
export function getEnvioSeed(input: {
  cliente?: string | null;
  localidad?: string | null;
}): string {
  const parts = [input.cliente, input.localidad]
    .map((s) => (typeof s === "string" ? s.trim() : ""))
    .filter((s) => s.length > 0 && s !== "—");
  return parts.join(" · ");
}
