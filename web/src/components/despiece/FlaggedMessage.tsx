/**
 * FlaggedMessage · variante del ValentinaMessage con btn-feedback inline
 * (mockup 17). Cuando Marina marca la respuesta como inútil → onFlag()
 * dispara la transición a FeedbackBanner.
 *
 * Reusa `.msg.v.flagged` + `.btn-feedback` + `.feedback-row` ya en CSS.
 */
"use client";

interface Props {
  name: string;
  relativeTs: string;
  body: string;
  /** true cuando ya se hizo click (botón disabled, igual que el mockup). */
  alreadyFlagged: boolean;
  onFlag: () => void;
}

export function FlaggedMessage({ name, relativeTs, body, alreadyFlagged, onFlag }: Props) {
  return (
    <div className="msg v flagged" data-testid="flagged-message">
      <div className="name">
        {name} <span className="ts-inline">{relativeTs}</span>
      </div>
      <div className="body">{body}</div>
      <div className="feedback-row">
        <button
          type="button"
          className="btn-feedback"
          onClick={onFlag}
          disabled={alreadyFlagged}
          data-testid="btn-feedback"
        >
          ✕ Esta respuesta no me sirvió
        </button>
      </div>
    </div>
  );
}
