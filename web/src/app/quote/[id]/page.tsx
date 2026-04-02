"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { fetchQuote, streamChat, markQuoteAsRead, type QuoteDetail } from "@/lib/api";
import type { UIMessage } from "@/lib/types";
import { useBreakpoints } from "@/lib/useMediaQuery";
import QuoteHeader from "@/components/quote/QuoteHeader";
import QuoteTabBar from "@/components/quote/QuoteTabBar";
import DetailView from "@/components/quote/DetailView";
import ChatView from "@/components/quote/ChatView";
import Section from "@/components/quote/Section";
import ChatInput from "@/components/chat/ChatInput";

export default function QuotePage() {
  const router = useRouter();
  const params = useParams();
  const quoteId = params.id as string;

  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [tab, setTab] = useState<"detail" | "chat">("chat");
  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const dragCounter = useRef(0);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionText, setActionText] = useState("");

  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchQuote(quoteId).then(q => {
      setQuote(q);
      if (!q.is_read) {
        markQuoteAsRead(quoteId).catch(() => {});
      }
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
      if (q.status === "validated" || q.status === "sent") {
        setTab("detail");
      }
    }).finally(() => setLoading(false));
  }, [quoteId]);

  // Prevent browser from opening dropped files globally
  useEffect(() => {
    const prevent = (e: DragEvent) => { e.preventDefault(); e.stopPropagation(); };
    document.addEventListener("dragover", prevent);
    document.addEventListener("drop", prevent);
    return () => { document.removeEventListener("dragover", prevent); document.removeEventListener("drop", prevent); };
  }, []);

  useEffect(() => {
    if (tab === "chat") endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, tab]);

  const send = useCallback(async () => {
    if ((!input.trim() && attachedFiles.length === 0) || sending) return;
    const text = input.trim();
    const filesToSend = [...attachedFiles];
    const fileNames = filesToSend.map(f => f.name).join(", ");
    const uid = `u-${Date.now()}`;
    const aid = `a-${Date.now()}`;

    setMessages(p => [...p,
      { id: uid, role: "user", content: text, attachmentName: fileNames || undefined },
      { id: aid, role: "assistant", content: "", isStreaming: true },
    ]);
    setInput(""); setAttachedFiles([]); setSending(true); setActionText("");
    if (tab === "detail") setTab("chat");

    try {
      let acc = "";
      let gotDone = false;
      for await (const chunk of streamChat(quoteId, text, filesToSend.length > 0 ? filesToSend : undefined)) {
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
      if (!gotDone) {
        setActionText("");
        const errorMsg = acc
          ? acc + "\n\n⚠️ _La conexión se interrumpió._"
          : "⚠️ La conexión se interrumpió. Intentá de nuevo.";
        setMessages(p => p.map(m => m.id === aid ? { ...m, content: errorMsg, isStreaming: false } : m));
      }
    } catch {
      setActionText("");
      setMessages(p => p.map(m => m.id === aid ? { ...m, content: "⚠️ Error de conexión. Intentá de nuevo.", isStreaming: false } : m));
    } finally {
      setSending(false);
    }
  }, [input, attachedFiles, sending, quoteId, tab]);

  const { isMobile } = useBreakpoints();

  const onKey = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  }, [send]);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--t3)", fontSize: 13 }}>
      Cargando...
    </div>
  );

  const chatInputProps = {
    input, setInput,
    files: attachedFiles, setFiles: setAttachedFiles,
    dragActive, setDragActive,
    dragCounterRef: dragCounter,
    sending, send, onKey,
    fileRef,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <QuoteHeader quote={quote} onBack={() => router.push("/")} />
      <QuoteTabBar tab={tab} setTab={setTab} canShowDetail={!!quote && quote.status !== "draft"} />

      {tab === "detail" ? (
        <div style={{ flex: 1, overflowY: "auto", padding: isMobile ? "16px 14px" : "24px 28px" }}>
          <DetailView quote={quote} breakdown={quote?.quote_breakdown || null} onSwitchToChat={() => setTab("chat")} />
          <Section title="Modificaciones" style={{ marginTop: 20 }}>
            <div style={{ fontSize: 12, color: "var(--t3)", marginBottom: 10 }}>
              Escribí un cambio y Valentina regenera los documentos automáticamente.
            </div>
            <ChatInput {...chatInputProps} />
            <button onClick={() => setTab("chat")} style={{
              marginTop: 8, background: "none", border: "none", color: "var(--acc)",
              fontSize: 12, cursor: "pointer", fontFamily: "inherit", padding: 0,
            }}>
              Ver historial completo →
            </button>
          </Section>
        </div>
      ) : (
        <ChatView messages={messages} actionText={actionText} endRef={endRef} chatInputProps={chatInputProps} />
      )}
    </div>
  );
}
