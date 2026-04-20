/**
 * PR #357 — Tests de `applyCandidate`.
 *
 * Cubren las 7 reglas que pidió el user para cerrar el fix del apply-flow:
 * 1. Binding por ID estable (click en R1 → R1; click en R2 → R2).
 * 2. Ancho default 0.60 en cocina/isla/lavadero cuando null.
 * 3. NO completar ancho en baño.
 * 4. NO sobrescribir ancho si ya tenía valor.
 * 5. Status DUDOSO en largo/ancho/m².
 * 6. Total m² se recalcula bien.
 * 7. Otros tramos/sectores no se tocan.
 */
import { describe, it, expect } from "vitest";
import { applyCandidate, StateLike } from "./applyCandidate";

/** Mock state con shape Bernardi realista: 2 sectores, 3 tramos. */
function makeBernardiState(): StateLike {
  return {
    sectores: [
      {
        id: "sector_cocina",
        tipo: "cocina",
        tramos: [
          {
            id: "R1",
            largo_m: { valor: null, status: "DUDOSO" },
            ancho_m: { valor: null, status: "DUDOSO" },
            m2: { valor: null, status: "DUDOSO" },
          },
          {
            id: "R2",
            largo_m: { valor: null, status: "DUDOSO" },
            ancho_m: { valor: null, status: "DUDOSO" },
            m2: { valor: null, status: "DUDOSO" },
          },
        ],
      },
      {
        id: "sector_isla",
        tipo: "isla",
        tramos: [
          {
            id: "R3",
            largo_m: { valor: 2.05, status: "CONFIRMADO" },
            ancho_m: { valor: 0.6, status: "CONFIRMADO" },
            m2: { valor: 1.23, status: "CONFIRMADO" },
          },
        ],
      },
    ],
  };
}

describe("applyCandidate — binding por ID estable (reglas 1, 5 de la spec)", () => {
  it("click en candidata R1 modifica SOLO R1, no toca R2 ni R3", () => {
    const state = makeBernardiState();
    const result = applyCandidate(state, "R1", 2.35);

    // R1 fue el target — tiene el valor nuevo.
    const r1 = result.state.sectores[0].tramos[0];
    expect(r1.id).toBe("R1");
    expect(r1.largo_m.valor).toBe(2.35);

    // R2 intacto (sigue null como antes).
    const r2 = result.state.sectores[0].tramos[1];
    expect(r2.id).toBe("R2");
    expect(r2.largo_m.valor).toBeNull();
    expect(r2.ancho_m.valor).toBeNull();

    // R3 (sector isla) intacto — su 2.05 original.
    const r3 = result.state.sectores[1].tramos[0];
    expect(r3.id).toBe("R3");
    expect(r3.largo_m.valor).toBe(2.05);
    expect(r3.ancho_m.valor).toBe(0.6);
    expect(r3.largo_m.status).toBe("CONFIRMADO");
  });

  it("click en candidata R2 modifica SOLO R2, no toca R1 ni R3", () => {
    const state = makeBernardiState();
    const result = applyCandidate(state, "R2", 2.95);

    const r1 = result.state.sectores[0].tramos[0];
    expect(r1.largo_m.valor).toBeNull(); // R1 sigue null

    const r2 = result.state.sectores[0].tramos[1];
    expect(r2.largo_m.valor).toBe(2.95); // R2 recibió el valor

    const r3 = result.state.sectores[1].tramos[0];
    expect(r3.largo_m.valor).toBe(2.05); // R3 intacto
  });

  it("click en candidata R3 modifica SOLO R3 (tramo en sector no-primero)", () => {
    const state = makeBernardiState();
    // Caso edge: R3 ya tenía valor, ahora se lo reemplazan con una candidata.
    const result = applyCandidate(state, "R3", 1.6);

    const r3 = result.state.sectores[1].tramos[0];
    expect(r3.largo_m.valor).toBe(1.6);
    // Ancho sigue 0.6 (no se sobrescribe porque ya tenía valor).
    expect(r3.ancho_m.valor).toBe(0.6);
    // Status pasa a DUDOSO aunque antes era CONFIRMADO.
    expect(r3.largo_m.status).toBe("DUDOSO");
    expect(r3.ancho_m.status).toBe("DUDOSO");

    // R1 y R2 intactos.
    expect(result.state.sectores[0].tramos[0].largo_m.valor).toBeNull();
    expect(result.state.sectores[0].tramos[1].largo_m.valor).toBeNull();
  });
});

