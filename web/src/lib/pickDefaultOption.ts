/**
 * Heurística para preseleccionar el default más común en una pregunta
 * bloqueante del bloque "Análisis de contexto".
 *
 * Regla (en orden):
 * 1. Si alguna opción tiene la palabra "estándar" (case-insensitive) en el
 *    label → esa es la default. El backend la marca explícitamente así
 *    (ej: "0.60 m (estándar residencial)", "0.90 m (estándar — piso a
 *    mesada)"). Es un contrato ligero con el copy del backend.
 * 2. Si no hay "estándar", devolver la primera opción NO custom. Son
 *    consideradas custom aquellas cuyo `value === "custom"` o el label
 *    contiene "detallar" o "otra" (typically "Otra medida (detallar)"):
 *    requieren input adicional, no se pueden usar como default "silencioso".
 * 3. Si todas las opciones son custom (edge case improbable) → null.
 *    El operador tiene que elegir explícitamente.
 *
 * Diseño:
 * - Función pura. Misma entrada → misma salida. Fácil de testear.
 * - No asume qué pregunta es: cualquier pregunta con el shape
 *   {value, label}[] funciona.
 * - Si el backend cambia los labels (ej. quita "estándar"), el fallback a
 *   "primera no custom" preserva el comportamiento razonable.
 */
export interface PickableOption {
  value: string;
  label: string;
}

const STANDARD_RE = /est[aá]ndar/i;
const CUSTOM_RE = /(detallar|otra)/i;

function isCustomOption(opt: PickableOption): boolean {
  if (opt.value === "custom") return true;
  return CUSTOM_RE.test(opt.label);
}

/**
 * Elige el value default para una pregunta con opciones, o null si no hay
 * un default razonable. Ver comentario arriba para la heurística.
 */
export function pickDefaultOption(
  options: PickableOption[] | undefined,
): string | null {
  if (!options || options.length === 0) return null;

  // Regla 1 — opción marcada como "estándar" en el label
  const standard = options.find(o => STANDARD_RE.test(o.label));
  if (standard) return standard.value;

  // Regla 2 — primera opción no custom
  const firstNonCustom = options.find(o => !isCustomOption(o));
  if (firstNonCustom) return firstNonCustom.value;

  // Regla 3 — todas son custom → null (sin preselect)
  return null;
}
