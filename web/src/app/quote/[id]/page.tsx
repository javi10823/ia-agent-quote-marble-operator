"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { fetchQuote, streamChat, type QuoteDetail } from "@/lib/api";
import MessageBubble from "@/components/chat/MessageBubble";

export interface UIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  attachmentName?: string;
}

export default function QuotePage() {
  const router = useRouter();
  const params = useParams();
  const quoteId = params.id as string;

  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState("");
  const [planFile, setPlanFile] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionText, setActionText] = useState("");

  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetchQuote(quoteId).then(q => {
      setQuote(q);
      const uiMsgs: UIMessage[] = q.messages
        .filter((m: any) => m.role === "user" || m.role === "assistant")
        .map((m: any, i: number) => ({
          id: `stored-${i}`,
          role: m.role,
          content: typeof m.content === "string"
            ? m.content
            : (m.content as any[]).filter(c => c.type === "text").map(c => c.text || "").join(""),
        }));
      setMessages(uiMsgs);
    }).finally(() => setLoading(false));
  }, [quoteId]);

  useEffect(() => {
    if (!loading && messages.length === 0) {
      setMessages([{
        id: "greeting", role: "assistant",
        content: "Hola 👋 Soy Valentina.\n\nPasame el enunciado del trabajo y/o el plano. Si tenés un PDF o imagen, adjuntalo directamente.",
      }]);
    }
  }, [loading, messages.length]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (taRef.current) {
      taRef.current.style.height = "auto";
      taRef.current.style.height = `${Math.min(taRef.current.scrollHeight, 110)}px`;
    }
  }, [input]);

  const send = useCallback(async () => {
    if ((!input.trim() && !planFile) || sending) return;
    const text = input.trim();
    const file = planFile;
    const uid = `u-${Date.now()}`;
    const aid = `a-${Date.now()}`;

    setMessages(p => [...p,
      { id: uid, role: "user", content: text, attachmentName: file?.name },
      { id: aid, role: "assistant", content: "", isStreaming: true },
    ]);
    setInput(""); setPlanFile(null); setSending(true); setActionText("");

    try {
      let acc = "";
      let gotDone = false;
      for await (const chunk of streamChat(quoteId, text, file || undefined)) {
        if (chunk.type === "text") {
          acc += chunk.content;
          setActionText("");
          setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc } : m));
        } else if (chunk.type === "action") {
          setActionText(chunk.content);
        } else if (chunk.type === "done") {
          gotDone = true;
          setActionText("");
          setMessages(p => p.map(m => m.id === aid ? { ...m, isStreaming: false } : m));
          const updated = await fetchQuote(quoteId);
          setQuote(updated);
        }
      }
      // Stream ended without a done event — connection dropped
      if (!gotDone) {
        setActionText("");
        const errorMsg = acc
          ? acc + "\n\n⚠️ _La conexión se interrumpió. El texto anterior puede estar incompleto._"
          : "⚠️ La conexión se interrumpió antes de recibir una respuesta. Por favor intentá de nuevo.";
        setMessages(p => p.map(m => m.id === aid ? { ...m, content: errorMsg, isStreaming: false } : m));
      }
    } catch {
      setActionText("");
      setMessages(p => p.map(m => m.id === aid ? { ...m, content: "⚠️ Hubo un error de conexión. Verificá tu internet e intentá de nuevo.", isStreaming: false } : m));
    } finally {
      setSending(false);
    }
  }, [input, planFile, sending, quoteId]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--t3)", fontSize: 13 }}>
      Cargando...
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 28px", borderBottom: "1px solid var(--b1)",
        flexShrink: 0, background: "var(--s1)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <button onClick={() => router.push("/")} style={backStyle}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <div>
            <div style={{ fontSize: 15, fontWeight: 500, letterSpacing: "-0.02em" }}>
              {quote?.client_name || "Nuevo presupuesto"}
            </div>
            <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 2 }}>
              {quote?.project}{quote?.material ? ` · ${quote.material}` : ""}
            </div>
          </div>
        </div>

        {/* File links */}
        {(quote?.pdf_url || quote?.excel_url || quote?.drive_url) && (
          <div style={{ display: "flex", gap: 6 }}>
            {quote?.pdf_url && <FileLink href={quote.pdf_url} label="PDF" color="#ff6b63" borderColor="rgba(255,69,58,.22)" />}
            {quote?.excel_url && <FileLink href={quote.excel_url} label="Excel" color="var(--grn)" borderColor="rgba(48,209,88,.22)" />}
            {quote?.drive_url && <FileLink href={quote.drive_url} label="Drive" color="var(--acc)" borderColor="var(--acc3)" />}
          </div>
        )}
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "28px 28px 16px", display: "flex", flexDirection: "column", gap: 20 }}>
        {messages.map(msg => <MessageBubble key={msg.id} message={msg} actionText={msg.isStreaming ? actionText : undefined} />)}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div style={{ flexShrink: 0, padding: "14px 28px 18px", borderTop: "1px solid var(--b1)", background: "var(--s1)" }}>
        {planFile && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "6px 10px", background: "var(--s3)",
            border: "1px solid var(--b1)", borderRadius: 6,
            fontSize: 11, color: "var(--t2)", marginBottom: 8,
          }}>
            <span>📎</span>
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{planFile.name}</span>
            <button onClick={() => setPlanFile(null)} style={{ background: "none", border: "none", color: "var(--t3)", cursor: "pointer", fontSize: 13 }}>✕</button>
          </div>
        )}
        <div style={{
          display: "flex", alignItems: "flex-end", gap: 8,
          background: "var(--s3)", border: "1px solid var(--b2)",
          borderRadius: 12, padding: "10px 10px 10px 16px",
          transition: "border-color .15s",
        }}>
          <textarea ref={taRef} value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={onKey} rows={1} disabled={sending}
            placeholder="Escribí el enunciado o adjuntá el plano..."
            style={{
              flex: 1, background: "transparent", border: "none", outline: "none",
              fontFamily: "inherit", fontSize: 13, color: "var(--t1)",
              resize: "none", lineHeight: 1.5, maxHeight: 110,
            }}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 5, flexShrink: 0 }}>
            <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png" style={{ display: "none" }}
              onChange={e => { if (e.target.files?.[0]) setPlanFile(e.target.files[0]); e.target.value = ""; }}
            />
            <IconBtn onClick={() => fileRef.current?.click()} title="Adjuntar plano">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
              </svg>
            </IconBtn>
            <IconBtn onClick={send} primary disabled={sending || (!input.trim() && !planFile)}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </IconBtn>
          </div>
        </div>
        <div style={{ fontSize: 10, color: "var(--t4)", textAlign: "center", marginTop: 7, letterSpacing: "0.02em" }}>
          Enter para enviar · Shift+Enter para nueva línea
        </div>
      </div>
    </div>
  );
}

