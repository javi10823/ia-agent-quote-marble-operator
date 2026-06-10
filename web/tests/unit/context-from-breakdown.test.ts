/**
 * Unit tests · Sprint 4 paso-2-context-wire-real · Bug 1 fix.
 *
 * Cubre el adapter pure function `breakdownToContext()` que traduce
 * `quote_breakdown` del backend a `ContextResponse` del frontend.
 *
 * Casos cubiertos (12):
 * - happy path data_known con Localidad/Material/Cliente
 * - assumptions con Zócalos/Pileta
 * - _brief_analysis_raw fallback cuando data_known vacío
 * - source mapping 8→5 (BRIEF / INFERIDO / DEFAULT)
 * - "quote" source mapea a BRIEF (deuda documentada Bug 3)
 * - verified_context_analysis > pending precedencia
 * - breakdown null → todos FALTA (preserva "—" behavior)
 * - work_types[] array → tipologia string concatenado
 * - es_edificio bool → tipo_obra particular/edificio
 * - regrueso_mentioned bool → "Sí"/"No"
 * - anafe_mentioned bool → boolean directo
 * - "brief+rule" multi-source → BRIEF
 */
import { describe, expect, test } from "vitest";
import {
  breakdownToContext,
  mapBackendSourceToOrigin,
} from "@/lib/api/adapters/context-from-breakdown";

describe("mapBackendSourceToOrigin · 8 → 5 source mapping", () => {
  test("brief variants → BRIEF", () => {
    expect(mapBackendSourceToOrigin("brief")).toBe("BRIEF");
    expect(mapBackendSourceToOrigin("brief+rule")).toBe("BRIEF");
    expect(mapBackendSourceToOrigin("brief+dual_read")).toBe("BRIEF");
  });

  test("quote → BRIEF (deuda Bug 3 documentada · operador-input consistency)", () => {
    expect(mapBackendSourceToOrigin("quote")).toBe("BRIEF");
  });

  test("dual_read / rule / inferred → INFERIDO", () => {
    expect(mapBackendSourceToOrigin("dual_read")).toBe("INFERIDO");
    expect(mapBackendSourceToOrigin("rule")).toBe("INFERIDO");
    expect(mapBackendSourceToOrigin("inferred")).toBe("INFERIDO");
  });

  test("config_default → DEFAULT", () => {
    expect(mapBackendSourceToOrigin("config_default")).toBe("DEFAULT");
  });

  test("null/undefined/empty → FALTA", () => {
    expect(mapBackendSourceToOrigin(null)).toBe("FALTA");
    expect(mapBackendSourceToOrigin(undefined)).toBe("FALTA");
    expect(mapBackendSourceToOrigin("")).toBe("FALTA");
  });

  test("source desconocido → INFERIDO (defensivo · no esconde como FALTA)", () => {
    expect(mapBackendSourceToOrigin("unknown_source")).toBe("INFERIDO");
  });
});

describe("breakdownToContext · null/undefined/empty input", () => {
  test("breakdown null → todos los fields FALTA · preserva '—' behavior", () => {
    const ctx = breakdownToContext(null);
    expect(ctx.localidad.value).toBeNull();
    expect(ctx.localidad.origin).toBe("FALTA");
    expect(ctx.cliente.value).toBeNull();
    expect(ctx.cliente.origin).toBe("FALTA");
    expect(ctx.material.value).toBeNull();
    expect(ctx.material.origin).toBe("FALTA");
    expect(ctx.contacto.value).toBeNull();
    expect(ctx.contacto.origin).toBe("FALTA");
  });

  test("breakdown vacío {} → todos FALTA", () => {
    const ctx = breakdownToContext({});
    expect(ctx.localidad.origin).toBe("FALTA");
    expect(ctx.material.origin).toBe("FALTA");
  });

  test("anafe defaults a false + FALTA cuando no hay raw", () => {
    const ctx = breakdownToContext({});
    expect(ctx.anafe.value).toBe(false);
    expect(ctx.anafe.origin).toBe("FALTA");
  });

  test("tipo_obra defaults a particular + DEFAULT cuando es_edificio undefined", () => {
    const ctx = breakdownToContext({});
    expect(ctx.tipo_obra.value).toBe("particular");
    expect(ctx.tipo_obra.origin).toBe("DEFAULT");
  });
});

describe("breakdownToContext · data_known precedencia y mapping", () => {
  test("data_known con Localidad/Material/Cliente → BRIEF mapeo correcto", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        data_known: [
          { field: "Cliente", value: "Cueto-Heredia", source: "brief" },
          { field: "Localidad", value: "Rosario", source: "brief" },
          { field: "Material", value: "Purastone Venatino", source: "brief" },
          { field: "Tipo de trabajo", value: "Cocina", source: "brief" },
        ],
      },
    });
    expect(ctx.cliente.value).toBe("Cueto-Heredia");
    expect(ctx.cliente.origin).toBe("BRIEF");
    expect(ctx.localidad.value).toBe("Rosario");
    expect(ctx.localidad.origin).toBe("BRIEF");
    expect(ctx.material.value).toBe("Purastone Venatino");
    expect(ctx.material.origin).toBe("BRIEF");
  });

  test("data_known con source='quote' → BRIEF (Bug 3 deuda)", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        data_known: [{ field: "Cliente", value: "Estudio Vidal", source: "quote" }],
      },
    });
    expect(ctx.cliente.value).toBe("Estudio Vidal");
    expect(ctx.cliente.origin).toBe("BRIEF");
  });

  test("assumptions con Zócalos / Pileta → mapeo a INFERIDO con source rule", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        assumptions: [
          {
            field: "Zócalos",
            value: "Trasero por tramo, 7 cm",
            source: "config_default",
          },
          { field: "Pileta", value: "empotrada", source: "inferred" },
        ],
      },
    });
    expect(ctx.zocalo.value).toBe("Trasero por tramo, 7 cm");
    expect(ctx.zocalo.origin).toBe("DEFAULT");
    expect(ctx.pileta.value).toBe("empotrada");
    expect(ctx.pileta.origin).toBe("INFERIDO");
  });
});

