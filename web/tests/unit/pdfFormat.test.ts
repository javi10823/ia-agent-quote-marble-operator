/**
 * Unit · helpers paso-5 PDF · Sprint 4 paso-5-pdf-preview.
 * Mockup 18 canon: "Cueto-Heredia Arquitectura - Silestone Blanco Norte - 03.05.2026.pdf"
 */
import { describe, expect, it } from "vitest";
import { formatPdfDate, getPdfFilename, getEnvioSeed } from "@/lib/pdfFormat";

describe("formatPdfDate", () => {
  it("formato dd.mm.yyyy con padding 0", () => {
    expect(formatPdfDate(new Date(2026, 4, 3))).toBe("03.05.2026");
  });
  it("mes 12 sin padding extra", () => {
    expect(formatPdfDate(new Date(2026, 11, 31))).toBe("31.12.2026");
  });
  it("año múltiples dígitos preserva 4", () => {
    expect(formatPdfDate(new Date(2030, 0, 1))).toBe("01.01.2030");
  });
});

describe("getPdfFilename", () => {
  const date = new Date(2026, 4, 3);

  it("formato canónico mockup 18 (pdf)", () => {
    expect(
      getPdfFilename({
        client: "Cueto-Heredia Arquitectura",
        material: "Silestone Blanco Norte",
        date,
        ext: "pdf",
      }),
    ).toBe("Cueto-Heredia Arquitectura - Silestone Blanco Norte - 03.05.2026.pdf");
  });

  it("formato canónico mockup 18 (xlsx)", () => {
    expect(
      getPdfFilename({
        client: "Cueto-Heredia Arquitectura",
        material: "Silestone Blanco Norte",
        date,
        ext: "xlsx",
      }),
    ).toBe("Cueto-Heredia Arquitectura - Silestone Blanco Norte - 03.05.2026.xlsx");
  });

  it("trim de whitespace y collapse múltiples espacios", () => {
    expect(
      getPdfFilename({
        client: "   Cueto-Heredia    Arquitectura  ",
        material: "  Silestone  Blanco   Norte ",
        date,
        ext: "pdf",
      }),
    ).toBe("Cueto-Heredia Arquitectura - Silestone Blanco Norte - 03.05.2026.pdf");
  });

  it("omite client si es em-dash", () => {
    expect(getPdfFilename({ client: "—", material: "Mármol", date, ext: "pdf" })).toBe(
      "Mármol - 03.05.2026.pdf",
    );
  });

  it("omite material si es em-dash", () => {
    expect(getPdfFilename({ client: "Pereyra", material: "—", date, ext: "pdf" })).toBe(
      "Pereyra - 03.05.2026.pdf",
    );
  });

  it("ambos em-dash → solo fecha + ext", () => {
    expect(getPdfFilename({ client: "—", material: "—", date, ext: "pdf" })).toBe("03.05.2026.pdf");
  });

  it("usa fecha de hoy si no se pasa override", () => {
    const result = getPdfFilename({ client: "X", material: "Y", ext: "pdf" });
    // No assert exact date — solo que matchea el patrón dd.mm.yyyy.
    expect(result).toMatch(/^X - Y - \d{2}\.\d{2}\.\d{4}\.pdf$/);
  });
});

describe("getEnvioSeed", () => {
  it("cliente + localidad → 'cliente · localidad'", () => {
    expect(getEnvioSeed({ cliente: "Cueto-Heredia", localidad: "Belgrano" })).toBe(
      "Cueto-Heredia · Belgrano",
    );
  });

  it("solo cliente → cliente", () => {
    expect(getEnvioSeed({ cliente: "Pereyra", localidad: null })).toBe("Pereyra");
  });

  it("solo localidad → localidad", () => {
    expect(getEnvioSeed({ cliente: null, localidad: "Palermo" })).toBe("Palermo");
  });

  it("ambos null → string vacío (no separador huérfano)", () => {
    expect(getEnvioSeed({ cliente: null, localidad: null })).toBe("");
  });

  it("em-dash y whitespace tratados como vacío", () => {
    expect(getEnvioSeed({ cliente: "—", localidad: "   " })).toBe("");
  });

  it("trim de whitespace alrededor de los valores", () => {
    expect(getEnvioSeed({ cliente: "  Cueto-Heredia  ", localidad: " Belgrano " })).toBe(
      "Cueto-Heredia · Belgrano",
    );
  });
});