function FileLink({ href, label, color, borderColor }: { href: string; label: string; color: string; borderColor: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" style={{
      display: "flex", alignItems: "center", gap: 5,
      padding: "6px 12px", borderRadius: 6,
      fontSize: 11, fontWeight: 500, textDecoration: "none",
      border: `1px solid ${borderColor}`, background: "transparent",
      color, transition: "all .1s",
    }}>
      {label === "PDF" ? "📄" : label === "Excel" ? "📊" : "☁"} {label}
    </a>
  );
}

function IconBtn({ onClick, children, primary, disabled, title }: {
  onClick: () => void; children: React.ReactNode;
  primary?: boolean; disabled?: boolean; title?: string;
}) {
  return (
    <button onClick={onClick} disabled={disabled} title={title} style={{
      width: 32, height: 32, borderRadius: "50%",
      border: primary ? "none" : "1px solid var(--b1)",
      background: primary ? "var(--acc)" : "transparent",
      color: primary ? "#fff" : "var(--t2)",
      cursor: disabled ? "not-allowed" : "pointer",
      display: "flex", alignItems: "center", justifyContent: "center",
      transition: "all .1s", opacity: disabled ? 0.4 : 1,
    }}>
      {children}
    </button>
  );
}

const backStyle: React.CSSProperties = {
  width: 30, height: 30, borderRadius: 6,
  border: "1px solid var(--b1)", background: "transparent",
  color: "var(--t2)", cursor: "pointer",
  display: "flex", alignItems: "center", justifyContent: "center",
  transition: "all .1s",
};
