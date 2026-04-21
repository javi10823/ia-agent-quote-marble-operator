/**
 * Tests de `pickDefaultOption` — heurística de preselect para preguntas
 * bloqueantes del contexto analysis.
 *
 * Casos cubiertos:
 * - Opción con "estándar" → esa gana (caso feliz Bernardi: profundidad
 *   isla 0.60 m estándar residencial, alto patas 0.90 m estándar).
 * - Sin "estándar" → primera no-custom gana (caso Bernardi: patas,
 *   alzada — ambas arrancan con la opción más común).
 * - Con opciones custom al inicio → saltea hasta encontrar no-custom.
 * - Todas custom / sin opciones → null (no inventamos default).
 * - Mayúsculas/minúsculas y acentos: "Estándar" / "estandar" / "ESTÁNDAR"
 *   todos matchean.
 */
import { describe, it, expect } from "vitest";
import { pickDefaultOption } from "./pickDefaultOption";

describe("pickDefaultOption", () => {
  describe("Regla 1: opción con 'estándar' en el label", () => {
    it("elige la opción marcada como estándar residencial", () => {
      // Caso real: profundidad isla Bernardi
      const options = [
        { value: "0.60", label: "0.60 m (estándar residencial)" },
        { value: "0.70", label: "0.70 m" },
        { value: "0.80", label: "0.80 m" },
        { value: "custom", label: "Otra medida (detallar)" },
      ];
      expect(pickDefaultOption(options)).toBe("0.60");
    });

    it("elige estándar aunque no sea la primera opción", () => {
      // Caso real: alto patas Bernardi
      const options = [
        { value: "0.90", label: "0.90 m (estándar — piso a mesada)" },
        { value: "0.85", label: "0.85 m" },
        { value: "0.80", label: "0.80 m" },
      ];
      expect(pickDefaultOption(options)).toBe("0.90");
    });

    it("matchea case-insensitive: Estándar, ESTÁNDAR, estandar", () => {
      for (const variant of ["Estándar", "ESTÁNDAR", "estándar", "estandar"]) {
        const options = [
          { value: "a", label: "A — algo" },
          { value: "b", label: `B (${variant})` },
        ];
        expect(pickDefaultOption(options)).toBe("b");
      }
    });

    it("si hay varias opciones con 'estándar', elige la primera", () => {
      // Defensivo: no debería pasar en copy real, pero el algoritmo
      // tiene que ser determinístico.
      const options = [
        { value: "primero", label: "Primer estándar" },
        { value: "segundo", label: "Segundo estándar" },
      ];
      expect(pickDefaultOption(options)).toBe("primero");
    });
  });

  describe("Regla 2: sin 'estándar' → primera no-custom", () => {
    it("elige la primera opción cuando no hay custom", () => {
      // Caso real: patas de isla Bernardi
      const options = [
        { value: "frontal_y_ambos", label: "Sí — frontal + ambos laterales" },
        { value: "solo_frontal", label: "Solo frontal" },
        { value: "solo_laterales", label: "Solo ambos laterales" },
        { value: "custom", label: "Otra combinación (detallar lados y alto)" },
        { value: "no", label: "No lleva patas" },
      ];
      expect(pickDefaultOption(options)).toBe("frontal_y_ambos");
    });

    it("alzada: 'No lleva' como primera opción", () => {
      // Caso real: alzada Bernardi
      const options = [
        { value: "no", label: "No lleva" },
        { value: "5cm", label: "Sí — 5 cm" },
        { value: "10cm", label: "Sí — 10 cm" },
        { value: "custom", label: "Sí — otro alto (detallar)" },
      ];
      expect(pickDefaultOption(options)).toBe("no");
    });

    it("saltea opciones custom al buscar la primera", () => {
      const options = [
        { value: "custom", label: "Otra medida (detallar)" },
        { value: "a", label: "Opción A" },
        { value: "b", label: "Opción B" },
      ];
      expect(pickDefaultOption(options)).toBe("a");
    });

    it("detecta custom por value='custom' aunque el label no diga 'detallar'", () => {
      const options = [
        { value: "custom", label: "Personalizar" },
        { value: "default", label: "Default" },
      ];
      expect(pickDefaultOption(options)).toBe("default");
    });

    it("detecta custom por label con 'otra' (ej: 'Otra combinación')", () => {
      const options = [
        { value: "otra_combinacion", label: "Otra combinación (detallar)" },
        { value: "a", label: "Opción A" },
      ];
      expect(pickDefaultOption(options)).toBe("a");
    });
  });

  describe("Regla 3: edge cases", () => {
    it("devuelve null si options es undefined", () => {
      expect(pickDefaultOption(undefined)).toBeNull();
    });

    it("devuelve null si options es vacío", () => {
      expect(pickDefaultOption([])).toBeNull();
    });

    it("devuelve null si todas las opciones son custom", () => {
      const options = [
        { value: "custom", label: "Otra medida (detallar)" },
        { value: "otro_custom", label: "Otra más (detallar)" },
      ];
      expect(pickDefaultOption(options)).toBeNull();
    });
  });

  describe("Integración — coherencia con las 4 preguntas de Bernardi", () => {
    it("cubre exactamente el preselect que el operador hace a mano", () => {
      // Captura de la UI de Javi confirma estos defaults como los que
      // marca el operador en la mayoría de los casos residenciales.
      const profundidad = [
        { value: "0.60", label: "0.60 m (estándar residencial)" },
        { value: "0.70", label: "0.70 m" },
        { value: "0.80", label: "0.80 m" },
        { value: "custom", label: "Otra medida (detallar)" },
      ];
      const patas = [
        { value: "frontal_y_laterales", label: "Sí — frontal + ambos laterales" },
        { value: "solo_frontal", label: "Solo frontal" },
        { value: "solo_laterales", label: "Solo ambos laterales" },
        { value: "custom", label: "Otra combinación (detallar lados y alto)" },
        { value: "no", label: "No lleva patas" },
      ];
      const altoPatas = [
        { value: "0.90", label: "0.90 m (estándar — piso a mesada)" },
        { value: "0.85", label: "0.85 m" },
        { value: "0.80", label: "0.80 m" },
        { value: "custom", label: "Otra medida (detallar)" },
      ];
      const alzada = [
        { value: "no", label: "No lleva" },
        { value: "5cm", label: "Sí — 5 cm" },
        { value: "10cm", label: "Sí — 10 cm" },
        { value: "custom", label: "Sí — otro alto (detallar)" },
      ];
      expect(pickDefaultOption(profundidad)).toBe("0.60");
      expect(pickDefaultOption(patas)).toBe("frontal_y_laterales");
      expect(pickDefaultOption(altoPatas)).toBe("0.90");
      expect(pickDefaultOption(alzada)).toBe("no");
    });
  });
});
