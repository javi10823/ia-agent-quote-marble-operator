/**
 * Mensaje de Marina (role=user) en el chat scoped.
 * Reusa clases legacy `.msg.user` (alineado a la derecha, sans serif).
 */
import type { ChatMessage } from "@/lib/types";

interface Props {
  message: ChatMessage;
}

export function UserMessage({ message }: Props) {
  return (
    <div className="msg user" data-testid="chat-msg-user">
      {message.content}
    </div>
  );
}
