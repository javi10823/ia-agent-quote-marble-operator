/**
 * Confirm bar inferior. Variante `.warn-bar` en estado B con confirm disabled.
 * Confirm → router.push a /quotes/[id]/pdf (placeholder en este PR).
 */
"use client";

import { useState } from "react";

interface Props {
  quoteId: string;
  blocked: boolean;
  blockedReason?: string;
  onOpenChat: () => void;
  onConfirm: () => void;
}

export function CalcConfirmBar({
  quoteId: _quoteId,
  blocked,
  blockedReason,
  onOpenChat,
  onConfirm,
}: Props) {
  const [vigencia, setVigencia] = useState("15");
  return (
    <div className={`confirm-bar${blocked ? " warn-bar" : ""}`} data-testid="confirm-bar">
      <div className="summary">
        {blocked ? (
          <span className="warn-tone">
            ⚠ <strong>No se puede confirmar</strong>
            {blockedReason && ` · ${blockedReason}`}
          </span>
        ) : (
          <>
            Vigencia
            <input
              className="vig-input"
              type="text"
              value={vigencia}
              onChange={(e) => setVigencia(e.target.value)}
              data-testid="vig-input"
              style={{
                margin: "0 6px",
                padding: "3px 8px",
                width: 50,
                background: "var(--surface-2)",
                border: "1px solid var(--line)",
                borderRadius: "var(--r-sm)",
                color: "var(--ink)",
                fontFamily: "var(--mono)",
                fontSize: 13,
                textAlign: "center",
              }}
            />
            días · listo para generar PDF
          </>
        )}
      </div>
      <button
        type="button"
        className="btn ghost"
        onClick={onOpenChat}
        data-testid="open-chat"
        style={{ marginRight: 8 }}
      >
        💬 Ayuda con esta sección
      </button>
      <button
        type="button"
        className={`btn primary${blocked ? " disabled" : ""}`}
        disabled={blocked}
        onClick={onConfirm}
        data-testid="confirm-calculo"
      >
        Confirmar y generar PDF →
      </button>
    </div>
  );
}
