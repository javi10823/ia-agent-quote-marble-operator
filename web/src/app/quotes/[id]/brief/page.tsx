/**
 * Paso 1 · Brief — redirect a Paso 2 · Contexto.
 *
 * La ruta persiste como safety net. El step `brief` sigue declarado en
 * `STEPS` (canonicalQuote.ts) para preservar la semántica del Stepper.
 */
import { redirect } from "next/navigation";

interface Props {
  params: { id: string };
}

export default function BriefPage({ params }: Props) {
  redirect(`/quotes/${params.id}/contexto`);
}
