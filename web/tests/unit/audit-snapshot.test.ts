/**
 * Unit tests · Sprint 4 audit-copy-3-layer-state · registry module-level.
 *
 * Cubre el caveat anti-stale: getSnapshot solo devuelve si el quoteId pedido
 * matchea el registrado (evita que el 📋 del Topbar copie un snapshot viejo
 * tras navegar a otro quote).
 */
import { afterEach, describe, expect, test } from "vitest";
import {
  registerSnapshot,
  unregisterSnapshot,
  getSnapshot,
  _resetSnapshotRegistry,
  type AuditSnapshot,
} from "@/lib/audit-snapshot";

const SNAP: AuditSnapshot = {
  step: "/contexto",
  contextResponse: null,
  uiRender: [{ title: "Detalles", fields: [] }],
};

afterEach(() => {
  _resetSnapshotRegistry();
});

describe("audit-snapshot registry", () => {
  test("register + get con mismo quoteId → devuelve el snapshot", () => {
    registerSnapshot("quote-A", SNAP);
    expect(getSnapshot("quote-A")).toBe(SNAP);
  });

  test("register quote A + get con quote B → null (anti-stale)", () => {
    registerSnapshot("quote-A", SNAP);
    expect(getSnapshot("quote-B")).toBeNull();
  });

  test("unregister → get devuelve null", () => {
    registerSnapshot("quote-A", SNAP);
    unregisterSnapshot("quote-A");
    expect(getSnapshot("quote-A")).toBeNull();
  });

  test("unregister de otro quoteId NO borra el activo (unmount tardío)", () => {
    registerSnapshot("quote-A", SNAP);
    // La página vieja (quote-B) se desmonta tarde · NO debe limpiar quote-A.
    unregisterSnapshot("quote-B");
    expect(getSnapshot("quote-A")).toBe(SNAP);
  });

  test("getSnapshot con quoteId vacío → null", () => {
    registerSnapshot("quote-A", SNAP);
    expect(getSnapshot("")).toBeNull();
  });
});
