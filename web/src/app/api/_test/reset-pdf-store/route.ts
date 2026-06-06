/**
 * Route Handler de testing · Sprint 4 paso-5-c-generado.
 *
 * Resetea el `_generatedStore` in-memory del mock `triggerPdfGeneration`
 * (mocks.ts) para evitar cross-talk entre tests E2E que corren en paralelo
 * contra el mismo Next dev server. Solo expuesto en dev/test · en producción
 * el endpoint retorna 404 (no hace nada útil porque el mock no existe).
 */
import { NextResponse } from "next/server";
import { _resetGeneratedStore } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function POST() {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json({ ok: false, reason: "disabled-in-prod" }, { status: 404 });
  }
  _resetGeneratedStore();
  return NextResponse.json({ ok: true });
}
