/**
 * Unit del helper Qhead · Sprint 3 qhead-empty-title.
 *
 * Cubre los 4 niveles de fallback del título + las 4 combinaciones del sub.
 * MINOR #10 audit CFC PR #465 ("título muestra '— — —'") + extensión Javi
 * (mismo principio aplicado al sub `id · material · m²`).
 */
import { describe, expect, it } from "vitest";
import type { QuoteHeader } from "@/lib/api";
import { getQuoteDisplayName, getQuoteDisplaySub } from "@/lib/qheadFallback";

function make(overrides: Partial<QuoteHeader> = {}): QuoteHeader {
  return {
    id: "PRES-2026-018",
    client: "Cueto-Heredia",
    clientFull: "Estudio Cueto-Heredia",
    material: "Granito Negro Brasil",
    m2: 8.4,
    status: "sent",
    ...overrides,
  };
}

describe("getQuoteDisplayName", () => {
  it("nivel 1 · ambos válidos distintos → 'clientFull — client'", () => {
    expect(getQuoteDisplayName(make())).toBe("Estudio Cueto-Heredia — Cueto-Heredia");
  });

  it("nivel 1 · ambos válidos iguales → muestra uno solo (sin duplicar)", () => {
    expect(getQuoteDisplayName(make({ clientFull: "Pereyra", client: "Pereyra" }))).toBe("Pereyra");
  });

  it("nivel 2 · clientFull válido + client em-dash → clientFull solo", () => {
    expect(getQuoteDisplayName(make({ client: "—" }))).toBe("Estudio Cueto-Heredia");
  });

  it("nivel 3 · clientFull em-dash + client válido → client solo", () => {
    expect(getQuoteDisplayName(make({ clientFull: "—", client: "Cliente sin identificar" }))).toBe(
      "Cliente sin identificar",
    );
  });

  it("nivel 4 · ambos em-dash + ID corto → 'Presupuesto PRES-2026-018'", () => {
    expect(getQuoteDisplayName(make({ clientFull: "—", client: "—" }))).toBe(
      "Presupuesto PRES-2026-018",
    );
  });

  it("nivel 4 · ambos em-dash + UUID largo → 'Presupuesto web-9543be47'", () => {
    expect(
      getQuoteDisplayName(
        make({ id: "web-9543be47-1234-5678-9abc-def012345678", clientFull: "—", client: "—" }),
      ),
    ).toBe("Presupuesto web-9543be47");
  });

  it("nivel 4 · ambos vacíos string → fallback a Presupuesto + ID", () => {
    expect(getQuoteDisplayName(make({ clientFull: "", client: "   " }))).toBe(
      "Presupuesto PRES-2026-018",
    );
  });

  it("no renderea nunca em-dash literal en el output", () => {
    const out = getQuoteDisplayName(make({ clientFull: "—", client: "—" }));
    // El texto puede contener guión normal del 'PRES-' pero no em-dash literal '—'.
    expect(out).not.toMatch(/—/);
  });
});

describe("getQuoteDisplaySub", () => {
  it("ambos válidos → 'id · material · m² m²'", () => {
    expect(getQuoteDisplaySub(make(), "8,40")).toBe(
      "PRES-2026-018 · Granito Negro Brasil · 8,40 m²",
    );
  });

  it("material em-dash + m² válido → 'id · m² m²'", () => {
    expect(getQuoteDisplaySub(make({ material: "—" }), "8,40")).toBe("PRES-2026-018 · 8,40 m²");
  });

  it("material válido + m² em-dash → 'id · material' (sin m²)", () => {
    expect(getQuoteDisplaySub(make(), "—")).toBe("PRES-2026-018 · Granito Negro Brasil");
  });

  it("ambos em-dash → solo el id", () => {
    expect(getQuoteDisplaySub(make({ material: "—" }), "—")).toBe("PRES-2026-018");
  });

  it("UUID en id se preserva (no se acorta como en el título)", () => {
    expect(
      getQuoteDisplaySub(
        make({ id: "web-9543be47-1234-5678-9abc-def012345678", material: "—" }),
        "—",
      ),
    ).toBe("web-9543be47-1234-5678-9abc-def012345678");
  });
});
