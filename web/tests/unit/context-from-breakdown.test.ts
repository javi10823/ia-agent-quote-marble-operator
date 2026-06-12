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
    // Sub-PR Bug 7 · ajuste: el backend NO emite assumption con field
    // exacto `"Pileta"`. Los nombres reales son `"Pileta — montaje"`,
    // `"Pileta (tipo de montaje)"`, `"Pileta — bachas"`, `"Pileta —
    // marca"`. Para la regla cocina→empotrada (source="rule"), el
    // backend usa `"Pileta (tipo de montaje)"` (líneas 218-223 de
    // context_analyzer.py). Tests específicos de los 4 nombres reales
    // viven en el bloque "Bug 7 · pileta · assumption name canónico
    // backend" abajo. Acá lo dejamos cubierto con el caso regla.
    const ctx = breakdownToContext({
      context_analysis_pending: {
        assumptions: [
          {
            field: "Zócalos",
            value: "Trasero por tramo, 7 cm",
            source: "config_default",
          },
          {
            field: "Pileta (tipo de montaje)",
            value: "Empotrada (PEGADOPILETA)",
            source: "rule",
          },
        ],
      },
    });
    expect(ctx.zocalo.value).toBe("Trasero por tramo, 7 cm");
    expect(ctx.zocalo.origin).toBe("DEFAULT");
    expect(ctx.pileta.value).toBe("Empotrada (PEGADOPILETA)");
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

  // Test legacy migrado · sub-PR Bug 7. El schema viejo era
  // `regrueso_mentioned: bool` (deprecated por PR #485). Hoy el
  // backend devuelve `regrueso: "yes" as const|"no"|null` y el adapter combina
  // con `frentin`. Ver tests ternary abajo.

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

// ─────────────────────────────────────────────────────────────────────
// Sub-PR sprint-4/contacto-extraction-fix · activación deuda PR #483
//
// Antes: el adapter hardcodeaba `contacto = null + FALTA` con comentario
// "deuda · backend no extrae phone/email del brief". Hoy el backend
// (brief_analyzer + context_analyzer) extrae phone+email y genera
// data_known entry "Contacto" con value formateado. El adapter ahora
// usa resolveString igual que Cliente / Localidad / Material.
//
// Shape REAL del backend (lección #60): el data_known entry vive
// anidado dentro de `context_analysis_pending`.
// ─────────────────────────────────────────────────────────────────────

