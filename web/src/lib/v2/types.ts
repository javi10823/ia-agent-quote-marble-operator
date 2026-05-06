/**
 * Tipos compartidos del v2.
 *
 * Sprint 2 paso-1-brief-upload: tipos del state machine del paso 1.
 * Más tipos van a salir de `docs/handoff-context/schemas/*.md` en
 * sub-PRs siguientes (paso-2-contexto, paso-3-despiece, etc.).
 */

/** Estado del state machine del paso 1 (mockups 00 A/B/C). */
export type BriefUploadState = "idle" | "submitting" | "error";

/** Form data del paso 1 antes de submit. */
export interface BriefFormData {
  planFile: File | null;
  photos: File[];
  briefText: string;
}
