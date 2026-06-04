/**
 * Empty-CTA del chat lateral en mockup 15.
 *
 * Cuando el despiece está rejected, el chat side panel está cerrado pero
 * muestra una CTA para abrirlo ("Si querés rehacer hablando, abrime").
 *
 * Reusa `.chat.fit` + `.empty-cta` ya presentes en operator-shared.css.
 */
"use client";

interface Props {
  onOpenChat: () => void;
}

export function DespieceEmptyChat({ onOpenChat }: Props) {
  return (
    <aside className="chat fit" data-testid="despiece-empty-chat">
      <div className="head">
        <div className="vbubble" />
        <div>
          <div className="title">Ayuda con Despiece</div>
          <div className="sub">Scoped · cerrado</div>
        </div>
        <span className="x" aria-hidden="true">
          →
        </span>
      </div>
      <div className="empty-cta">
        <div className="msg">
          Si querés rehacer hablando, abrime —<br />
          te pregunto lo que necesite.
        </div>
        <div className="cta">
          <button
            type="button"
            className="btn ghost sm"
            onClick={onOpenChat}
            data-testid="empty-chat-open"
          >
            Abrir chat ↗
          </button>
        </div>
      </div>
    </aside>
  );
}
