/**
 * Estado C — procesando del paso 1 (mockup 00-paso1-C-procesando).
 *
 * Hero Valentina con copy distinto + status-bar inferior + skeleton
 * filas + botón cancelar. NO hay spinner full-screen (Master §
 * comportamientos transversales).
 *
 * Cancel callback aborta el AbortController del hook → vuelve a
 * estado B con el form preservado.
 */
"use client";

interface Props {
  onCancel: () => void;
  planName?: string;
}

export function BriefProcessing({ onCancel, planName }: Props) {
  return (
    <div className="col brief-stage" data-step="brief" data-state="C">
      <div className="brief-hero">
        <div className="vbubble-lg" />
        <div className="hero-text">
          <div className="eyebrow">Paso 1 de 5 · Brief · procesando</div>
          <h2>Estoy leyendo el plano</h2>
          <div className="lead">
            Extraigo medidas reales (no las marcadas), identifico ambiente, busco el cliente en mi
            base de arquitectos y armo el contexto del paso 2.
          </div>
        </div>
      </div>

      <div className="status-bar slow" data-testid="brief-status-bar">
        <div className="dot" />
        <div className="status-msg">
          <em>Valentina</em> está leyendo el plano y extrayendo medidas…
        </div>
      </div>

      <div className="processing-stage" data-testid="brief-processing">
        <div className="preview-card">
          <div className="ph-head">
            <span>📄 {planName ?? "Plano en proceso"}</span>
          </div>
          <div className="ph-rows">
            <div className="skel short" />
            <div className="skel long" />
            <div className="skel medium" />
            <div className="skel long" />
            <div className="skel short" />
            <div className="skel medium" />
            <div className="skel long" />
          </div>
        </div>

        <div className="cancel-row">
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onCancel} data-testid="brief-cancel">
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
