/**
 * PR #357 — applyCandidate: función PURA que aplica una candidata sugerida
 * al tramo correspondiente.
 *
 * Reglas (del user, tarea #357):
 * 1. Escribe el largo del tramo cuyo `id` === `regionId`. Nunca escribe en
 *    otro tramo. Binding estable por ID, no por índice de posición.
 * 2. Si el tramo destino tiene `ancho_m.valor === null` Y sector es
 *    "cocina" | "isla" | "lavadero" → completa con 0.60 (default residencial).
 *    NO toca ancho en baño. NO sobrescribe ancho si ya tenía valor.
 * 3. Marca el tramo como DUDOSO explícitamente: `largo_m.status`,
 *    `ancho_m.status`, `m2.status` = "DUDOSO".
 * 4. Recalcula m² con el nuevo largo × ancho.
 * 5. No toca otros tramos ni otros sectores.
 * 6. Si no encuentra el tramo (regionId inválido), devuelve el estado sin
 *    cambios — fail loud sería tirar error, fail soft es no mutar.
 *
 * Diseño: función pura `(state, regionId, valor) => nextState`. Facilita
 * tests sin DOM y mantiene `setEditedData(prev => applyCandidate(prev, ...))`.
 */

const ANCHO_DEFAULT_RESIDENCIAL = 0.6;
const SECTOR_CON_ANCHO_DEFAULT = new Set(["cocina", "isla", "lavadero"]);

/** Tipo minimalista que refleja lo que `applyCandidate` necesita. Usado en
 *  tests para no tener que importar todo el shape de DualReadResult. El
 *  caller real pasa su `DualReadData` directamente — TypeScript valida
 *  estructural compatibility (sin index signatures para permitir tipos
 *  concretos del caller con más campos). */
export interface FieldLike {
  valor: number | null;
  status: string;
  opus?: number | null;
  sonnet?: number | null;
}

export interface TramoLike {
  id: string;
  largo_m: FieldLike;
  ancho_m: FieldLike;
  m2: FieldLike;
}

export interface SectorLike {
  id: string;
  tipo: string;
  tramos: TramoLike[];
}

export interface StateLike {
  sectores: SectorLike[];
}

export interface ApplyCandidateResult<S> {
  state: S;
  meta: {
    found: boolean;
    targetSectorId?: string;
    targetSectorTipo?: string;
    targetTramoId?: string;
    beforeLargo?: number | null;
    beforeAncho?: number | null;
    afterLargo: number | null;
    afterAncho: number | null;
    anchoAutocompletado: boolean;
  };
}

export function applyCandidate<S extends StateLike>(
  state: S,
  regionId: string,
  valor: number,
): ApplyCandidateResult<S> {
  // Deep clone para no mutar el state que viene del caller (React quiere
  // referencias nuevas para detectar cambios de renderizado).
  const next: S = JSON.parse(JSON.stringify(state));

  // Buscar el tramo por id estable — NO por índice.
  let targetSectorIdx = -1;
  let targetTramoIdx = -1;
  for (let si = 0; si < next.sectores.length; si++) {
    const sector = next.sectores[si];
    for (let ti = 0; ti < sector.tramos.length; ti++) {
      if (sector.tramos[ti].id === regionId) {
        targetSectorIdx = si;
        targetTramoIdx = ti;
        break;
      }
    }
    if (targetSectorIdx !== -1) break;
  }

  if (targetSectorIdx === -1) {
    // regionId no existe — no mutamos. El caller ve `meta.found=false`
    // y puede decidir qué hacer (log error, toast, etc).
    return {
      state,
      meta: {
        found: false,
        afterLargo: null,
        afterAncho: null,
        anchoAutocompletado: false,
      },
    };
  }

  const sector = next.sectores[targetSectorIdx];
  const tramo = sector.tramos[targetTramoIdx];
  const beforeLargo = tramo.largo_m.valor;
  const beforeAncho = tramo.ancho_m.valor;

  // 1. Escribir largo + marcar DUDOSO.
  tramo.largo_m.valor = valor;
  tramo.largo_m.status = "DUDOSO";

  // 2. Ancho default si aplica: null + cocina/isla/lavadero → 0.60.
  //    NO sobrescribe si ya tenía valor. NO aplica en baño.
  let anchoAutocompletado = false;
  if (tramo.ancho_m.valor === null) {
    const sectorTipoLc = (sector.tipo || "").toLowerCase().trim();
    if (SECTOR_CON_ANCHO_DEFAULT.has(sectorTipoLc)) {
      tramo.ancho_m.valor = ANCHO_DEFAULT_RESIDENCIAL;
      anchoAutocompletado = true;
    }
  }
  // Status del ancho pasa a DUDOSO siempre (el tramo entero entra en
  // revisión manual).
  tramo.ancho_m.status = "DUDOSO";

  // 3. Recalcular m² determinísticamente (consistente con updateField
  //    existente). null si alguno sigue null.
  const largo = tramo.largo_m.valor;
  const ancho = tramo.ancho_m.valor;
  if (typeof largo === "number" && typeof ancho === "number") {
    tramo.m2.valor = Math.round(largo * ancho * 100) / 100;
  } else {
    tramo.m2.valor = null;
  }
  tramo.m2.status = "DUDOSO";

  return {
    state: next,
    meta: {
      found: true,
      targetSectorId: sector.id,
      targetSectorTipo: sector.tipo,
      targetTramoId: tramo.id,
      beforeLargo,
      beforeAncho,
      afterLargo: tramo.largo_m.valor,
      afterAncho: tramo.ancho_m.valor,
      anchoAutocompletado,
    },
  };
}