describe("applyCandidate — ancho default (reglas 2, 3, 4 de la spec)", () => {
  it("completa ancho 0.60 en cocina cuando ancho era null", () => {
    const state = makeBernardiState();
    const result = applyCandidate(state, "R1", 2.35);

    const r1 = result.state.sectores[0].tramos[0];
    expect(r1.ancho_m.valor).toBe(0.6);
    expect(result.meta.anchoAutocompletado).toBe(true);
  });

  it("completa ancho 0.60 en isla cuando ancho era null", () => {
    const state: StateLike = {
      sectores: [
        {
          id: "sector_isla",
          tipo: "isla",
          tramos: [
            {
              id: "R_isla",
              largo_m: { valor: null, status: "DUDOSO" },
              ancho_m: { valor: null, status: "DUDOSO" },
              m2: { valor: null, status: "DUDOSO" },
            },
          ],
        },
      ],
    };
    const result = applyCandidate(state, "R_isla", 1.6);
    expect(result.state.sectores[0].tramos[0].ancho_m.valor).toBe(0.6);
    expect(result.meta.anchoAutocompletado).toBe(true);
  });

  it("completa ancho 0.60 en lavadero cuando ancho era null", () => {
    const state: StateLike = {
      sectores: [
        {
          id: "sector_lavadero",
          tipo: "lavadero",
          tramos: [
            {
              id: "R_lav",
              largo_m: { valor: null, status: "DUDOSO" },
              ancho_m: { valor: null, status: "DUDOSO" },
              m2: { valor: null, status: "DUDOSO" },
            },
          ],
        },
      ],
    };
    const result = applyCandidate(state, "R_lav", 1.8);
    expect(result.state.sectores[0].tramos[0].ancho_m.valor).toBe(0.6);
  });

  it("NO completa ancho en baño (regla 3)", () => {
    const state: StateLike = {
      sectores: [
        {
          id: "sector_banio",
          tipo: "baño",
          tramos: [
            {
              id: "R_banio",
              largo_m: { valor: null, status: "DUDOSO" },
              ancho_m: { valor: null, status: "DUDOSO" },
              m2: { valor: null, status: "DUDOSO" },
            },
          ],
        },
      ],
    };
    const result = applyCandidate(state, "R_banio", 1.2);
    expect(result.state.sectores[0].tramos[0].ancho_m.valor).toBeNull();
    expect(result.meta.anchoAutocompletado).toBe(false);
  });

  it("NO sobrescribe ancho si ya tenía valor (regla 4)", () => {
    const state: StateLike = {
      sectores: [
        {
          id: "sector_cocina",
          tipo: "cocina",
          tramos: [
            {
              id: "R_con_ancho",
              largo_m: { valor: null, status: "DUDOSO" },
              ancho_m: { valor: 0.7, status: "CONFIRMADO" }, // ya tenía 0.7
              m2: { valor: null, status: "DUDOSO" },
            },
          ],
        },
      ],
    };
    const result = applyCandidate(state, "R_con_ancho", 2.0);
    // Ancho sigue en 0.7, NO se sobreescribe.
    expect(result.state.sectores[0].tramos[0].ancho_m.valor).toBe(0.7);
    expect(result.meta.anchoAutocompletado).toBe(false);
  });

  it("normaliza tipo de sector (trim + lowercase)", () => {
    const state: StateLike = {
      sectores: [
        {
          id: "sector_cocina",
          tipo: "  COCINA  ", // variación de casing + espacios
          tramos: [
            {
              id: "R1",
              largo_m: { valor: null, status: "DUDOSO" },
              ancho_m: { valor: null, status: "DUDOSO" },
              m2: { valor: null, status: "DUDOSO" },
            },
          ],
        },
      ],
    };
    const result = applyCandidate(state, "R1", 2.35);
    expect(result.state.sectores[0].tramos[0].ancho_m.valor).toBe(0.6);
  });
});

