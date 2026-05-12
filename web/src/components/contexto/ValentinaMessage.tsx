/**
 * Mensaje de Valentina (role=valentina) en el chat scoped.
 *
 * Reusa clases legacy `.msg.v` (sans serif para body, .name uppercase
 * mono, em → serif italic accent). Si message.partial=true, agregamos
 * un cursor parpadeante al final del texto durante streaming.
 */
import type { ChatMessage } from "@/lib/types";

interface Props {
  message: ChatMessage;
}

export function ValentinaMessage({ message }: Props) {
  return (
    <div
      className="msg v"
      data-testid="chat-msg-valentina"
      data-partial={message.partial ? "true" : "false"}
    >
      <div className="name">Valentina</div>
      <div className="body">
        {message.content}
        {message.partial && (
          <span
            aria-hidden="true"
            data-testid="chat-cursor"
            style={{
              display: "inline-block",
              width: 8,
              height: 14,
              marginLeft: 2,
              background: "var(--accent)",
              verticalAlign: "middle",
              animation: "blink 1s steps(2) infinite",
            }}
          />
        )}
      </div>
    </div>
  );
}
