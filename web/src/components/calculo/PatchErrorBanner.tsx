/**
 * Banner `.patch-banner` del estado B (merma fantasma post-PATCH).
 * - Botón `.btn-warn` "✕ Eliminar merma" → auto-fix
 * - Botón `.btn-warn.ghost` "Ver diff con v1" → DISABLED (TODO Sprint 4 #5)
 * - Link "Recalcular todo desde cero" → recalculate (descarta patch)
 */
"use client";

interface Props {
  traceId: string;
  msg: string;
  onFix: () => void;
  onRecalcFromScratch: () => void;
}

export function PatchErrorBanner({ traceId, msg, onFix, onRecalcFromScratch }: Props) {
  return (
    <div className="patch-banner" data-testid="patch-banner">
      <div className="icon" aria-hidden="true">
        !
      </div>
      <div className="pb-body">
        <div className="head">
          <strong>Validación post-PATCH</strong>
          <span className="sub" style={{ marginLeft: 8, opacity: 0.7 }}>
            trace {traceId}
          </span>
        </div>
        <div className="msg">{msg}</div>
        <div
          className="actions"
          style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}
        >
          <button type="button" className="btn-warn" onClick={onFix} data-testid="patch-fix">
            ✕ Eliminar merma
          </button>
          <button
            type="button"
            className="btn-warn ghost"
            disabled
            title="Ver diff con v1 — Sprint 4 (versioning + drawer)"
            data-testid="patch-diff-disabled"
          >
            Ver diff con v1
          </button>
          <a
            href="#"
            className="recalc-link"
            onClick={(e) => {
              e.preventDefault();
              onRecalcFromScratch();
            }}
            data-testid="patch-recalc-link"
          >
            Recalcular todo desde cero
          </a>
        </div>
      </div>
    </div>
  );
}
