/**
 * Container del paso 3 — coordina el state machine del despiece + chat scoped.
 *
 * Estados (mockups 04/05/06/16):
 *   - loading   → skeleton de filas + timeline corriendo (mockup 04-A en carga)
 *   - empty     → IA no propuso piezas → empty-hero (mockup 16 / 04-manual)
 *   - manual    → tabla vacía editable tras "Completar a mano"
 *   - A propuso → tabla de piezas + timeline done (mockup 04-A)
 *   - B editó   → ediciones en púrpura + banner recalculado (mockup 05)
 *   - C chat    → panel 480px enfocado en el paso o en una pieza (mockup 06)
 *
 * Layout: el chrome [id]/layout.tsx ya renderea el children dentro de
 * `.body.no-chat`. Acá montamos un grid interno que alterna 1col / 1fr 480px
 * según el chat (mismo patrón validado en ContextView del paso 2). NO se
 * toca el chrome ni el layout (reglas estrictas #2/#3).
 */
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getCalculationForQuote, piecesTotalM2, streamChat, type Piece } from "@/lib/api";
import { useDespiece } from "@/lib/hooks/useDespiece";
import { useChatScoped } from "@/lib/hooks/useChatScoped";
import { DESPIECE_LOADING_TIMELINE } from "@/lib/mocks/canonicalQuote";
import { DespieceTable } from "./DespieceTable";
import { DespieceTimeline } from "./DespieceTimeline";
import { DespieceEmptyState } from "./DespieceEmptyState";
import { DespieceChatPanel } from "./DespieceChatPanel";
import { DespieceEmptyChat } from "./DespieceEmptyChat";
import { RecoveryBlock } from "./RecoveryBlock";
import { SessionInfoBanner } from "./SessionInfoBanner";
import { IaAuditBanner } from "@/components/observability/IaAuditBanner";

interface Props {
  quoteId: string;
}

const SKELETON_COLS = ["sk-w-70", "sk-w-60", "sk-w-60", "sk-w-40", "sk-w-50", "sk-w-50"];

function NewPieceDefaults(): Omit<Piece, "id" | "origin" | "confidence" | "extracted_from"> {
  return {
    type: "encimera",
    label: "Pieza nueva",
    sublabel: "describí la pieza",
    width_mm: 1000,
    depth_mm: 600,
    quantity: 1,
    options: {},
  };
}

