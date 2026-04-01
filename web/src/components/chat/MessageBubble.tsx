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

    // Markdown table: collect all consecutive | lines
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      elements.push(<MarkdownTable key={`table-${i}`} lines={tableLines} />);
      continue;
    }

    if (line.trim() === "") {
      elements.push(<div key={i} style={{ height: 6 }} />);
    } else if (line.trim() === "---") {
      elements.push(
        <hr key={i} style={{ border: "none", borderTop: "1px solid var(--b2)", margin: "14px 0" }} />
      );
    } else if (line.startsWith("### ")) {
      elements.push(
        <div key={i} style={{
          fontWeight: 600, color: "var(--t1)", fontSize: 15,
          marginTop: 18, marginBottom: 8,
          paddingBottom: 6, borderBottom: "1px solid var(--b1)",
          letterSpacing: "-0.01em",
        }}>
          <InlineFormat text={line.slice(4)} />
        </div>
      );
    } else if (line.startsWith("## ")) {
      elements.push(
        <div key={i} style={{
          fontWeight: 600, color: "var(--t1)", fontSize: 20,
          marginTop: 4, marginBottom: 4,
          letterSpacing: "-0.02em", lineHeight: 1.3,
        }}>
          <InlineFormat text={line.slice(3)} />
        </div>
      );
    } else if (line.startsWith("**") && line.endsWith("**")) {
      elements.push(
        <p key={i} style={{ fontWeight: 500, color: "var(--t2)", fontSize: 13 }}>
          <InlineFormat text={line} />
        </p>
      );
    } else if (line.startsWith("✅") || line.startsWith("⚠") || line.startsWith("❌")) {
      elements.push(<p key={i} style={{ color: "var(--t1)" }}>{line}</p>);
    } else if (line.startsWith("- ")) {
      elements.push(
        <p key={i} style={{ marginBottom: 3, paddingLeft: 12 }}>
          <span style={{ color: "var(--t3)", marginRight: 6 }}>•</span>
          <InlineFormat text={line.slice(2)} />
        </p>
      );
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

function MarkdownTable({ lines }: { lines: string[] }) {
  // Filter out separator lines (|---|---|)
  const dataLines = lines.filter(l => !l.match(/^\|[\s\-:|]+\|$/));
  if (dataLines.length === 0) return null;

  const parseRow = (line: string) =>
    line.split("|").slice(1, -1).map(c => c.trim());

  const header = parseRow(dataLines[0]);
  const rows = dataLines.slice(1).map(parseRow);

  // Check if last row is a TOTAL row
  const isTotal = (row: string[]) => row.some(c => c.toLowerCase().includes("total"));

  const cellStyle: React.CSSProperties = {
    padding: "10px 14px",
    fontSize: 14,
    borderBottom: "1px solid rgba(255,255,255,.06)",
    color: "var(--t2)",
    lineHeight: 1.4,
  };

  const headerStyle: React.CSSProperties = {
    padding: "8px 14px",
    fontWeight: 600,
    color: "var(--t1)",
    fontSize: 13,
    letterSpacing: "0.02em",
    borderBottom: "2px solid rgba(255,255,255,.1)",
  };

  return (
    <div style={{ margin: "8px 0", borderRadius: 10, overflow: "hidden", border: "1px solid var(--b1)", background: "rgba(255,255,255,.02)" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {header.map((h, j) => (
              <th key={j} style={{ ...headerStyle, textAlign: j >= 1 ? "right" : "left" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => {
            const isTotalRow = isTotal(row);
            return (
              <tr key={ri} style={{
                background: isTotalRow ? "rgba(255,255,255,.04)" : "transparent",
              }}>
                {row.map((cell, ci) => (
                  <td key={ci} style={{
                    ...cellStyle,
                    textAlign: ci >= 1 ? "right" : "left",
                    fontWeight: isTotalRow ? 600 : 400,
                    color: isTotalRow ? "var(--t1)" : "var(--t2)",
                    borderBottom: isTotalRow ? "none" : cellStyle.borderBottom,
                  }}>
                    <InlineFormat text={cell} />
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function InlineFormat({ text }: { text: string }) {
  // Parse markdown links [text](url) and bold **text**
  const elements: React.ReactNode[] = [];
  const regex = /\[([^\]]+)\]\(([^)]+)\)|\*\*(.*?)\*\*/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      elements.push(text.slice(lastIndex, match.index));
    }

    if (match[1] && match[2]) {
      // Markdown link [text](url)
      elements.push(
        <a key={match.index} href={match[2]} target="_blank" rel="noopener noreferrer"
          style={{ color: "var(--acc)", textDecoration: "none", borderBottom: "1px solid rgba(79,143,255,.3)" }}
          onMouseEnter={e => (e.currentTarget.style.borderBottomColor = "var(--acc)")}
          onMouseLeave={e => (e.currentTarget.style.borderBottomColor = "rgba(79,143,255,.3)")}
        >{match[1]}</a>
      );
    } else if (match[3]) {
      // Bold **text**
      elements.push(<strong key={match.index} style={{ fontWeight: 500, color: "var(--t1)" }}>{match[3]}</strong>);
    }

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    elements.push(text.slice(lastIndex));
  }

  if (elements.length === 0) return <>{text}</>;
  return <>{elements}</>;
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
