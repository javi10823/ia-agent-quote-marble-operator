/**
 * Paso 3 · Despiece (mockups 04/05/06/16).
 *
 * Reemplaza el placeholder del PR #456 chrome-refactor. Renderiza el
 * container client `DespieceView`, que coordina la tabla de piezas
 * editable + timeline de pasadas + chat scoped.
 *
 * Mock-first: el client de piezas vive en lib/api.ts (cubre el endpoint
 * dedicado del paso 3 todavía inexistente). El switch a HTTP real es
 * sprint-3/api-integration.
 *
 * NOTA: el quote (Topbar/Qhead) lo resuelve [id]/layout.tsx via
 * getQuoteMetadata(params.id) — NO se duplica acá (fix-up #2 del PR #460).
 */
import { DespieceView } from "@/components/despiece/DespieceView";

interface Props {
  params: { id: string };
}

export default function DespiecePage({ params }: Props) {
  return <DespieceView quoteId={params.id} />;
}
