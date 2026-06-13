/**
 * Home `/` · Sprint 2.5 switch-to-main.
 *
 * Bloque E del Master §6 — dashboard funcional (mockup 25 desktop +
 * mockup 23 mobile). Reemplaza el placeholder de saludo Valentina del
 * draft inicial de Sprint 2.5 por la implementación canon.
 *
 * Mock-first: el endpoint `GET /api/v1/quotes` está marcado como
 * missing en docs/handoff-context/missing-endpoints.md. El client
 * sirve DASHBOARD_QUOTES (16 visibles · counters totales 47).
 */
import { DashboardView } from "@/components/dashboard/DashboardView";

export default function HomePage() {
  return <DashboardView />;
}
