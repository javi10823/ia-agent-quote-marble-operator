/**
 * Empty state del paso 3 (mockup 16 + variante 04-manual): Valentina no pudo
 * proponer un despiece. Dos caminos: procesar con IA (vuelve al paso 1) o
 * completar a mano (tabla editable vacía).
 */
"use client";

interface Props {
  onProcessWithAI: () => void;
  onCompleteManual: () => void;
}

export function DespieceEmptyState({ onProcessWithAI, onCompleteManual }: Props) {
  return (
    <div className="empty-hero" data-testid="despiece-empty">
      <div className="glyph">∅</div>
      <h3>Acá todavía no hay piezas que despiezar</h3>
      <p className="lead">
        <em>Valentina</em> no pudo proponer un despiece — falta brief o contexto del ambiente. Elegí
        cómo seguir:
      </p>

      <div className="empty-paths">
        <div
          className="path primary"
          role="button"
          tabIndex={0}
          data-testid="empty-process-ai"
          onClick={onProcessWithAI}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onProcessWithAI();
            }
          }}
        >
          <div className="icon-wrap">
            <div className="icon">↑</div>
            <div className="ttl">Procesar con Valentina</div>
            <div className="badge-rec">recomendado</div>
          </div>
          <div className="desc">
            Subí el brief, el plano, o ambos. <em>Valentina</em> identifica las piezas y propone el
            despiece completo. Después editás lo que quieras.
          </div>
          <div className="meta">→ vuelve al paso 1 · procesa con IA</div>
        </div>

        <div
          className="path"
          role="button"
          tabIndex={0}
          data-testid="empty-complete-manual"
          onClick={onCompleteManual}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onCompleteManual();
            }
          }}
        >
          <div className="icon-wrap">
            <div className="icon">+</div>
            <div className="ttl">Completar a mano</div>
          </div>
          <div className="desc">
            Empezás con una tabla vacía y vas agregando piezas una por una con sus medidas. Sin
            ayuda de Valentina hasta que confirmes contexto.
          </div>
          <div className="meta">→ tabla editable inline · sin cálculo automático</div>
        </div>
      </div>
    </div>
  );
}
