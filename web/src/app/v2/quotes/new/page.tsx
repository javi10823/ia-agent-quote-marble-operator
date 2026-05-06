/**
 * `/v2/quotes/new` — paso 1 del flujo (brief upload).
 *
 * Renderiza el container client `BriefView` que coordina los 3
 * estados (A vacío / B form cargado / C procesando).
 *
 * Mock-first: el `createDraftQuote` del lib/v2/api.ts simula el
 * response del backend. Cuando el endpoint dedicado del paso 1
 * se implemente (ver docs/handoff-context/missing-endpoints.md),
 * se hace el swap del cliente sin tocar este componente.
 */
import { BriefView } from "@/components/v2/brief/BriefView";

export default function NewQuotePage() {
  return <BriefView />;
}
