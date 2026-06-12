/**
 * Campo individual editable del contexto (Master §4 #3).
 *
 * Comportamiento:
 *   - Click en el value → entra a edit mode (input visible, autoFocus)
 *   - Tab / Enter / blur → guarda + sale de edit mode
 *   - Esc → cancela + revierte al value original
 *
 * Visual:
 *   - field.edited === true → row con clase `.row-edited` (borde
 *     izquierdo púrpura · operator-shared.css) + chip "EDITADO" en
 *     la columna de origen + ícono ✏ en label.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import type { ContextField as ContextFieldData } from "@/lib/api";

interface Props {
  name: string;
  label: string;
  hint?: string;
  field: ContextFieldData;
  type?: "text" | "boolean";
  onCommit: (value: string | number | boolean | null) => void;
}

export function ContextField({ name, label, hint, field, type = "text", onCommit }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => formatForInput(field.value));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  // Si el field cambia por update remoto (mock), refrescar draft
  useEffect(() => {
    if (!editing) setDraft(formatForInput(field.value));
  }, [field.value, editing]);

  function commit() {
    setEditing(false);
    const cleaned = draft.trim();
    const original = formatForInput(field.value);
    if (cleaned === original) return;
    if (type === "boolean") {
      const lower = cleaned.toLowerCase();
      onCommit(lower === "sí" || lower === "si" || lower === "true");
      return;
    }
    onCommit(cleaned || null);
  }

  function cancel() {
    setDraft(formatForInput(field.value));
    setEditing(false);
  }

  const isEdited = field.edited === true;
  const displayValue = formatForDisplay(field.value);

  return (
    <div
      className={`row${isEdited ? " row-edited" : ""}`}
      data-testid={`context-row-${name}`}
      data-edited={isEdited}
    >
      <div className="cell label-cell">
        {label}
        {isEdited && (
          <span aria-hidden="true" data-testid={`edit-icon-${name}`}>
            {" "}
            ✏
          </span>
        )}
        {hint && <span className="sub">{hint}</span>}
      </div>
      <div className={`cell${isEdited ? " edited" : ""}`}>
        {editing ? (
          <input
            ref={inputRef}
            className="input"
            data-testid={`context-input-${name}`}
            value={draft}
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
            data-testid={`context-value-${name}`}
            onClick={() => setEditing(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setEditing(true);
              }
            }}
            role="button"
            tabIndex={0}
            style={{ cursor: "pointer" }}
          >
            {displayValue}
          </span>
        )}
      </div>
      <div className="cell">
        {isEdited ? (
          <span className="k k-edited" data-testid={`origin-chip-${name}`}>
            EDITADO
          </span>
        ) : (
          <span className="k" data-testid={`origin-chip-${name}`}>
            {field.origin}
          </span>
        )}
      </div>
      <div className="cell action">⋯</div>
    </div>
  );
}

function formatForInput(value: string | number | boolean | null): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "sí" : "no";
  return String(value);
}

// Exportado (Sprint 4 audit-copy-3-layer-state): el snapshot de [UI RENDER]
// reusa este formatter exacto para que el audit copy refleje 1:1 lo que el
// usuario ve (value ?? "—", bool → "Sí"/"No").
export function formatForDisplay(value: string | number | boolean | null): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Sí" : "No";
  return String(value);
}