describe("breakdownToContext · precedencia verified > pending > raw", () => {
  test("verified gana sobre pending para el mismo field", () => {
    const ctx = breakdownToContext({
      verified_context_analysis: {
        data_known: [{ field: "Localidad", value: "CABA · Belgrano", source: "quote" }],
      },
      context_analysis_pending: {
        data_known: [{ field: "Localidad", value: "Rosario", source: "brief" }],
      },
    });
    expect(ctx.localidad.value).toBe("CABA · Belgrano");
  });

  test("pending wins cuando verified no tiene el field", () => {
    const ctx = breakdownToContext({
      verified_context_analysis: { data_known: [] },
      context_analysis_pending: {
        data_known: [{ field: "Localidad", value: "Rosario", source: "brief" }],
      },
    });
    expect(ctx.localidad.value).toBe("Rosario");
  });

  test("raw fallback cuando ningún analysis tiene el field", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: {
        localidad: "Rosario",
        material: "Purastone Venatino",
        client_name: "Familia X",
      },
    });
    expect(ctx.localidad.value).toBe("Rosario");
    expect(ctx.localidad.origin).toBe("BRIEF");
    expect(ctx.material.value).toBe("Purastone Venatino");
    expect(ctx.cliente.value).toBe("Familia X");
  });
});

describe("breakdownToContext · derived fields", () => {
  test("work_types[] array → tipologia concatenado con ', '", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { work_types: ["cocina", "baño"] },
    });
    expect(ctx.tipologia.value).toBe("cocina, baño");
    expect(ctx.tipologia.origin).toBe("BRIEF");
  });

  test("work_types vacío → FALTA", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { work_types: [] },
    });
    expect(ctx.tipologia.origin).toBe("FALTA");
  });

  test("es_edificio=true → tipo_obra='edificio' BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { es_edificio: true },
    });
    expect(ctx.tipo_obra.value).toBe("edificio");
    expect(ctx.tipo_obra.origin).toBe("BRIEF");
  });

  test("es_edificio=false → tipo_obra='particular' BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { es_edificio: false },
    });
    expect(ctx.tipo_obra.value).toBe("particular");
    expect(ctx.tipo_obra.origin).toBe("BRIEF");
  });

  test("regrueso_mentioned=true → 'Sí' BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { regrueso_mentioned: true },
    });
    expect(ctx.regrueso.value).toBe("Sí");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });

  test("anafe_mentioned=true → boolean true BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { anafe_mentioned: true },
    });
    expect(ctx.anafe.value).toBe(true);
    expect(ctx.anafe.origin).toBe("BRIEF");
  });

  test("pileta_type fallback al raw cuando no hay assumption", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { pileta_type: "Johnson PEGADOPILETA" },
    });
    expect(ctx.pileta.value).toBe("Johnson PEGADOPILETA");
    expect(ctx.pileta.origin).toBe("BRIEF");
  });

  test("demora_dias number → plazo formateado con 'días'", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { demora_dias: 15 },
    });
    expect(ctx.plazo.value).toBe("15 días");
    expect(ctx.plazo.origin).toBe("BRIEF");
  });
});

describe("breakdownToContext · contacto siempre FALTA (deuda documentada)", () => {
  test("contacto siempre null + FALTA · backend no extrae phone/email", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        data_known: [
          // Mock backend hipotético: incluso si trajera Contacto, lo
          // ignoramos en este sub-PR.
          { field: "Contacto", value: "+54 11 1234-5678", source: "brief" },
        ],
      },
    });
    expect(ctx.contacto.value).toBeNull();
    expect(ctx.contacto.origin).toBe("FALTA");
  });
});

describe("breakdownToContext · canon real PRES-2026-018 shape", () => {
  test("shape realista del audit log de Javi (Mesada 2x0.60 purastone)", () => {
    // Replicar el shape que el backend devuelve para la prueba real
    // post-PR #482 (smoke test).
    const ctx = breakdownToContext({
      context_analysis_pending: {
        data_known: [
          { field: "Material", value: "Purastone Venatino", source: "brief" },
          { field: "Localidad", value: "Rosario", source: "brief" },
          { field: "Tipo de trabajo", value: "Cocina", source: "brief" },
        ],
        assumptions: [
          {
            field: "Zócalos",
            value: "Trasero por tramo, 7 cm",
            source: "config_default",
            note: "default del config si no se especifica",
          },
          {
            field: "Colocación",
            value: "Incluida",
            source: "brief",
          },
        ],
      },
      _brief_analysis_raw: {
        material: "Purastone Venatino",
        localidad: "Rosario",
        work_types: ["cocina"],
        zocalos: "Trasero",
        alzada: "sí",
        colocacion: "sí",
        es_edificio: false,
      },
    });
    expect(ctx.material.value).toBe("Purastone Venatino");
    expect(ctx.material.origin).toBe("BRIEF");
    expect(ctx.localidad.value).toBe("Rosario");
    expect(ctx.localidad.origin).toBe("BRIEF");
    expect(ctx.tipologia.value).toBe("cocina");
    expect(ctx.zocalo.value).toBe("Trasero por tramo, 7 cm");
    expect(ctx.zocalo.origin).toBe("DEFAULT");
    expect(ctx.tipo_obra.value).toBe("particular");
    expect(ctx.tipo_obra.origin).toBe("BRIEF");
  });
});
