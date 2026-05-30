/**
 * Paso 4 · Cálculo · Sprint 3 paso-4-calculo.
 *
 * Reemplaza el placeholder del PR #456. Renderiza el container client
 * `CalculoView` con los 4 estados (loading/A/B/C). Server Component que
 * SOLO pasa quoteId — sin fetch SSR (lección Sprint 3 día 3, getQuoteMetadata
 * real ya tiene fallback; no agregamos más fetches server-side).
 */
import { CalculoView } from "@/components/calculo/CalculoView";

interface Props {
  params: { id: string };
}

export default function CalculoPage({ params }: Props) {
  return <CalculoView quoteId={params.id} />;
}
