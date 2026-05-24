/**
 * Celda numérica editable inline de una pieza (Largo / Ancho / Cant.).
 *
 * Mismo patrón validado en el paso 2 (ContextField · Master §4 #3):
 *   - Click en el value → edit mode (input con foco + select)
 *   - Tab / Enter / blur → commit (guarda)
 *   - Esc → cancela + revierte al value original
 *
 * Visual: `.cell.num`; si `edited` agrega `.edited` (borde púrpura + ✏);
 * mientras se tipea agrega `.typing` (outline púrpura + cursor).
 */
"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  value: number;
  edited?: boolean;
  testId: string;
  /** Sólo enteros (cantidades). Default false → admite decimales (cm). */
  integer?: boolean;
  onCommit: (value: number) => void;
}

export function PieceCell({ value, edited = false, testId, integer = false, onCommit }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => String(value));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  useEffect(() => {
    if (!editing) setDraft(String(value));
  }, [value, editing]);

  function commit() {
    setEditing(false);
    const parsed = integer ? parseInt(draft, 10) : parseFloat(draft);
    if (Number.isNaN(parsed) || parsed < 0 || parsed === value) {
      setDraft(String(value));
      return;
    }
    onCommit(parsed);
  }

  function cancel() {
    setDraft(String(value));
    setEditing(false);
  }

  return (
    <div
      className={`cell num${edited ? " edited" : ""}${editing ? " typing" : ""}`}
      data-testid={testId}
      data-edited={edited}
    >
      {editing ? (
        <input
          ref={inputRef}
          className="input num"
          inputMode={integer ? "numeric" : "decimal"}
          value={draft}
          data-testid={`${testId}-input`}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === "Tab") {
              if (e.key === "Enter") e.preventDefault();
              commit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              cancel();
            }
          }}
        />
      ) : (
        <span
          className="value-clickable"
          data-testid={`${testId}-value`}
          role="button"
          tabIndex={0}
          style={{ cursor: "pointer" }}
          onClick={() => setEditing(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setEditing(true);
            }
          }}
        >
          {value}
        </span>
      )}
    </div>
  );
}
