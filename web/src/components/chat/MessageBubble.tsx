import clsx from "clsx";
import type { UIMessage } from "@/app/quote/[id]/page";

interface Props { message: UIMessage; actionText?: string; }

export default function MessageBubble({ message, actionText }: Props) {
  const isV = message.role === "assistant";

  if (!isV) {
    return (
      <div className="msg-anim flex gap-3 flex-row-reverse items-start">
        <Avatar isV={false} />
        <div className="max-w-[85%] md:max-w-[70%] lg:max-w-[52%] px-3 md:px-4 py-2.5 md:py-3 bg-acc-bg border border-acc-hover rounded-[12px_2px_12px_12px] text-sm md:text-[15px] leading-[1.65] text-white/[0.78]">
          {message.attachmentName && (
            <div className="inline-flex items-center gap-[5px] px-2 py-1 rounded-[5px] bg-white/[0.08] border border-b1 text-[11px] text-t2 mb-[7px]">
              📎 {message.attachmentName}
            </div>
          )}
          <p>{message.content}</p>
        </div>
      </div>
    );
  }

  const blocks = parseBlocks(message.content, message.isStreaming, actionText);

  return (
    <div className="msg-anim flex gap-3 items-start">
      <Avatar isV />
      <div className="flex-1 border border-b2 rounded-[2px_12px_12px_12px] overflow-hidden">
        {blocks.map((block, i) => (
          <Block key={i} block={block} isLast={i === blocks.length - 1} isStreaming={!!message.isStreaming && i === blocks.length - 1} actionText={actionText} />
        ))}
      </div>
    </div>
  );
}

// ── BLOCK RENDERER ──────────────────────────────────────────────────────────

type BlockType = { type: "thinking" | "text" | "raw"; content: string };

function parseBlocks(content: string, isStreaming?: boolean, actionText?: string): BlockType[] {
  if (!content) return [{ type: "thinking", content: actionText || "" }];

  const blocks: BlockType[] = [];
  const lines = content.split("\n");
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

  if (thinkingLines.length > 0) blocks.push({ type: "thinking", content: thinkingLines.join("\n") });
  if (restLines.join("").trim()) blocks.push({ type: "text", content: restLines.join("\n").trim() });
  if (blocks.length === 0) blocks.push({ type: "text", content });

  return blocks;
}