describe("contacto-extraction-fix · contacto del backend canon", () => {
  test("data_known 'Contacto' nested → contacto populated + BRIEF", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        data_known: [
          {
            field: "Contacto",
            value: "Tel: 3464696027 · Email: micaela@ejemplo.com",
            source: "brief",
          },
        ],
      },
    });
    expect(ctx.contacto.value).toBe(
      "Tel: 3464696027 · Email: micaela@ejemplo.com",
    );
    expect(ctx.contacto.origin).toBe("BRIEF");
  });

  test("data_known 'Contacto' phone only → 'Tel: X' + BRIEF", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        data_known: [
          { field: "Contacto", value: "Tel: 3464696027", source: "brief" },
        ],
      },
    });
    expect(ctx.contacto.value).toBe("Tel: 3464696027");
    expect(ctx.contacto.origin).toBe("BRIEF");
  });

  test("sin data_known 'Contacto' → contacto null + FALTA (current UX preservada)", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        data_known: [
          { field: "Cliente", value: "Juan", source: "brief" },
        ],
      },
    });
    expect(ctx.contacto.value).toBeNull();
    expect(ctx.contacto.origin).toBe("FALTA");
  });

  test("regression · audit literal Micaela post-fix · 3 fields contacto-relacionados", () => {
    // Anclaje al dump literal esperado post-deploy (lección #60).
    // Si el backend cambia su shape, este test rompe primero.
    const ctx = breakdownToContext({
      context_analysis_pending: {
        data_known: [
          { field: "Cliente", value: "Micaela Volattire", source: "brief" },
          {
            field: "Contacto",
            value:
              "Tel: 3464696027 · Email: micaelavolattire.1234@gmail.com",
            source: "brief",
          },
          { field: "Localidad", value: "Casilda", source: "brief" },
          { field: "Material", value: "Granito Gris Perla", source: "brief" },
        ],
        _brief_analysis_raw: {
          client_name: "Micaela Volattire",
          phone: "3464696027",
          email: "micaelavolattire.1234@gmail.com",
          localidad: "Casilda",
          material: "Granito Gris Perla",
        },
      },
    });
    expect(ctx.cliente.value).toBe("Micaela Volattire");
    expect(ctx.contacto.value).toBe(
      "Tel: 3464696027 · Email: micaelavolattire.1234@gmail.com",
    );
    expect(ctx.contacto.origin).toBe("BRIEF");
    expect(ctx.localidad.value).toBe("Casilda");
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

// ─────────────────────────────────────────────────────────────────────
// Sub-PR Bug 7 · adapter sync post-PR #485
//
// PR #485 migró el schema brief_analyzer de bool a ternary:
//   frentin_mentioned: bool → frentin: "yes" as const | "no" | null
//   regrueso_mentioned: bool → regrueso: "yes" as const | "no" | null
//
// El adapter no se había actualizado · sub-PR Bug 7 cierra esa deuda
// + agrega lectura de `frentin` (que NUNCA estuvo cubierta en PR #483
// inicial — el UI siempre mostró "—" para el field combinado).
// ─────────────────────────────────────────────────────────────────────

describe("Bug 7 · frentin/regrueso ternary · matriz combinación", () => {
  test("null/null → null + FALTA", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { frentin: null, regrueso: null },
    });
    expect(ctx.regrueso.value).toBeNull();
    expect(ctx.regrueso.origin).toBe("FALTA");
  });

  test("no/no → 'No lleva' + BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { frentin: "no" as const, regrueso: "no" as const },
    });
    expect(ctx.regrueso.value).toBe("No lleva");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });

  test("yes/yes → 'Frentín + Regrueso' + BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { frentin: "yes" as const, regrueso: "yes" as const },
    });
    expect(ctx.regrueso.value).toBe("Frentín + Regrueso");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });

  test("yes/no disjoint → 'Frentín: Sí · Regrueso: No' + BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { frentin: "yes" as const, regrueso: "no" as const },
    });
    expect(ctx.regrueso.value).toBe("Frentín: Sí · Regrueso: No");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });

  test("no/yes disjoint → 'Frentín: No · Regrueso: Sí' + BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { frentin: "no" as const, regrueso: "yes" as const },
    });
    expect(ctx.regrueso.value).toBe("Frentín: No · Regrueso: Sí");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });

  test("yes/null partial → 'Frentín: Sí · Regrueso: —' + BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { frentin: "yes" as const, regrueso: null },
    });
    expect(ctx.regrueso.value).toBe("Frentín: Sí · Regrueso: —");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });

  test("null/yes partial → 'Frentín: — · Regrueso: Sí' + BRIEF", () => {
    const ctx = breakdownToContext({
      _brief_analysis_raw: { frentin: null, regrueso: "yes" as const },
    });
    expect(ctx.regrueso.value).toBe("Frentín: — · Regrueso: Sí");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });
});

