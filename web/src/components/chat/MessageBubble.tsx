import type { UIMessage } from "@/app/quote/[id]/page";

interface Props { message: UIMessage; actionText?: string; }

export default function MessageBubble({ message, actionText }: Props) {
  const isV = message.role === "assistant";

  if (!isV) {
    return (
      <div className="msg-anim" style={{ display: "flex", gap: 12, flexDirection: "row-reverse", alignItems: "flex-start" }}>
        <Avatar isV={false} />
        <div style={{
          maxWidth: "52%", padding: "12px 16px",
          background: "var(--acc2)", border: "1px solid var(--acc3)",
          borderRadius: "12px 2px 12px 12px",
          fontSize: 15, lineHeight: 1.65, color: "rgba(255,255,255,.78)",
        }}>
          {message.attachmentName && (
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              padding: "4px 9px", borderRadius: 5,
              background: "rgba(255,255,255,.08)", border: "1px solid var(--b1)",
              fontSize: 11, color: "var(--t2)", marginBottom: 7,
            }}>📎 {message.attachmentName}</div>
          )}
          <p>{message.content}</p>
        </div>
      </div>
    );
  }

  // Parse content into blocks
  const blocks = parseBlocks(message.content, message.isStreaming, actionText);

  return (
    <div className="msg-anim" style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      <Avatar isV />
      <div style={{
        flex: 1,
        border: "1px solid var(--b2)",
        borderRadius: "2px 12px 12px 12px",
        overflow: "hidden",
      }}>
        {blocks.map((block, i) => (
          <Block key={i} block={block} isLast={i === blocks.length - 1} isStreaming={!!message.isStreaming && i === blocks.length - 1} actionText={actionText} />
        ))}
      </div>
    </div>
  );
}

// ── BLOCK RENDERER ─────────────────────────────────────────────────────────────

type BlockType = { type: "thinking" | "text" | "raw"; content: string };

function parseBlocks(content: string, isStreaming?: boolean, actionText?: string): BlockType[] {
  if (!content) return [{ type: "thinking", content: actionText || "" }];

  const blocks: BlockType[] = [];
  const lines = content.split("\n");

  // Detect thinking lines (italic starting with _)
  const thinkingLines: string[] = [];
  const restLines: string[] = [];
  let pastThinking = false;

  for (const line of lines) {
    if (!pastThinking && (line.startsWith("_") || line.trim() === "")) {
      if (line.startsWith("_")) thinkingLines.push(line.replace(/^_|_$/g, "").trim());
    } else {
      pastThinking = true;
      restLines.push(line);
    }
  }

  if (thinkingLines.length > 0) {
    blocks.push({ type: "thinking", content: thinkingLines.join("\n") });
  }

  if (restLines.join("").trim()) {
    blocks.push({ type: "text", content: restLines.join("\n").trim() });
  }

  if (blocks.length === 0) {
    blocks.push({ type: "text", content });
  }

  return blocks;
}

function Block({ block, isLast, isStreaming, actionText }: { block: BlockType; isLast: boolean; isStreaming: boolean; actionText?: string }) {
  const borderBottom = !isLast ? "1px solid var(--b1)" : undefined;

  if (block.type === "thinking") {
    const lines = block.content ? block.content.split("\n") : [""];
    return (
      <div style={{ padding: "12px 18px", background: "var(--s2)", borderBottom, display: "flex", flexDirection: "column", gap: 6 }}>
        {lines.map((line, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11, color: "var(--t3)", fontStyle: "italic" }}>
            <div style={{
              width: 5, height: 5, borderRadius: "50%", background: "var(--acc)", flexShrink: 0,
              animation: "pulse 1.4s ease-in-out infinite",
              animationDelay: `${i * 0.3}s`,
            }} />
            {line || (isStreaming ? (actionText || "Procesando...") : "")}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div style={{ padding: "14px 18px", background: "var(--s2)", borderBottom, fontSize: 15, lineHeight: 1.7, color: "var(--t2)" }}>
      <FormattedText text={block.content} isStreaming={isStreaming} />
    </div>
  );
}

// ── TEXT FORMATTER ─────────────────────────────────────────────────────────────

function FormattedText({ text, isStreaming }: { text: string; isStreaming?: boolean }) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      elements.push(<div key={i} style={{ height: 6 }} />);
    } else if (line.startsWith("**") && line.endsWith("**")) {
      elements.push(<p key={i} style={{ fontWeight: 500, color: "var(--t1)" }}>{line.slice(2, -2)}</p>);
    } else if (line.startsWith("✅") || line.startsWith("⚠") || line.startsWith("❌")) {
      elements.push(<p key={i} style={{ color: "var(--t1)" }}>{line}</p>);
    } else {
      elements.push(<p key={i} style={{ marginBottom: 2 }}><InlineFormat text={line} /></p>);
    }
    i++;
  }

  return (
    <div className={isStreaming ? "streaming-cursor" : ""}>
      {elements}
    </div>
  );
}

function InlineFormat({ text }: { text: string }) {
  const parts = text.split(/\*\*(.*?)\*\*/g);
  if (parts.length === 1) return <>{text}</>;
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1
          ? <strong key={i} style={{ fontWeight: 500, color: "var(--t1)" }}>{p}</strong>
          : p
      )}
    </>
  );
}

// ── AVATAR ─────────────────────────────────────────────────────────────────────

function Avatar({ isV }: { isV: boolean }) {
  return (
    <div style={{
      width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 11, fontWeight: 600,
      background: isV ? "var(--acc)" : "var(--s3)",
      color: isV ? "#fff" : "var(--t2)",
      border: isV ? "none" : "1px solid var(--b2)",
    }}>
      {isV ? "V" : "OP"}
    </div>
  );
}
