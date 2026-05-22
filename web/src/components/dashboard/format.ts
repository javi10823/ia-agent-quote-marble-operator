/**
 * Helpers de formateo del dashboard.
 *
 * Locale `es-AR`:
 *   - ARS: `$660.890` (separador miles con punto, sin decimales)
 *   - USD: `USD 1.538` (espacio, separador miles con punto)
 *   - m²:  `6,50 m²` (coma decimal · 2 decimales)
 */

export function formatARS(value: number): string {
  return `$${value.toLocaleString("es-AR", { maximumFractionDigits: 0 })}`;
}

export function formatUSD(value: number): string {
  return `USD ${value.toLocaleString("es-AR", { maximumFractionDigits: 0 })}`;
}

export function formatAmount(amount: number, currency: "ARS" | "USD"): string {
  return currency === "ARS" ? formatARS(amount) : formatUSD(amount);
}

export function formatM2(value: number): string {
  return `${value.toLocaleString("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} m²`;
}