describe("Bug 7 · pileta · assumption name canónico backend", () => {
  test("'Pileta — montaje' (post bug 4 fix) → mapping correcto", () => {
    // Caso brief Micaela post-PR #484: backend genera assumption con
    // este field exacto cuando brief declara pileta_type.
    const ctx = breakdownToContext({
      context_analysis_pending: {
        assumptions: [
          {
            field: "Pileta — montaje",
            value: "Apoyo",
            source: "brief",
            note: "Excepción a la regla D'Angelo",
          },
        ],
      },
    });
    expect(ctx.pileta.value).toBe("Apoyo");
    expect(ctx.pileta.origin).toBe("BRIEF");
  });

  test("'Pileta (tipo de montaje)' (regla cocina→empotrada) → INFERIDO", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        assumptions: [
          {
            field: "Pileta (tipo de montaje)",
            value: "Empotrada (PEGADOPILETA)",
            source: "rule",
          },
        ],
      },
    });
    expect(ctx.pileta.value).toBe("Empotrada (PEGADOPILETA)");
    expect(ctx.pileta.origin).toBe("INFERIDO");
  });

  test("'Pileta — montaje' tiene prioridad sobre 'Pileta (tipo de montaje)'", () => {
    // Si el operador declaró pileta_type explícito (echo del brief), gana
    // sobre la regla. Replica el mismo patrón brief > rule del backend.
    const ctx = breakdownToContext({
      context_analysis_pending: {
        assumptions: [
          {
            field: "Pileta (tipo de montaje)",
            value: "Empotrada (PEGADOPILETA)",
            source: "rule",
          },
          {
            field: "Pileta — montaje",
            value: "Apoyo",
            source: "brief",
          },
        ],
      },
    });
    expect(ctx.pileta.value).toBe("Apoyo");
    expect(ctx.pileta.origin).toBe("BRIEF");
  });
});

describe("Bug 7 · drift guard · adapter no resucita schemas obsoletos", () => {
  test("regression: el adapter NO lee `regrueso_mentioned` (PR #485 deprecated)", () => {
    // Si alguien resucita el field viejo en un commit futuro y NO
    // setea `regrueso` (nuevo), el adapter debe igualmente caer a
    // FALTA — no debe revivir el comportamiento pre-#485.
    // Cast a Record para inyectar key legacy sin romper TypeScript
    // (BriefAnalysisRaw tiene `[key: string]: unknown` que la admite,
    // pero queremos que el test sea explícito sobre que es legacy).
    const ctx = breakdownToContext({
      _brief_analysis_raw: { regrueso_mentioned: true } as Record<string, unknown>,
    });
    expect(ctx.regrueso.origin).toBe("FALTA");
    expect(ctx.regrueso.value).toBeNull();
  });

  test("regression: el adapter NO lee `frentin_mentioned`", () => {
    // `frentin_mentioned` NUNCA existió en el adapter — drift guard
    // contra resurrección futura del schema obsoleto.
    const ctx = breakdownToContext({
      _brief_analysis_raw: { frentin_mentioned: true } as Record<string, unknown>,
    });
    expect(ctx.regrueso.origin).toBe("FALTA");
    expect(ctx.regrueso.value).toBeNull();
  });
});

describe("Bug 7 · smoke E2E · brief Micaela post-PR #485", () => {
  test("shape real prod · pileta apoyo + frentin/regrueso ambos no", () => {
    // Replica el shape que el backend devuelve para el brief Micaela
    // post-PR #485 + PR #484. Pre-fix: pileta=—, frentin/regrueso=—.
    // Post-fix: pileta="Apoyo" + regrueso="No lleva".
    const ctx = breakdownToContext({
      context_analysis_pending: {
        data_known: [
          { field: "Cliente", value: "Micaela Volattire", source: "brief" },
          { field: "Material", value: "Granito Gris Perla", source: "brief" },
          { field: "Localidad", value: "Casilda", source: "brief" },
          { field: "Tipo de trabajo", value: "Cocina", source: "brief" },
        ],
        assumptions: [
          {
            field: "Pileta — montaje",
            value: "Apoyo",
            source: "brief",
            note: "Excepción a la regla D'Angelo (cocina normalmente empotrada).",
          },
          { field: "Zócalos", value: "Trasero por tramo, 5 cm", source: "brief+rule" },
          { field: "Frentín", value: "No lleva", source: "brief" },
          { field: "Regrueso", value: "No lleva", source: "brief" },
        ],
      },
      _brief_analysis_raw: {
        client_name: "Micaela Volattire",
        material: "Granito Gris Perla",
        localidad: "Casilda",
        work_types: ["cocina"],
        pileta_type: "apoyo",
        frentin: "no" as const,
        regrueso: "no" as const,
        pulido: null,
        anafe_mentioned: false,
        es_edificio: false,
      },
    });
    expect(ctx.cliente.value).toBe("Micaela Volattire");
    expect(ctx.localidad.value).toBe("Casilda");
    expect(ctx.material.value).toBe("Granito Gris Perla");
    expect(ctx.pileta.value).toBe("Apoyo");
    expect(ctx.pileta.origin).toBe("BRIEF");
    expect(ctx.regrueso.value).toBe("No lleva");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });
});

