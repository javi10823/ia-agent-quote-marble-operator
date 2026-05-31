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

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { piecesTotalM2, type Piece } from "@/lib/api";
import { useDespiece } from "@/lib/hooks/useDespiece";
import { useChatScoped } from "@/lib/hooks/useChatScoped";
import { DESPIECE_LOADING_TIMELINE } from "@/lib/mocks/canonicalQuote";
import { DespieceTable } from "./DespieceTable";
import { DespieceTimeline } from "./DespieceTimeline";
import { DespieceEmptyState } from "./DespieceEmptyState";
import { DespieceChatPanel } from "./DespieceChatPanel";

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
          onProcessWithAI={() => router.push(`/quotes/${quoteId}/brief`)}
          onCompleteManual={() => setManualMode(true)}
        />
      </div>
    );
  }

  /* ── A / B / C / manual ────────────────────────────────────────────── */
  const showTimeline = timeline.length > 0 && status !== "failed";
  const symbolsCount = pieces.reduce((n, p) => n + (p.detected_symbols?.length ?? 0), 0);
  const canConfirm = pieces.length > 0 && state !== "regenerating";

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
          <button
            type="button"
            className="btn primary"
            data-testid="confirm-despiece"
            disabled={!canConfirm}
            onClick={() => router.push(`/quotes/${quoteId}/calculo`)}
          >
            Confirmar y seguir →
          </button>
        </div>
      </div>

      {chatOpen && (
        <DespieceChatPanel
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