function Block({ block, isLast, isStreaming, actionText }: { block: BlockType; isLast: boolean; isStreaming: boolean; actionText?: string }) {
  if (block.type === "thinking") {
    const lines = block.content ? block.content.split("\n") : [""];
    return (
      <div className={clsx("px-[18px] py-3 bg-s2 flex flex-col gap-1.5", !isLast && "border-b border-b1")}>
        {lines.map((line, i) => (
          <div key={i} className="flex items-center gap-[7px] text-[11px] text-t3 italic">
            <div
              className="w-[5px] h-[5px] rounded-full bg-acc shrink-0 animate-[pulse_1.4s_ease-in-out_infinite]"
              style={{ animationDelay: `${i * 0.3}s` }}
            />
            {line || (isStreaming ? (actionText || "Procesando...") : "")}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={clsx("px-[18px] py-3.5 bg-s2 text-[15px] leading-[1.7] text-t2", !isLast && "border-b border-b1")}>
      <FormattedText text={block.content} isStreaming={isStreaming} />
    </div>
  );
}

// ── TEXT FORMATTER ───────────────────────────────────────────────────────────

function FormattedText({ text, isStreaming }: { text: string; isStreaming?: boolean }) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Markdown table
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
      elements.push(<div key={i} className="h-1.5" />);
    } else if (line.trim() === "---") {
      elements.push(<hr key={i} className="border-none border-t border-b2 my-3.5" />);
    } else if (line.startsWith("### ")) {
      elements.push(
        <div key={i} className="font-semibold text-t1 text-[15px] mt-[18px] mb-2 pb-1.5 border-b border-b1 -tracking-[0.01em]">
          <InlineFormat text={line.slice(4)} />
        </div>
      );
    } else if (line.startsWith("## ")) {
      elements.push(
        <div key={i} className="font-semibold text-t1 text-xl mt-1 mb-1 -tracking-[0.02em] leading-[1.3]">
          <InlineFormat text={line.slice(3)} />
        </div>
      );
    } else if (line.startsWith("**") && line.endsWith("**")) {
      elements.push(
        <p key={i} className="font-medium text-t2 text-[13px]">
          <InlineFormat text={line} />
        </p>
      );
    } else if (line.startsWith("\u2705") || line.startsWith("\u26A0") || line.startsWith("\u274C")) {
      elements.push(<p key={i} className="text-t1">{line}</p>);
    } else if (line.startsWith("- ")) {
      elements.push(
        <p key={i} className="mb-[3px] pl-3">
          <span className="text-t3 mr-1.5">•</span>
          <InlineFormat text={line.slice(2)} />
        </p>
      );
    } else {
      elements.push(<p key={i} className="mb-0.5"><InlineFormat text={line} /></p>);
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
  const dataLines = lines.filter(l => !l.match(/^\|[\s\-:|]+\|$/));
  if (dataLines.length === 0) return null;

  const parseRow = (line: string) => line.split("|").slice(1, -1).map(c => c.trim());
  const header = parseRow(dataLines[0]);
  const rows = dataLines.slice(1).map(parseRow);
  const isTotal = (row: string[]) => row.some(c => c.toLowerCase().includes("total"));

  return (
    <div className="my-2 rounded-[10px] overflow-hidden border border-b1 bg-white/[0.02]">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {header.map((h, j) => (
              <th key={j} className={clsx(
                "px-3.5 py-2 font-semibold text-t1 text-[13px] tracking-wide border-b-2 border-white/10",
                j >= 1 ? "text-right" : "text-left",
              )}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => {
            const isTotalRow = isTotal(row);
            return (
              <tr key={ri} className={isTotalRow ? "bg-white/[0.04]" : ""}>
                {row.map((cell, ci) => (
                  <td key={ci} className={clsx(
                    "px-3.5 py-2.5 text-sm leading-[1.4]",
                    ci >= 1 ? "text-right" : "text-left",
                    isTotalRow ? "font-semibold text-t1 border-b-0" : "font-normal text-t2 border-b border-white/[0.06]",
                  )}>
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
  const elements: React.ReactNode[] = [];
  const regex = /\[([^\]]+)\]\(([^)]+)\)|\*\*(.*?)\*\*|(https?:\/\/[^\s,)]+)|`(\/files\/[^`]+)`/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) elements.push(text.slice(lastIndex, match.index));

    if (match[1] && match[2]) {
      elements.push(
        <a key={match.index} href={match[2]} target="_blank" rel="noopener noreferrer" className="text-acc no-underline border-b border-acc/30">{match[1]}</a>
      );
    } else if (match[3]) {
      elements.push(<strong key={match.index} className="font-medium text-t1">{match[3]}</strong>);
    } else if (match[4]) {
      const url = match[4];
      const label = url.includes("drive.google") ? "Abrir en Drive" :
                    url.includes("/files/") && url.endsWith(".pdf") ? "Descargar PDF" :
                    url.includes("/files/") && url.endsWith(".xlsx") ? "Descargar Excel" : "Abrir link";
      elements.push(
        <a key={match.index} href={url} target="_blank" rel="noopener noreferrer" className="text-acc no-underline border-b border-acc/30">{label}</a>
      );
    } else if (match[5]) {
      const path = match[5];
      const label = path.endsWith(".pdf") ? "Descargar PDF" : path.endsWith(".xlsx") ? "Descargar Excel" : "Descargar archivo";
      elements.push(
        <a key={match.index} href={path} target="_blank" rel="noopener noreferrer" className="text-acc no-underline border-b border-acc/30">{label}</a>
      );
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) elements.push(text.slice(lastIndex));
  if (elements.length === 0) return <>{text}</>;
  return <>{elements}</>;
}

// ── AVATAR ───────────────────────────────────────────────────────────────────

function Avatar({ isV }: { isV: boolean }) {
  return (
    <div className={clsx(
      "w-[30px] h-[30px] rounded-full shrink-0 flex items-center justify-center text-[11px] font-semibold",
      isV ? "bg-acc text-white" : "bg-s3 text-t2 border border-b2",
    )}>
      {isV ? "V" : "OP"}
    </div>
  );
}