// ─────────────────────────────────────────────────────────────────────
// Bug 7 RESIDUAL · adapter leía _brief_analysis_raw desde top-level
// cuando el backend lo emite SIEMPRE anidado dentro de
// context_analysis_pending (o verified_context_analysis).
//
// Pre-existente desde PR #483 · oculto en prod hasta brief de Micaela
// porque Cliente/Material/Pileta/etc. tienen fallback a data_known +
// assumptions. Frentín/Regrueso/Anafe SOLO leen del raw → caían a FALTA.
//
// Tests del PR #486 cubrían shape FICTICIA top-level (legacy compat).
// Los tests abajo replican el SHAPE REAL emitido por el backend:
//   { context_analysis_pending: { _brief_analysis_raw: {...} } }
//
// Lección operativa #60: las fixtures de tests del adapter deben
// REPLICAR shape REAL del upstream. Si la fixture difiere del shape de
// prod, el test no certifica nada · drift silencioso.
// ─────────────────────────────────────────────────────────────────────

describe("Bug 7 RESIDUAL · _brief_analysis_raw anidado (shape REAL del backend)", () => {
  test("regression · audit literal Micaela · prod 2026-06-12", () => {
    // Dump literal del audit-log de prod (quote d8e85524) confirmado
    // por Javi. Si este test rompe, el backend cambió su shape · NO
    // tocar el adapter sin coordinación.
    const realBackendShape = {
      dual_read_result: { sectores: [{ id: "sector_1", tipo: "cocina" }] },
      context_analysis_pending: {
        data_known: [
          { field: "Cliente", value: "Micaela Volattire", source: "brief" },
          { field: "Material", value: "Granito Gris Perla", source: "quote" },
          { field: "Localidad", value: "Casilda", source: "brief" },
          { field: "Tipo de trabajo", value: "Cocina", source: "brief" },
        ],
        assumptions: [
          {
            field: "Zócalos",
            value: "Trasero por tramo, 5 cm",
            source: "brief+rule",
          },
          { field: "Colocación", value: "No incluye", source: "brief" },
          {
            field: "Pileta — montaje",
            value: "Apoyo",
            source: "brief",
          },
          { field: "Forma de pago", value: "Contado", source: "config_default" },
          { field: "Demora", value: "30 días", source: "config_default" },
          { field: "Tipo", value: "Particular", source: "inferred" },
          { field: "Descuento", value: "No aplica", source: "config_default" },
          { field: "Frentín", value: "No lleva", source: "brief" },
          { field: "Regrueso", value: "No lleva", source: "brief" },
        ],
        _brief_analysis_raw: {
          client_name: "Micaela Volattire",
          project: null,
          material: "Granito Gris Perla",
          localidad: "Casilda",
          work_types: ["cocina"],
          zocalos: "yes",
          zocalos_alto_cm: 5,
          alzada: "yes",
          colocacion: "no",
          pileta_mentioned: true,
          pileta_type: "apoyo",
          anafe_mentioned: true,
          anafe_count: null,
          frentin: "no" as const,
          regrueso: "no" as const,
          pulido: null,
          es_edificio: false,
        },
      },
    };
    const ctx = breakdownToContext(realBackendShape);

    // Campos que ya funcionaban (vienen de pending.data_known / assumptions)
    expect(ctx.cliente.value).toBe("Micaela Volattire");
    expect(ctx.cliente.origin).toBe("BRIEF");
    expect(ctx.localidad.value).toBe("Casilda");
    expect(ctx.localidad.origin).toBe("BRIEF");
    expect(ctx.material.value).toBe("Granito Gris Perla");
    expect(ctx.material.origin).toBe("BRIEF"); // source=quote → BRIEF
    expect(ctx.pileta.value).toBe("Apoyo");
    expect(ctx.pileta.origin).toBe("BRIEF");
    expect(ctx.zocalo.value).toBe("Trasero por tramo, 5 cm");

    // Campos rotos por Bug 7 RESIDUAL · ahora deben funcionar
    expect(ctx.regrueso.value).toBe("No lleva");
    expect(ctx.regrueso.origin).toBe("BRIEF");
    expect(ctx.anafe.value).toBe(true);
    expect(ctx.anafe.origin).toBe("BRIEF");

    // tipo_obra: es_edificio=false → "particular" + BRIEF
    expect(ctx.tipo_obra.value).toBe("particular");
    expect(ctx.tipo_obra.origin).toBe("BRIEF");
  });

  test("frentin/regrueso en pending._brief_analysis_raw nested · no/no → No lleva BRIEF", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        _brief_analysis_raw: { frentin: "no" as const, regrueso: "no" as const },
      },
    });
    expect(ctx.regrueso.value).toBe("No lleva");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });

  test("anafe_mentioned=true nested → true + BRIEF", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        _brief_analysis_raw: { anafe_mentioned: true },
      },
    });
    expect(ctx.anafe.value).toBe(true);
    expect(ctx.anafe.origin).toBe("BRIEF");
  });

  test("anafe nested NO impacta tipo_obra (regresión cross-field)", () => {
    const ctx = breakdownToContext({
      context_analysis_pending: {
        _brief_analysis_raw: { anafe_mentioned: true, es_edificio: true },
      },
    });
    expect(ctx.anafe.value).toBe(true);
    expect(ctx.tipo_obra.value).toBe("edificio");
    expect(ctx.tipo_obra.origin).toBe("BRIEF");
  });
});

