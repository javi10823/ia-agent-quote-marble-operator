/**
 * Tabla `.etable.cols-despiece` de piezas (mockups 04/05/06).
 * Header fijo + una `PieceRow` por pieza + fila "agregar pieza manualmente".
 */
"use client";

import type { Piece } from "@/lib/api";
import { PieceRow } from "./PieceRow";

interface Props {
  pieces: Piece[];
  focusedPieceId: string | null;
  onUpdatePiece: (pieceId: string, partial: Partial<Piece>) => void;
  onDeletePiece: (pieceId: string) => void;
  onOpenPieceChat: (pieceId: string) => void;
  onAddPiece: () => void;
  /** Sprint 3 error-states (mockup 15) · cuando true, tabla se renderea
   * `.discarded` con tag "descartado" en el header de Pieza · interacciones
   * deshabilitadas (sin add-row, sin onUpdate, sin onDelete). */
  discarded?: boolean;
  /** Sprint 3 error-states (mockup 17) · ID de la pieza referida por el
   * chat scoped abierto · se marca con `.row-chat-ref` + label "↳ chat
   * referido a esta pieza". */
  chatRefPieceId?: string;
}

export function DespieceTable({
  pieces,
  focusedPieceId,
  onUpdatePiece,
  onDeletePiece,
  onOpenPieceChat,
  onAddPiece,
  discarded = false,
  chatRefPieceId,
}: Props) {
  return (
    <div
      className={`etable cols-despiece mb-16${discarded ? " discarded" : ""}`}
      data-testid="despiece-table"
      data-discarded={discarded ? "true" : "false"}
    >
      <div className="colh">
        <div>#</div>
        <div>
          Pieza
          {discarded && (
            <>
              {" · "}
              <span className="discarded-tag" data-testid="discarded-tag">
                descartado
              </span>
            </>
          )}
        </div>
        <div>Largo (cm)</div>
        <div>Ancho (cm)</div>
        <div>Cant.</div>
        <div>m² unit.</div>
        <div>m² total</div>
        <div />
      </div>

      {pieces.map((piece) => (
        <PieceRow
          key={piece.id}
          piece={piece}
          focused={focusedPieceId === piece.id}
          chatRef={chatRefPieceId === piece.id}
          onUpdate={onUpdatePiece}
          onDelete={onDeletePiece}
          onOpenChat={onOpenPieceChat}
        />
      ))}

      {!discarded && (
        <div
          className="add-row"
          role="button"
          tabIndex={0}
          data-testid="despiece-add-row"
          onClick={onAddPiece}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onAddPiece();
            }
          }}
        >
          + agregar pieza manualmente
        </div>
      )}
    </div>
  );
}
