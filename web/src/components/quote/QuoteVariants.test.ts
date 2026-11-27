import { describe, expect, it } from "vitest";
import { variantLabel } from "./QuoteVariants";

describe("variantLabel", () => {
  it("material + total", () => {
    const label = variantLabel({
      id: "a",
      material: "Silestone Blanco",
      total_ars: 1234567,
      total_usd: 0,
      status: "draft",
    });
    expect(label.startsWith("Silestone Blanco · $")).toBe(true);
    expect(label.replace(/\D/g, "")).toBe("1234567");
  });

  it("sin total ni material", () => {
    expect(
      variantLabel({ id: "a", material: "", total_ars: 0, total_usd: 0, status: "draft" }),
    ).toBe("Sin material");
  });
});
