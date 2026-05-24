/**
 * Fila de una pieza del despiece (mockups 04/05/06).
 *
 * Columnas (grid `.cols-despiece`): # · Pieza · Largo · Ancho · Cant. ·
 * m² unit. · m² total · acciones.
 *
 * - Largo/Ancho/Cant. son `PieceCell` editables (Tab/Enter/Esc).
 * - m² unit/total son derivados (read-only) de las dimensiones actuales.
 * - Las dimensiones se guardan en mm; la tabla muestra cm (mm/10).
 * - Highlight `.edited` por celda comparando contra el valor inicial de la
 *   sesión; piezas `AGREGADO_MANUAL` muestran todas las celdas en púrpura.
 */
"use client";

import { useRef, useState } from "react";
import { pieceM2Total, pieceM2Unit, type Piece } from "@/lib/api";
import { PieceCell } from "./PieceCell";
import { PieceChatButton } from "./PieceChatButton";

interface Props {
  piece: Piece;
  focused: boolean;
  onUpdate: (pieceId: string, partial: Partial<Piece>) => void;
  onDelete: (pieceId: string) => void;
  onOpenChat: (pieceId: string) => void;
}

const RESET_BTN: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "inherit",
  font: "inherit",
  cursor: "pointer",
  padding: 0,
  lineHeight: 1,
};

export function PieceRow({ piece, focused, onUpdate, onDelete, onOpenChat }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Valores iniciales de la sesión para resaltar celdas tocadas.
  const initial = useRef({
    largo: piece.width_mm / 10,
    ancho: piece.depth_mm / 10,
    cant: piece.quantity,
  });

  const isManual = piece.origin === "AGREGADO_MANUAL";
  const isEdited = piece.edited === true || piece.origin === "EDITADO" || isManual;

  const largoCm = piece.width_mm / 10;
  const anchoCm = piece.depth_mm / 10;

  const rowCls = [
    "row",
    isEdited ? "row-edited" : "",
    isManual ? "row-manual" : "",
    focused ? "row-chat-ref" : "",
  ]
    .filter(Boolean)
    .join(" ");

  function closeMenu() {
    setMenuOpen(false);
    setConfirmDelete(false);
  }

  return (
    <div
      className={rowCls}
      data-testid={`piece-row-${piece.id}`}
      data-origin={piece.origin}
      data-edited={isEdited}
    >
      <div className="cell">{piece.id}</div>

      <div className="cell label-cell">
        <span>{piece.label}</span>
        {isEdited && (
          <span className="k k-edited" data-testid={`piece-edited-chip-${piece.id}`}>
            EDITADO
          </span>
        )}
        {(piece.sublabel || (piece.detected_symbols && piece.detected_symbols.length > 0)) && (
          <span className="sub">
            {piece.sublabel}
            {piece.detected_symbols?.map((s, i) => (
              <span className="det-sym" key={`${s.src}-${i}`}>
                <span className="src">{s.src}</span>
                <span className="arrow">→</span>
                <span className="out">{s.out}</span>
              </span>
            ))}
          </span>
        )}
        {focused && <span className="sub sub-chat-ref">↳ chat enfocado aquí</span>}
      </div>

      <PieceCell
        value={largoCm}
        edited={isManual || largoCm !== initial.current.largo}
        testId={`piece-largo-${piece.id}`}
        onCommit={(cm) => onUpdate(piece.id, { width_mm: Math.round(cm * 10) })}
      />
      <PieceCell
        value={anchoCm}
        edited={isManual || anchoCm !== initial.current.ancho}
        testId={`piece-ancho-${piece.id}`}
        onCommit={(cm) => onUpdate(piece.id, { depth_mm: Math.round(cm * 10) })}
      />
      <PieceCell
        value={piece.quantity}
        edited={isManual || piece.quantity !== initial.current.cant}
        testId={`piece-cant-${piece.id}`}
        integer
        onCommit={(qty) => onUpdate(piece.id, { quantity: qty })}
      />

      <div className="cell num" data-testid={`piece-m2unit-${piece.id}`}>
        {pieceM2Unit(piece).toFixed(2)}
      </div>
      <div className="cell num" data-testid={`piece-m2total-${piece.id}`}>
        {pieceM2Total(piece).toFixed(2)}
      </div>

      <div className="cell action regen-wrap">
        <button
          type="button"
          style={RESET_BTN}
          aria-label={`acciones de ${piece.id}`}
          data-testid={`piece-menu-${piece.id}`}
          onClick={() => (menuOpen ? closeMenu() : setMenuOpen(true))}
        >
          ⋯
        </button>
        {menuOpen && (
          <div className="regen-menu open" role="menu">
            <PieceChatButton
              pieceId={piece.id}
              onOpen={() => {
                onOpenChat(piece.id);
                closeMenu();
              }}
            />
            {!confirmDelete ? (
              <div
                className="item danger"
                role="button"
                tabIndex={0}
                data-testid={`piece-delete-${piece.id}`}
                onClick={() => setConfirmDelete(true)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setConfirmDelete(true);
                  }
                }}
              >
                Eliminar pieza
                <span className="desc">se quita del despiece</span>
              </div>
            ) : (
              <div
                className="item danger"
                role="button"
                tabIndex={0}
                data-testid={`piece-delete-confirm-${piece.id}`}
                onClick={() => {
                  onDelete(piece.id);
                  closeMenu();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onDelete(piece.id);
                    closeMenu();
                  }
                }}
              >
                ¿Confirmar? eliminar {piece.id}
                <span className="desc">esta acción no se puede deshacer</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