describe("applyCandidate — status DUDOSO (regla 5)", () => {
  it("setea status DUDOSO en largo, ancho y m² del tramo target", () => {
    const state = makeBernardiState();
    const result = applyCandidate(state, "R3", 1.8); // R3 era CONFIRMADO

    const r3 = result.state.sectores[1].tramos[0];
    expect(r3.largo_m.status).toBe("DUDOSO");
    expect(r3.ancho_m.status).toBe("DUDOSO");
    expect(r3.m2.status).toBe("DUDOSO");
  });

  it("NO toca status de otros tramos al aplicar en un target", () => {
    const state = makeBernardiState();
    const result = applyCandidate(state, "R1", 2.35);

    // R3 que era CONFIRMADO sigue CONFIRMADO.
    const r3 = result.state.sectores[1].tramos[0];
    expect(r3.largo_m.status).toBe("CONFIRMADO");
    expect(r3.ancho_m.status).toBe("CONFIRMADO");
    expect(r3.m2.status).toBe("CONFIRMADO");
  });
});

describe("applyCandidate — recálculo de m² (regla 6)", () => {
  it("recalcula m² cuando largo y ancho son números", () => {
    const state = makeBernardiState();
    const result = applyCandidate(state, "R1", 2.35);

    const r1 = result.state.sectores[0].tramos[0];
    expect(r1.largo_m.valor).toBe(2.35);
    expect(r1.ancho_m.valor).toBe(0.6);
    expect(r1.m2.valor).toBe(1.41); // 2.35 × 0.6 = 1.41
  });

  it("m² queda null si ancho no pudo completarse (baño sin ancho previo)", () => {
    const state: StateLike = {
      sectores: [
        {
          id: "sector_banio",
          tipo: "baño",
          tramos: [
            {
              id: "R_banio",
              largo_m: { valor: null, status: "DUDOSO" },
              ancho_m: { valor: null, status: "DUDOSO" },
              m2: { valor: null, status: "DUDOSO" },
            },
          ],
        },
      ],
    };
    const result = applyCandidate(state, "R_banio", 1.2);
    const tramo = result.state.sectores[0].tramos[0];
    expect(tramo.largo_m.valor).toBe(1.2);
    expect(tramo.ancho_m.valor).toBeNull();
    expect(tramo.m2.valor).toBeNull();
  });

  it("redondea m² a 2 decimales", () => {
    const state: StateLike = {
      sectores: [
        {
          id: "sector_cocina",
          tipo: "cocina",
          tramos: [
            {
              id: "R1",
              largo_m: { valor: null, status: "DUDOSO" },
              ancho_m: { valor: 0.625, status: "DUDOSO" },
              m2: { valor: null, status: "DUDOSO" },
            },
          ],
        },
      ],
    };
    const result = applyCandidate(state, "R1", 2.3333);
    // 2.3333 × 0.625 = 1.4583... → redondeado 1.46
    expect(result.state.sectores[0].tramos[0].m2.valor).toBe(1.46);
  });
});

describe("applyCandidate — defensivo (regla implícita: fail-soft)", () => {
  it("regionId no existe → no muta el state", () => {
    const state = makeBernardiState();
    const result = applyCandidate(state, "R99_inexistente", 2.35);

    expect(result.meta.found).toBe(false);
    // Estado devuelto es el mismo (por referencia) — no se hizo clone.
    expect(result.state).toBe(state);
  });

  it("no muta el state original cuando encuentra el target", () => {
    const state = makeBernardiState();
    const before = JSON.stringify(state);
    applyCandidate(state, "R1", 2.35);

    // El state original no cambió — applyCandidate hace deep clone.
    expect(JSON.stringify(state)).toBe(before);
  });
});

describe("applyCandidate — meta de diagnóstico (regla 6 del user: logs)", () => {
  it("meta contiene before/after y target IDs para logs", () => {
    const state = makeBernardiState();
    const result = applyCandidate(state, "R1", 2.35);

    expect(result.meta.found).toBe(true);
    expect(result.meta.targetSectorId).toBe("sector_cocina");
    expect(result.meta.targetSectorTipo).toBe("cocina");
    expect(result.meta.targetTramoId).toBe("R1");
    expect(result.meta.beforeLargo).toBeNull();
    expect(result.meta.beforeAncho).toBeNull();
    expect(result.meta.afterLargo).toBe(2.35);
    expect(result.meta.afterAncho).toBe(0.6);
    expect(result.meta.anchoAutocompletado).toBe(true);
  });
});
