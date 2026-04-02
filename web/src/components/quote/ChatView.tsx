import type { UIMessage } from "@/lib/types";
import type { ChatInputProps } from "@/components/chat/ChatInput";
import MessageBubble from "@/components/chat/MessageBubble";
import ChatInput from "@/components/chat/ChatInput";

interface Props {
  messages: UIMessage[];
  actionText: string;
  endRef: React.RefObject<HTMLDivElement>;
  chatInputProps: ChatInputProps;
}

export default function ChatView({ messages, actionText, endRef, chatInputProps }: Props) {
  return (
    <>
      <div style={{ flex: 1, overflowY: "auto", padding: "28px 28px 16px", display: "flex", flexDirection: "column", gap: 20 }}>
        {messages.length === 0 && (
          <div style={{ padding: "14px 18px", background: "var(--s2)", borderRadius: 12, fontSize: 13, color: "var(--t2)" }}>
            Hola 👋 Soy Valentina. Pasame el enunciado del trabajo y/o el plano.
          </div>
        )}
        {messages.map(msg => <MessageBubble key={msg.id} message={msg} actionText={msg.isStreaming ? actionText : undefined} />)}
        <div ref={endRef} />
      </div>
      <div style={{ flexShrink: 0, padding: "14px 28px 18px", borderTop: "1px solid var(--b1)", background: "var(--s1)" }}>
        <ChatInput {...chatInputProps} />
        <div style={{ fontSize: 10, color: "var(--t4)", textAlign: "center", marginTop: 7 }}>
          Enter para enviar · Shift+Enter para nueva línea
        </div>
      </div>
    </>
  );
}
