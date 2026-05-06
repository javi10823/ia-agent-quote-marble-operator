/**
 * Smoke unit del scaffold v2.
 *
 * Único objetivo: confirmar que Vitest está cableado y corre.
 */
import { describe, expect, it } from "vitest";

describe("scaffold smoke", () => {
  it("ejecuta una aserción trivial (Vitest vivo)", () => {
    expect(1 + 1).toBe(2);
  });
});