export function DespieceView({ quoteId }: Props) {
  const router = useRouter();
  const {
    pieces,
    timeline,
    status,
    state,
    error,
    updatePiece,
    addPiece,
    deletePiece,
    regenerate,
    isDirty,
    editedCount,
    rejected,
    chatFlagged,
  } = useDespiece(quoteId);

  const [focusedPieceId, setFocusedPieceId] = useState<string | null>(null);
  const [manualMode, setManualMode] = useState(false);
  const [confirmRegen, setConfirmRegen] = useState(false);
  const [regenMenuOpen, setRegenMenuOpen] = useState(false);

  const chat = useChatScoped(quoteId, "despiece", focusedPieceId ?? undefined);
  const chatOpen = chat.panelState !== "closed";
  const focusedPiece = useMemo(
    () => pieces.find((p) => p.id === focusedPieceId) ?? null,
    [pieces, focusedPieceId],
  );

  const totalM2 = piecesTotalM2(pieces);

  // Confirmar despiece: manda `[DUAL_READ_CONFIRMED]{}` (backend usa el despiece
  // guardado), espera a que termine el turno y recién ahí navega a /calculo.
  // Si el cálculo sigue pendiente (Valentina pidió un dato) nos quedamos acá
  // con el chat abierto.
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  // Evita setState / router.push si el usuario se fue de la vista mientras
  // esperábamos el stream o el cálculo.
  const mountedRef = useRef(true);
  useEffect(() => {
    // Se re-arma al montar: en StrictMode React monta, desmonta y vuelve a montar.
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  // Un turno del chat: drena el stream y devuelve lo que dijo Valentina.
  async function runChatTurn(message: string): Promise<string> {
    const reader = streamChat(quoteId, message, "despiece").getReader();
    let failed = false;
    let text = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value && value.type === "text") text += value.content;
      if (value && (value.type === "error" || (value.type === "done" && value.error))) {
        failed = true;
      }
    }
    if (failed) throw new Error("No se pudo confirmar el despiece. Reintentá.");
    return text;
  }

  async function handleConfirm() {
    setConfirming(true);
    setConfirmError(null);
    try {
      // Turno 1: confirma las medidas. El agente responde con el resumen del
      // Paso 1 y pide confirmar las piezas (no calcula todavía).
      let valentinaText = await runChatTurn("[DUAL_READ_CONFIRMED]{}");
      let calc = await getCalculationForQuote(quoteId);
      if (!mountedRef.current) return;
      // Cálculo de edificios: el backend lo marca con este summary y nunca se
      // resuelve por chat; /calculo ya muestra el estado pending.
      if (calc.status === "pending" && !calc.bannerSummary.includes("edificios")) {
        // Turno 2: es la confirmación que el operador escribiría después del
        // resumen del Paso 1; con eso el agente corre calculate_quote.
        valentinaText =
          (await runChatTurn("Confirmo las piezas y medidas. Seguí con el Paso 2.")) ||
          valentinaText;
        calc = await getCalculationForQuote(quoteId);
        if (!mountedRef.current) return;
      }
      if (calc.status === "pending") {
        const question = valentinaText.trim();
        if (!question || calc.bannerSummary.includes("edificios")) {
          router.push(`/quotes/${quoteId}/calculo`);
          return;
        }
        setConfirmError(question.slice(-400));
        setFocusedPieceId(null);
        chat.open();
        setConfirming(false);
        return;
      }
      router.push(`/quotes/${quoteId}/calculo`);
      // El encabezado (m², material) viene del server layout: sin refresh
      // mostraría los valores previos al cálculo.
      router.refresh();
    } catch (err) {
      if (!mountedRef.current) return;
      setConfirmError(err instanceof Error ? err.message : "Error al confirmar el despiece");
      setConfirming(false);
    }
  }

  function openStepChat() {
    setFocusedPieceId(null);
    chat.open();
  }
  function openPieceChat(pieceId: string) {
    setFocusedPieceId(pieceId);
    chat.open();
  }
  function closeChat() {
    chat.close();
    setFocusedPieceId(null);
  }

  // Sprint 3 error-states (mockup 17) · cuando hay un preset flagged en la
  // quote, abrimos el chat scoped automáticamente al mount con el preset
  // (sesión persistente intra-quote · decisión Javi E solo copy del banner).
  const flaggedAutoOpened = chatFlagged != null;
  useEffect(() => {
    if (flaggedAutoOpened && chat.panelState === "closed") {
      chat.open();
    }
    // chat es estable entre renders · solo dependemos del flag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flaggedAutoOpened]);

  /* ── Loading ─────────────────────────────────────────────────────── */
  if (state === "loading") {
    return (
      <div className="col" data-testid="despiece-view" data-state="loading">
        <div className="section-head">
          <div>
            <div className="meta">Paso 3 de 5 · Despiece</div>
            <h2>Despiece de piezas</h2>
          </div>
        </div>
        <div className="ia-banner">
          <div className="vbubble" />
          <div className="text">
            <em>Valentina</em> está leyendo el plano para proponer las piezas.
            <div className="sub">
              Identifica el inventario en 4 pasadas · puede tardar unos segundos
            </div>
          </div>
        </div>
        <DespieceTimeline steps={DESPIECE_LOADING_TIMELINE} meta="4 pasadas" />
        <div className="etable cols-despiece mb-16" data-testid="despiece-loading">
          <div className="colh">
            <div>#</div>
            <div>Pieza</div>
            <div>Largo (cm)</div>
            <div>Ancho (cm)</div>
            <div>Cant.</div>
            <div>m² unit.</div>
            <div>m² total</div>
            <div />
          </div>
          {[0, 1, 2, 3, 4].map((i) => (
            <div className="row" key={i}>
              <div className="cell dim">R{i + 1}</div>
              {SKELETON_COLS.map((w, j) => (
                <div className="cell" key={j}>
                  <span className={`skel ${w}`} />
                </div>
              ))}
              <div className="cell action dim dim-40">⋯</div>
            </div>
          ))}
        </div>
        <div className="status-bar slow">
          <span className="vbubble" />
          <em>Valentina</em> está calculando las piezas…
          <span className="elapsed">leyendo el plano</span>
        </div>
      </div>
    );
  }

  /* ── Error ───────────────────────────────────────────────────────── */
  if (state === "error") {
    return (
      <div className="col" data-testid="despiece-view" data-state="error">
        <div className="section-head">
          <h2>No pude cargar el despiece</h2>
        </div>
        <p className="font-mono" style={{ fontSize: 12, color: "var(--error)" }}>
          {error ?? "Error desconocido"}
        </p>
      </div>
    );
  }

  /* ── Empty (IA falló, sin piezas, sin modo manual activado) ────────── */
  const isEmpty = pieces.length === 0 && status === "failed" && !manualMode;
  if (isEmpty) {
    return (
      <div className="col" data-testid="despiece-view" data-state="idle" data-status="failed">
        <div className="section-head">
          <div>
            <div className="meta">Paso 3 de 5 · Despiece</div>
            <h2>Despiece de piezas</h2>
          </div>
        </div>
        <DespieceEmptyState
          onProcessWithAI={() => router.push(`/quotes/${quoteId}/contexto`)}
          onCompleteManual={() => setManualMode(true)}
        />
      </div>
    );
  }

  /* ── Rejected · mockup 15 ──────────────────────────────────────────── */
  if (rejected) {
    return (
      <div
        data-testid="despiece-view"
        data-state="rejected"
        style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 24, minHeight: 0 }}
      >
        <div className="col">
          <div className="section-head">
            <div>
              <div className="meta">Paso 3 de 5 · Despiece</div>
              <h2>Despiece de piezas</h2>
            </div>
          </div>

          <IaAuditBanner quoteId={quoteId} />

          <div className="ia-banner error" data-testid="rejected-banner">
            <div className="vbubble" />
            <div className="text">
              Marina marcó este despiece como{" "}
              <strong>&ldquo;esto no me sirve&rdquo;</strong>.
              <div className="sub">Valentina toma nota y te ofrece tres caminos abajo</div>
            </div>
            <div className="actions">
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => router.push(`/quotes/${quoteId}/calculo`)}
                data-testid="rejected-close"
              >
                Cerrar
              </button>
            </div>
          </div>

          <DespieceTable
            pieces={pieces}
            focusedPieceId={null}
            discarded
            onUpdatePiece={() => {}}
            onDeletePiece={() => {}}
            onOpenPieceChat={() => {}}
            onAddPiece={() => {}}
          />

          <RecoveryBlock
            traceId="q_8f2a"
            onPath={() => {
              /* Sprint 4 wire recovery */
            }}
            onFeedback={() => {
              /* Sprint 4 wire trace */
            }}
          />
        </div>

        <DespieceEmptyChat onOpenChat={openStepChat} />

        {chatOpen && (
          <DespieceChatPanel
            quoteId={quoteId}
            messages={chat.messages}
            panelState={chat.panelState}
            pieceCount={pieces.length}
            editedCount={editedCount}
            focusedPiece={focusedPiece}
            onSend={chat.send}
            onClose={closeChat}
          />
        )}
      </div>
    );
  }

  /* ── A / B / C / manual ────────────────────────────────────────────── */
  const showTimeline = timeline.length > 0 && status !== "failed";
  const symbolsCount = pieces.reduce((n, p) => n + (p.detected_symbols?.length ?? 0), 0);
  const canConfirm =
    pieces.length > 0 && state !== "regenerating" && state !== "saving" && !confirming;

  return (
    <div
      data-testid="despiece-view"
      data-state={state}
      data-status={status}
      data-dirty={isDirty ? "true" : "false"}
      data-chat-open={chatOpen ? "true" : "false"}
      style={{
        // Sprint 3 paso-4 fix-up #2 · grid SIEMPRE 1fr. Chat es overlay fixed
        // (ver operator-shared.css §.chat). Aplica fix correlativo a despiece.
        display: "grid",
        gridTemplateColumns: "1fr",
        gap: 24,
        minHeight: 0,
      }}
    >
      <div className="col">
        <div className="section-head">
          <div>
            <div className="meta">Paso 3 de 5 · Despiece</div>
            <h2>Despiece de piezas</h2>
          </div>
          <div className="right">
            {confirmRegen ? (
              <div
                className="status-bar slow"
                style={{ margin: 0 }}
                data-testid="despiece-regen-confirm-bar"
              >
                Re-generar descarta la propuesta actual.
                <button
                  type="button"
                  className="btn ghost sm"
                  data-testid="despiece-regen-cancel"
                  onClick={() => setConfirmRegen(false)}
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  className="btn primary sm"
                  data-testid="despiece-regen-confirm"
                  onClick={() => {
                    setConfirmRegen(false);
                    setRegenMenuOpen(false);
                    setFocusedPieceId(null);
                    void regenerate("all");
                  }}
                >
                  Re-generar todo
                </button>
              </div>
            ) : isDirty ? (
              <div className="regen-wrap">
                <div className="regen-split">
                  <button
                    type="button"
                    className="main"
                    data-testid="despiece-regen-keep"
                    onClick={() => void regenerate("keep-edits")}
                  >
                    ↻ Re-generar no-editadas
                    <span className="count">{editedCount} quedan tuyas</span>
                  </button>
                  <button
                    type="button"
                    className="kebab"
                    aria-label="más opciones de re-generar"
                    onClick={() => setRegenMenuOpen((v) => !v)}
                  >
                    ⋮
                  </button>
                </div>
                {regenMenuOpen && (
                  <div className="regen-menu open">
                    <div
                      className="item danger"
                      role="button"
                      tabIndex={0}
                      data-testid="despiece-regen"
                      onClick={() => setConfirmRegen(true)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setConfirmRegen(true);
                        }
                      }}
                    >
                      Re-generar TODO el despiece
                      <span className="desc">
                        descarta {editedCount} cambios · pide confirmación
                      </span>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <button
                type="button"
                className="btn ghost sm"
                data-testid="despiece-regen"
                onClick={() => setConfirmRegen(true)}
              >
                ↻ Re-generar despiece
              </button>
            )}
          </div>
        </div>

        {/* Sprint 3 observability · banner explicativo cuando audit on. */}
        <IaAuditBanner quoteId={quoteId} />

        {/* Sprint 3 error-states (mockup 17) · banner contexto sesión chat. */}
        {chatFlagged && <SessionInfoBanner context={chatFlagged.sessionContext} />}

        {/* Banner Valentina · pristine / dirty / focused */}
        <div
          className={`ia-banner${manualMode && pieces.length === 0 ? " muted" : ""}`}
          data-testid="despiece-banner"
        >
          <div className="vbubble" />
          <div className="text">
            {focusedPiece ? (
              <>
                Estoy enfocada en{" "}
                <strong className="t-accent">
                  {focusedPiece.id} · {focusedPiece.label}
                </strong>
                . Si querés validar otra pieza, abrí su chat desde la fila.
                <div className="sub">
                  El chat sólo ve esta pieza · al cerrar se borra el historial
                </div>
              </>
            ) : manualMode && pieces.length === 0 ? (
              <>
                <em>Valentina</em> está pausada. Cargá las piezas a mano con{" "}
                <strong>+ agregar pieza manualmente</strong>.
                <div className="sub">
                  Si querés que lo intente de nuevo, usá ↻ Re-generar arriba
                </div>
              </>
            ) : isDirty ? (
              <>
                Recalculé m² con tus{" "}
                <strong className="t-human">
                  {editedCount} ajuste{editedCount === 1 ? "" : "s"}
                </strong>
                . <em>Valentina</em> mantiene los símbolos detectados del plano.
                <div className="sub">
                  Tus ediciones quedan en púrpura · podés deshacer cualquiera
                </div>
              </>
            ) : (
              <>
                <em>Valentina</em> propuso <strong>{pieces.length} piezas</strong> leyendo el plano
                en 4 pasadas.
                <div className="sub">
                  Valentina lee, no propone alternativas · click cualquier celda para editar
                </div>
              </>
            )}
          </div>
        </div>

        {showTimeline && (
          <DespieceTimeline
            steps={timeline}
            meta={`4 pasadas${symbolsCount > 0 ? ` · ${symbolsCount} símbolos detectados` : ""}`}
            title={
              isDirty ? (
                <>
                  Cómo <em>Valentina</em> leyó el plano
                </>
              ) : undefined
            }
          />
        )}

        <DespieceTable
          pieces={pieces}
          focusedPieceId={focusedPieceId}
          chatRefPieceId={chatFlagged?.pieceRefId}
          onUpdatePiece={updatePiece}
          onDeletePiece={deletePiece}
          onOpenPieceChat={openPieceChat}
          onAddPiece={() => void addPiece(NewPieceDefaults())}
        />

        {manualMode && (
          <div className="status-bar manual" data-testid="despiece-status-manual">
            <span className="vbubble" />
            <strong>Modo manual</strong> · <em>Valentina</em> pausada
            <span className="hint-end">
              si querés que lo intente de nuevo, usá ↻ Re-generar arriba
            </span>
          </div>
        )}

        <div className="confirm-bar">
          <div className="summary" data-testid="despiece-summary">
            <strong>{pieces.length} piezas</strong> · {totalM2.toFixed(2)} m²
            {isDirty && (
              <>
                {" "}
                ·{" "}
                <strong className="t-human">
                  {editedCount} edición{editedCount === 1 ? "" : "es"}
                </strong>{" "}
                tuyas
              </>
            )}
          </div>
          <button
            type="button"
            className="btn ghost"
            data-testid="despiece-open-chat"
            onClick={openStepChat}
          >
            💬 Ayuda con esta sección
          </button>
          {confirmError && (
            <div
              className="summary t-human"
              role="alert"
              data-testid="confirm-error"
              style={{ whiteSpace: "pre-wrap" }}
            >
              {confirmError}
            </div>
          )}
          <button
            type="button"
            className="btn primary"
            data-testid="confirm-despiece"
            disabled={!canConfirm}
            onClick={handleConfirm}
          >
            {confirming ? "Confirmando…" : "Confirmar y seguir →"}
          </button>
        </div>
      </div>

      {chatOpen && (
        <DespieceChatPanel
          quoteId={quoteId}
          messages={chat.messages}
          panelState={chat.panelState}
          pieceCount={pieces.length}
          editedCount={editedCount}
          focusedPiece={focusedPiece}
          onSend={chat.send}
          onClose={closeChat}
          flaggedPreset={chatFlagged}
        />
      )}
    </div>
  );
}
