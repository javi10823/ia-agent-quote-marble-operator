/**
 * Paso 2 · Contexto — implementación del flujo (mockups 01/02/03).
 *
 * Reemplaza el placeholder del PR #456 chrome-refactor. Renderiza el
 * container client `ContextView` que coordina el form de 11 campos
 * con el chat scoped 480px.
 *
 * Mock-first: el client simulado en lib/v2/api.ts cubre los endpoints
 * dedicados que están marcados como faltantes en
 * docs/handoff-context/missing-endpoints.md (PATCH context + chat scoped).
 */
import { ContextView } from "@/components/contexto/ContextView";

interface Props {
  params: { id: string };
}

export default function ContextoPage({ params }: Props) {
  return <ContextView quoteId={params.id} />;
}
