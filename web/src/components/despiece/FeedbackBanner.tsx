/**
 * `.feedback-banner` post-click en btn-feedback (mockup 17).
 *
 * "Anotado. ¿Querés reformular la pregunta o cerrar el chat?"
 * + 2 actions: Reformular (solid) / Cerrar chat.
 *
 * Sprint 3 error-states · Reformular trigger composer prefill, Cerrar
 * llama a onClose del chat panel.
 */
"use client";

interface Props {
  onReformulate: () => void;
  onClose: () => void;
}

export function FeedbackBanner({ onReformulate, onClose }: Props) {
  return (
    <div className="feedback-banner" data-testid="feedback-banner">
      <div className="text">
        <em>Anotado.</em> ¿Querés reformular la pregunta o cerrar el chat?
        <div className="meta">Tu feedback queda en el audit log · el mensaje no se borra</div>
      </div>
      <div className="actions">
        <button
          type="button"
          className="btn-fb solid"
          onClick={onReformulate}
          data-testid="feedback-reformulate"
        >
          Reformular
        </button>
        <button
          type="button"
          className="btn-fb"
          onClick={onClose}
          data-testid="feedback-close"
        >
          Cerrar chat
        </button>
      </div>
    </div>
  );
}