describe("Bug 7 RESIDUAL · precedencia verified > pending > top-level (drift guard)", () => {
  test("verified gana sobre pending para _brief_analysis_raw", () => {
    const breakdown = {
      context_analysis_pending: {
        _brief_analysis_raw: { frentin: "no" as const, regrueso: "no" as const },
      },
      verified_context_analysis: {
        _brief_analysis_raw: { frentin: "yes" as const, regrueso: "yes" as const },
      },
    };
    const ctx = breakdownToContext(breakdown);
    // verified gana → yes/yes → "Frentín + Regrueso"
    expect(ctx.regrueso.value).toBe("Frentín + Regrueso");
    expect(ctx.regrueso.origin).toBe("BRIEF");
  });

  test("pending gana sobre top-level legacy", () => {
    const breakdown = {
      _brief_analysis_raw: { frentin: "yes" as const, regrueso: "yes" as const }, // top-level legacy
      context_analysis_pending: {
        _brief_analysis_raw: { frentin: "no" as const, regrueso: "no" as const }, // pending real
      },
    };
    const ctx = breakdownToContext(breakdown);
    // pending gana → no/no → "No lleva"
    expect(ctx.regrueso.value).toBe("No lleva");
  });

  test("backwards compat · top-level _brief_analysis_raw sigue funcionando", () => {
    // Quotes viejos o tests legacy podrían tener el raw en top-level
    // del breakdown. El adapter debe seguir aceptándolo como 3er
    // fallback (NO romper compat retroactiva).
    const ctx = breakdownToContext({
      _brief_analysis_raw: {
        frentin: "no" as const,
        regrueso: "no" as const,
        anafe_mentioned: true,
      },
    });
    expect(ctx.regrueso.value).toBe("No lleva");
    expect(ctx.anafe.value).toBe(true);
  });

  test("verified vacío + pending con raw → usa pending (no se confunde con verified)", () => {
    const ctx = breakdownToContext({
      verified_context_analysis: { data_known: [] }, // sin _brief_analysis_raw
      context_analysis_pending: {
        _brief_analysis_raw: { anafe_mentioned: true },
      },
    });
    expect(ctx.anafe.value).toBe(true);
  });
});
