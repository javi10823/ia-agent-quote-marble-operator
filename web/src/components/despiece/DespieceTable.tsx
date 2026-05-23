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
}

export function DespieceTable({
  pieces,
  focusedPieceId,
  onUpdatePiece,
  onDeletePiece,
  onOpenPieceChat,
  onAddPiece,
}: Props) {
  return (
    <div className="etable cols-despiece mb-16" data-testid="despiece-table">
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

      {pieces.map((piece) => (
        <PieceRow
          key={piece.id}
          piece={piece}
          focused={focusedPieceId === piece.id}
          onUpdate={onUpdatePiece}
          onDelete={onDeletePiece}
          onOpenChat={onOpenPieceChat}
        />
      ))}

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
    </div>
  );
}
