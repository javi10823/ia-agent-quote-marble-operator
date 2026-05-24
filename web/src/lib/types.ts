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

/* ─── Sprint 2 paso-2-contexto · chat scoped + context form ─────────── */

export type ContextFormState = "loading" | "idle" | "saving" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "valentina";
  content: string;
  timestamp: string;
  /** true mientras la respuesta de Valentina se está streameando. */
  partial?: boolean;
}

export type ChatPanelState = "closed" | "open" | "streaming";

/* ─── Sprint 3 paso-3-despiece · state machine + chat scope ─────────── */

/** Estado del container del paso 3 (DespieceView).
 *  - loading: carga inicial de piezas (skeleton + timeline running)
 *  - idle: piezas cargadas, sin operación en curso
 *  - editing: una celda está en edit mode (Tab/Enter/Esc)
 *  - saving: persistiendo un update/add/delete
 *  - regenerating: Valentina re-corre la inferencia
 *  - error: fallo de carga
 */
export type DespieceFormState =
  | "loading"
  | "idle"
  | "editing"
  | "saving"
  | "regenerating"
  | "error";

/** Scope del chat del paso 3: sobre el paso completo, o enfocado en 1 pieza
 *  (mockup 06 · chat sobre R2 = bacha). */
export type DespieceStreamScope = "despiece" | { scope: "despiece"; target_piece_id: string };
