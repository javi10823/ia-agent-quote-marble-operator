"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { fetchQuote, streamChat, markQuoteAsRead, validateQuote, updateQuote, reopenMeasurements, reopenContext, type QuoteDetail, type QuoteEditablePatch } from "@/lib/api";
import { useQuotes } from "@/lib/quotes-context";
import MessageBubble from "@/components/chat/MessageBubble";
import CopyButton from "@/components/chat/CopyButton";
import ZoneSelector from "@/components/chat/ZoneSelector";
import { selectZone } from "@/lib/api";
import { ResumenObraCard } from "@/components/quote/ResumenObraCard";
import { EmailDraftCard } from "@/components/quote/EmailDraftCard";
import { CondicionesCard } from "@/components/quote/CondicionesCard";
import RegenerateButton from "@/components/quote/RegenerateButton";
import EditableField from "@/components/quote/EditableField";
import ContextAnalysis from "@/components/chat/ContextAnalysis";
import HomeHero from "@/components/chat/HomeHero";
import { useToast } from "@/lib/toast-context";
import clsx from "clsx";
import { A, I, O, N, DOT, SUP2, DASH, ITEM, WARN, CIRCLE, ARROW, XMARK, CLOUD, WAVE, PAGE, PICTURE, CLIP, RULER, TAG, FOLDER, CHART } from "@/lib/chars";
import { VALID_FILE_TYPES as PARENT_VALID_TYPES, MAX_FILE_SIZE as PARENT_MAX_SIZE, MAX_FILES as PARENT_MAX_FILES } from "@/lib/constants";

export interface UIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  attachmentName?: string;
}

// ── HELPERS ──────────────────────────────────────────────────────────────────

const fmtARS = (n: number | null | undefined) => {
  if (n == null || isNaN(n)) return DASH;
  return `$${Math.round(n).toLocaleString("es-AR")}`;
};
const fmtUSD = (n: number | null | undefined) => {
  if (n == null || isNaN(n)) return DASH;
  return `USD ${Math.round(n).toLocaleString("en-US")}`;
};
const fmtQty = (n: number | null | undefined) => {
  if (n == null || isNaN(n)) return DASH;
  if (Math.abs(n - Math.round(n)) < 0.05) return String(Math.round(n));
  return n.toFixed(2).replace(".", ",");
};

// Snapshot completo para "📋 Copiar todo": TODO el diálogo —
// enunciado + cada mensaje del operador y Valentina (texto, tablas, adjuntos),
// más el despiece del Dual Read convertido a tabla markdown.
function buildFullSnapshot(quote: QuoteDetail | null, messages: UIMessage[]): string {
  const parts: string[] = [];
  parts.push(`## SNAPSHOT — ${quote?.client_name || "Cliente"} / ${quote?.project || "Proyecto"}`);
  parts.push("");

  const datos: string[] = [];
  if (quote?.client_name) datos.push(`- Cliente: ${quote.client_name}`);
  if (quote?.project) datos.push(`- Proyecto: ${quote.project}`);
  if (quote?.material) datos.push(`- Material: ${quote.material}`);
  if (datos.length) {
    parts.push("### Datos");
    parts.push(...datos);
    parts.push("");
  }

  parts.push("### Conversación");
  parts.push("");

  messages.forEach((m) => {
    const content = m.content.trim();
    if (!content || content === "." || content === "..") return;
    if (content.startsWith("__ZONE_SELECTOR__")) return;
    if (content.startsWith("__CONTEXT_ANALYSIS__")) return;
    if (content.startsWith("[SYSTEM_TRIGGER")) return;
    if (content.startsWith("[CONTEXT_CONFIRMED]")) return;
    // PR #379 — Filtros defensivos para quotes viejos que quedaron con
    // placeholders en DB (pre-#379 el backend persistía markers `_SHOWN_`
    // vacíos y un fake user turn "(contexto confirmado)"). En quotes
    // nuevos estos ya no aparecen — el backend persiste el JSON real de
    // la card. Estos filtros evitan el leak visual para el historial
    // legacy hasta que se corra un PR de rehydrate aparte.
    if (content === "__DUAL_READ_CARD_SHOWN__") return;
    if (content === "__CONTEXT_ANALYSIS_SHOWN__") return;
    if (content === "(contexto confirmado)") return;
    // También filtramos bloques internos del system prompt que pre-#379
    // se persistían como user turn (TEXTO EXTRAÍDO DEL PDF + hints de
    // SISTEMA) vía copy.deepcopy(content).
    if (content.startsWith("[TEXTO EXTRAÍDO DEL PDF")) return;
    if (content.startsWith("[SISTEMA")) return;

    if (content.startsWith("[DUAL_READ_CONFIRMED]")) {
      parts.push("**Operador:** \u2705 Medidas verificadas", "");
      return;
    }

    if (content.startsWith("__DUAL_READ__")) {
      try {
        const d = JSON.parse(content.replace("__DUAL_READ__", ""));
        const table: string[] = ["**Valentina \u2014 Despiece (Dual Read):**", "", "| Pieza | Medida | m\u00b2 |", "|---|---|---|"];
        let total = 0;
        d.sectores?.forEach((s: any) => {
          s.tramos?.forEach((t: any) => {
            const m2 = t.m2?.valor || 0;
            total += m2;
            const largo = (t.largo_m?.valor || 0).toFixed(2);
            const ancho = (t.ancho_m?.valor || 0).toFixed(2);
            table.push(`| ${t.descripcion || t.id} | ${largo} \u00d7 ${ancho} | ${m2.toFixed(2)} |`);
            t.zocalos?.forEach((z: any) => {
              if ((z.ml || 0) <= 0) return;
              const zm2 = z.ml * (z.alto_m || 0);
              total += zm2;
              table.push(`| Z\u00f3c. ${z.lado} | ${z.ml.toFixed(2)} ml \u00d7 ${(z.alto_m || 0).toFixed(2)} | ${zm2.toFixed(2)} |`);
            });
          });
        });
        table.push(`| **Total** | \u2014 | **${total.toFixed(2)}** |`);
        parts.push(...table, "");
      } catch {
        /* skip */
      }
      return;
    }

    const label = m.role === "user" ? "**Operador:**" : "**Valentina:**";
    parts.push(label);
    if (m.attachmentName) parts.push(`_[Adjunto: ${m.attachmentName}]_`);
    parts.push(content);
    parts.push("");
  });

  return parts.join("\n").trim();
}

const STATUS_CLASS: Record<string, { label: string; cls: string; text: string; dotColor: string }> = {
  draft:     { label: "Borrador",  cls: "bg-amb-bg text-amb", text: "text-amb",          dotColor: "var(--amb)" },
  pending:   { label: "Pendiente", cls: "bg-acc-bg text-acc", text: "text-[#b299ff]",    dotColor: "#b299ff" },
  validated: { label: "Validado",  cls: "bg-grn-bg text-grn", text: "text-grn",          dotColor: "var(--grn)" },
  sent:      { label: "Enviado",   cls: "bg-acc-bg text-acc", text: "text-acc",          dotColor: "var(--acc)" },
};

// ── MAIN ─────────────────────────────────────────────────────────────────────

export default function QuotePage() {
  const router = useRouter();
  const params = useParams();
  const quoteId = params.id as string;
  const toast = useToast();

  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [tab, setTab] = useState<"detail" | "chat">("chat");
  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const dragCounter = useRef(0);
  const [dropError, setDropError] = useState<string | null>(null);

  // Validación + añadir de archivos soltados sobre el área completa del chat.
  // Replica la lógica del `addFiles` del composer para que un drop en
  // cualquier parte del chat funcione idéntico que un drop sobre el input.
  const addDroppedFiles = (newFiles: FileList | File[]) => {
    if (sending) return;
    const arr = Array.from(newFiles);
    const valid: File[] = [];
    for (const f of arr) {
      if (!PARENT_VALID_TYPES.some(t => f.type.includes(t.split("/")[1]))) {
        setDropError(`"${f.name}" ${DASH} tipo no soportado`);
        setTimeout(() => setDropError(null), 3000);
        continue;
      }
      if (f.size > PARENT_MAX_SIZE) {
        setDropError(`"${f.name}" ${DASH} m${A}ximo 10MB`);
        setTimeout(() => setDropError(null), 3000);
        continue;
      }
      if (attachedFiles.length + valid.length >= PARENT_MAX_FILES) {
        setDropError(`M${A}ximo ${PARENT_MAX_FILES} archivos`);
        setTimeout(() => setDropError(null), 3000);
        break;
      }
      if (attachedFiles.some(ef => ef.name === f.name && ef.size === f.size)) continue;
      if (valid.some(ef => ef.name === f.name && ef.size === f.size)) continue;
      valid.push(f);
    }
    if (valid.length > 0) setAttachedFiles([...attachedFiles, ...valid]);
  };

  // Drag handlers del wrapper del chat — el overlay full-chat se muestra
  // cuando hay archivos siendo arrastrados. El dragCounter compensa los
  // dragEnter/Leave nested.
  const wrapperDragEnter = (e: React.DragEvent) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    dragCounter.current++;
    setDragActive(true);
  };
  const wrapperDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current--;
    if (dragCounter.current <= 0) { dragCounter.current = 0; setDragActive(false); }
  };
  const wrapperDrop = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current = 0;
    setDragActive(false);
    if (e.dataTransfer.files.length > 0) addDroppedFiles(e.dataTransfer.files);
  };
  const [sending, setSending] = useState(false);
  const [multiPiece, setMultiPiece] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionText, setActionText] = useState("");
  const [generating, setGenerating] = useState(false);
  const [lastFailedMsg, setLastFailedMsg] = useState<string | null>(null);
  const [lastInlineResponse, setLastInlineResponse] = useState<UIMessage | null>(null);
  const [inlineActionText, setInlineActionText] = useState("");
  // PR #381 — modal styled reemplaza window.confirm del "Editar despiece".
  // Estado { open, busy } para coordinar UI del modal (backdrop bloquea
  // clicks durante el POST + spinner en botón de confirmar).
  const [reopenModal, setReopenModal] = useState<{ open: boolean; busy: boolean }>({
    open: false, busy: false,
  });
  // PR #383 — segundo modal para "Editar contexto". Misma shape que
  // reopenModal, flujo análogo (POST /reopen-context + refresh del quote).
  const [contextModal, setContextModal] = useState<{ open: boolean; busy: boolean }>({
    open: false, busy: false,
  });
  const sentFromDetail = useRef(false);
  const { refresh: refreshQuotes, markRead } = useQuotes();

  const endRef = useRef<HTMLDivElement>(null);
  const inlineEndRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const userInteracted = useRef(false);

  const parseMessages = (rawMessages: any[]): UIMessage[] =>
    rawMessages
      .filter((m: any) => m.role === "user" || m.role === "assistant")
      .map((m: any, i: number) => ({
        id: `stored-${i}`,
        role: m.role as "user" | "assistant",
        content: typeof m.content === "string"
          ? m.content
          : (m.content as any[]).filter(c => c.type === "text").map(c => c.text || "").join(""),
      }))
      .filter(m => {
        const text = m.content.trim();
        if (!text || text === "." || text === "..") return false;
        return true;
      });

  useEffect(() => {
    fetchQuote(quoteId).then(async (q) => {
      setQuote(q);
      if (!q.is_read) { markQuoteAsRead(quoteId).catch(() => {}); markRead(quoteId); }

      setMessages(parseMessages(q.messages));
      if (q.status === "validated" || q.status === "sent" || q.status === "pending" || q.source === "web") setTab("detail");
    }).catch((err: any) => {
      // Quote was deleted elsewhere (another tab, cleanup job, etc.) — don't
      // strand the operator on an orphan page where every chat returns 404.
      if (err?.code === "QUOTE_NOT_FOUND") {
        abortRef.current?.abort();
        router.replace("/");
        return;
      }
      setLoadError(err.message || "Error al cargar presupuesto");
    }).finally(() => setLoading(false));
  }, [quoteId, router]);

  // Abort SSE stream on unmount or quoteId change
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, [quoteId]);

  // Poll for breakdown when web quote has files but no breakdown yet (background processing)
  useEffect(() => {
    if (!quote || quote.source !== "web") return;
    if (quote.quote_breakdown) return;
    if (!quote.source_files || quote.source_files.length === 0) return;

    const interval = setInterval(async () => {
      try {
        const updated = await fetchQuote(quoteId);
        if (updated.quote_breakdown) {
          setQuote(updated);
          clearInterval(interval);
        }
      } catch { /* ignore */ }
    }, 5000);

    return () => clearInterval(interval);
  }, [quote?.quote_breakdown, quote?.source, quote?.source_files, quoteId]);

  useEffect(() => {
    const prevent = (e: DragEvent) => { e.preventDefault(); e.stopPropagation(); };
    document.addEventListener("dragover", prevent);
    document.addEventListener("drop", prevent);
    return () => {
      document.removeEventListener("dragover", prevent);
      document.removeEventListener("drop", prevent);
      dragCounter.current = 0;
    };
  }, []);

  useEffect(() => {
    if (!userInteracted.current) return;
    if (tab === "chat") endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, tab]);

  useEffect(() => {
    if (lastInlineResponse && tab === "detail") {
      inlineEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [lastInlineResponse, tab]);

  const send = useCallback(async (overrideText?: string) => {
    const rawText = overrideText ?? input;
    if ((!rawText.trim() && attachedFiles.length === 0) || sending) return;
    userInteracted.current = true;

    // Multi-piece mode: don't send files, ask Valentina to request individual captures
    if (multiPiece && attachedFiles.length > 0) {
      const fileCount = attachedFiles.length;
      const text = (rawText.trim() || "") + `\n[SISTEMA: El operador adjuntó ${fileCount} archivo(s) pero marcó "múltiples piezas". NO proceses los archivos adjuntos. Respondé EXACTAMENTE: "Veo que el plano tiene múltiples piezas. Para leer las medidas correctamente, necesito que me mandes una captura/foto de CADA pieza por separado (una imagen por cuadro/box). Así evitamos errores en las cotas."]`;
      const uid = `u-${Date.now()}`;
      const aid = `a-${Date.now()}`;
      setMessages(p => [...p,
        { id: uid, role: "user", content: rawText.trim() || "(plano adjunto)", attachmentName: attachedFiles.map(f => f.name).join(", ") },
        { id: aid, role: "assistant", content: "", isStreaming: true },
      ]);
      setInput(""); setAttachedFiles([]); setMultiPiece(false); setSending(true);
      const isFromDetail = tab === "detail";
      sentFromDetail.current = isFromDetail;
      if (isFromDetail) { setLastInlineResponse({ id: aid, role: "assistant", content: "", isStreaming: true }); setInlineActionText(""); }
      else { setActionText(""); }
      try {
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;
        let acc = "";
        let gotDone = false;
        for await (const chunk of streamChat(quoteId, text, undefined, controller.signal)) {
          if (chunk.type === "text") { acc += chunk.content; setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc } : m)); }
          else if (chunk.type === "done") { gotDone = true; setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc, isStreaming: false } : m)); }
        }
        if (!gotDone) setMessages(p => p.map(m => m.id === aid ? { ...m, content: "Veo que el plano tiene m\u00faltiples piezas. Para leer las medidas correctamente, necesito que me mandes una captura/foto de CADA pieza por separado (una imagen por cuadro/box). As\u00ed evitamos errores en las cotas.", isStreaming: false } : m));
      } catch (e: any) {
        if (e?.code === "QUOTE_NOT_FOUND") {
          abortRef.current?.abort();
          router.replace("/");
          return;
        }
        setMessages(p => p.map(m => m.id === aid ? { ...m, content: "Veo que el plano tiene m\u00faltiples piezas. Para leer las medidas correctamente, necesito que me mandes una captura/foto de CADA pieza por separado (una imagen por cuadro/box). As\u00ed evitamos errores en las cotas.", isStreaming: false } : m));
      }
      finally { setSending(false); }
      return;
    }

    const text = rawText.trim();
    const filesToSend = [...attachedFiles];
    const fileNames = filesToSend.map(f => f.name).join(", ");
    const uid = `u-${Date.now()}`;
    const aid = `a-${Date.now()}`;

    const isFromDetail = tab === "detail";
    sentFromDetail.current = isFromDetail;

    // System triggers are invisible — don't add user message bubble
    const isSystemTrigger = text.startsWith("[SYSTEM_TRIGGER:");
    setMessages(p => [
      ...p,
      ...(isSystemTrigger ? [] : [{ id: uid, role: "user" as const, content: text, attachmentName: fileNames || undefined }]),
      { id: aid, role: "assistant" as const, content: "", isStreaming: true },
    ]);
    setInput(""); setAttachedFiles([]); setSending(true);

    if (isFromDetail) {
      setLastInlineResponse({ id: aid, role: "assistant", content: "", isStreaming: true });
      setInlineActionText("");
    } else {
      setActionText("");
    }

    try {
      // Abort previous stream if any
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      let acc = "";
      let gotDone = false;
      let rafPending = false;
      const fromDetail = sentFromDetail.current;
      const flushAcc = () => {
        rafPending = false;
        setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc } : m));
        if (fromDetail) setLastInlineResponse(prev => prev ? { ...prev, content: acc } : prev);
      };
      for await (const chunk of streamChat(quoteId, text, filesToSend.length > 0 ? filesToSend : undefined, controller.signal)) {
        if (chunk.type === "text") {
          acc += chunk.content;
          if (fromDetail) setInlineActionText(""); else setActionText("");
          // Throttle state updates to 1 per animation frame
          if (!rafPending) { rafPending = true; requestAnimationFrame(flushAcc); }
        } else if (chunk.type === "zone_selector") {
          // Fix G: show zone selector to operator
          try {
            const selectorData = JSON.parse(chunk.content);
            acc = `__ZONE_SELECTOR__${chunk.content}`;
            setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc, isStreaming: false } : m));
          } catch { /* ignore parse errors */ }
        } else if (chunk.type === "dual_read_result") {
          try {
            acc = `__DUAL_READ__${chunk.content}`;
            setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc, isStreaming: false } : m));
          } catch { /* ignore parse errors */ }
        } else if (chunk.type === "context_analysis") {
          // PR G — análisis de contexto previo al despiece
          try {
            acc = `__CONTEXT_ANALYSIS__${chunk.content}`;
            setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc, isStreaming: false } : m));
          } catch { /* ignore parse errors */ }
        } else if (chunk.type === "action") {
          if (fromDetail) setInlineActionText(chunk.content); else setActionText(chunk.content);
        } else if (chunk.type === "done") {
          gotDone = true;
          if (fromDetail) setInlineActionText(""); else setActionText("");
          // Final flush with complete content + streaming=false
          setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc, isStreaming: false } : m));
          if (fromDetail) setLastInlineResponse({ id: aid, role: "assistant", content: acc, isStreaming: false });
          const [updated] = await Promise.all([
            fetchQuote(quoteId),
            refreshQuotes(),
          ]);
          setQuote(updated);
        }
      }
      if (!gotDone) {
        if (fromDetail) setInlineActionText(""); else setActionText("");
        const friendlyErr = `${WARN} El servicio est${A} moment${A}neamente saturado. Presion${A} "Reintentar" para volver a intentar.`;
        const errorMsg = acc ? acc + `\n\n${friendlyErr}` : friendlyErr;
        setMessages(p => p.map(m => m.id === aid ? { ...m, content: errorMsg, isStreaming: false } : m));
        if (fromDetail) setLastInlineResponse({ id: aid, role: "assistant", content: errorMsg, isStreaming: false });
        setLastFailedMsg(text);
      }
    } catch (e: any) {
      if (e?.code === "QUOTE_NOT_FOUND") {
        // Quote was deleted — bail out, stop the 404 POST spam, go home.
        abortRef.current?.abort();
        router.replace("/");
        return;
      }
      if (sentFromDetail.current) setInlineActionText(""); else setActionText("");
      const errContent = `${WARN} El servicio est${A} moment${A}neamente saturado. Presion${A} "Reintentar" para volver a intentar.`;
      setMessages(p => p.map(m => m.id === aid ? { ...m, content: errContent, isStreaming: false } : m));
      if (sentFromDetail.current) setLastInlineResponse({ id: aid, role: "assistant", content: errContent, isStreaming: false });
      setLastFailedMsg(text);
    } finally {
      setSending(false);
    }
  }, [input, attachedFiles, sending, quoteId, tab]);

  const handleGenerate = useCallback(async () => {
    if (generating) return;
    setGenerating(true);
    try {
      await validateQuote(quoteId);
      const updated = await fetchQuote(quoteId);
      setQuote(updated);
      refreshQuotes();
    } catch {
      // Error handled by toast in api.ts
    } finally {
      setGenerating(false);
    }
  }, [quoteId, generating]);

  const handleFieldUpdate = useCallback(async (patch: QuoteEditablePatch) => {
    await updateQuote(quoteId, patch);
    setQuote((prev) => (prev ? ({ ...prev, ...patch } as QuoteDetail) : prev));
    refreshQuotes();
  }, [quoteId, refreshQuotes]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  if (loading) return <div className="flex items-center justify-center h-full text-t3 text-[13px]">Cargando...</div>;
  if (loadError) return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <div className="text-err text-[13px]">✕ {loadError}</div>
      <button onClick={() => window.location.reload()} className="px-3 py-1.5 rounded-md text-xs font-medium border border-b1 bg-transparent text-t2 cursor-pointer hover:border-b2 hover:text-t1 transition">Reintentar</button>
    </div>
  );

  const st = STATUS_CLASS[quote?.status || "draft"];
  const bd = quote?.quote_breakdown || null;

  return (
    <div className="flex flex-col h-full">
      {/* Header — editorial: cliente Fraunces italic + status dot+text */}
      <div className="flex flex-col md:flex-row md:items-center justify-between px-4 md:px-9 py-4 md:py-5 border-b border-b1 shrink-0 bg-bg gap-2 md:gap-0">
        <div className="flex items-center gap-4">
          <button onClick={() => router.push("/")} className="w-[32px] h-[32px] rounded-md border border-b1 bg-transparent text-t2 cursor-pointer flex items-center justify-center hover:border-b2 hover:text-t1 transition">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2.5">
              <span className="font-serif italic text-[18px] md:text-[22px] font-medium text-t1 -tracking-[0.01em] truncate max-w-[200px] md:max-w-[500px] leading-tight">{quote?.client_name || "Nuevo presupuesto"}</span>
              <span className={clsx("inline-flex items-center gap-1.5 text-[12px] shrink-0 font-sans", st.text)}>
                <span className="w-[7px] h-[7px] rounded-full shrink-0" style={{ background: st.dotColor }} />
                {st.label}
              </span>
              {quote?.source === "web" && <span className="text-[9px] font-semibold font-mono tracking-wider px-1.5 py-[2px] rounded border border-[#b48fe0]/30 text-[#b48fe0] shrink-0 not-italic">WEB</span>}
            </div>
            <div className="text-xs text-t3 mt-1 truncate max-w-[600px] font-sans">
              {quote?.project}{quote?.material ? ` ${DOT} ${quote.material}` : ""}
            </div>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {quote?.drive_pdf_url && <FileLink href={quote.drive_pdf_url} label="PDF Drive" cls="border-acc/20 text-acc" />}
          {quote?.drive_excel_url && <FileLink href={quote.drive_excel_url} label="Excel Drive" cls="border-emerald-400/20 text-emerald-400" />}
          {!quote?.drive_pdf_url && quote?.pdf_url && <FileLink href={quote.pdf_url} label="PDF" cls="border-red-400/20 text-red-400" />}
          {/* Regenerar: solo si hay docs ya generados Y hay breakdown para reutilizar */}
          <RegenerateButton
            quoteId={quoteId}
            enabled={!!quote && !!bd && (!!quote.pdf_url || !!quote.drive_pdf_url)}
            onRegenerated={async () => {
              const updated = await fetchQuote(quoteId);
              setQuote(updated);
            }}
          />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-b1 bg-bg pl-4 md:pl-9">
        <TabBtn active={tab === "detail"} onClick={() => setTab("detail")} disabled={!quote || (quote.status === "draft" && quote.source !== "web")}>Detalle</TabBtn>
        <TabBtn active={tab === "chat"} onClick={() => setTab("chat")}>Chat</TabBtn>
      </div>

      {/* Content */}
      {tab === "detail" ? (
        <div className="flex-1 overflow-y-auto px-4 md:px-7 py-4 md:py-6">
          <DetailView quote={quote} breakdown={bd} onSwitchToChat={() => setTab("chat")} onGenerate={quote?.status === "pending" || quote?.status === "draft" ? handleGenerate : undefined} generating={generating} onFieldUpdate={handleFieldUpdate} />
          {/* Show modifications section only when quote has breakdown and is not sent */}
          {bd && quote?.status !== "sent" && (
            <Section title="Modificaciones" className="mt-5">
              <div className="text-xs text-t3 mb-2.5">{quote?.pdf_url ? `Escrib${I} un cambio y Valentina regenera los documentos autom${A}ticamente.` : `Escrib${I} un cambio y Valentina ajusta el presupuesto.`}</div>
              {/* Inline response from Valentina (above input so operator can reply below) */}
              {(sending && sentFromDetail.current) && !lastInlineResponse?.content && (
                <div className="mb-3.5 px-5 py-4 bg-s2 border border-b1 rounded-xl flex items-center gap-2.5">
                  <div className="w-[26px] h-[26px] rounded-full bg-acc flex items-center justify-center text-[11px] font-bold text-white shrink-0">V</div>
                  {inlineActionText ? (
                    <span className="text-xs text-t3 italic">{inlineActionText}</span>
                  ) : (
                    <div className="flex gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-t3 animate-pulse" />
                      <span className="w-1.5 h-1.5 rounded-full bg-t3 animate-pulse [animation-delay:200ms]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-t3 animate-pulse [animation-delay:400ms]" />
                    </div>
                  )}
                </div>
              )}
              {lastInlineResponse && lastInlineResponse.content && (
                <div className="mb-3.5 animate-[fadeIn_0.3s_ease]">
                  <MessageBubble message={lastInlineResponse} actionText={lastInlineResponse.isStreaming ? inlineActionText : undefined} />
                </div>
              )}
              <ChatInput input={input} setInput={setInput} files={attachedFiles} setFiles={setAttachedFiles} dragActive={dragActive} setDragActive={setDragActive} dragCounterRef={dragCounter} sending={sending} send={send} onKey={onKey} fileRef={fileRef} multiPiece={multiPiece} setMultiPiece={setMultiPiece} placeholder={`Ej: cambiar material a Granito Negro Brasil...`} />
              <div ref={inlineEndRef} />
              <button onClick={() => setTab("chat")} className="mt-2 bg-transparent border-none text-acc text-xs cursor-pointer font-sans p-0">{`Ver historial completo ${ARROW}`}</button>
            </Section>
          )}
        </div>
      ) : tab === "chat" ? (
        <div
          className="flex-1 flex flex-col min-h-0 relative"
          onDragEnter={wrapperDragEnter}
          onDragLeave={wrapperDragLeave}
          onDragOver={(e) => { if (e.dataTransfer?.types?.includes("Files")) e.preventDefault(); }}
          onDrop={wrapperDrop}
        >
          {dragActive && <DragDropOverlay />}
          {dropError && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 px-4 py-2.5 rounded-lg bg-err/10 border border-err/30 text-[12px] text-err font-sans shadow-lg animate-[fadeUp_0.2s_ease]">
              {WARN} {dropError}
            </div>
          )}
          <div className="flex-1 overflow-y-auto px-4 md:px-7 pt-5 md:pt-7 pb-4 flex flex-col gap-4 md:gap-5">
            {messages.length === 0 && (
              <HomeHero
                onPickFile={() => fileRef.current?.click()}
                onFocusText={() => { const ta = document.querySelector("textarea"); if (ta) (ta as HTMLTextAreaElement).focus(); }}
              />
            )}
            {messages.map((msg, idx) => {
              // Find last REAL assistant message (not dots or empty)
              const isLastReal = (() => {
                for (let i = messages.length - 1; i >= 0; i--) {
                  const m = messages[i];
                  if (m.role === "assistant" && m.content.trim() && m.content.trim() !== "." && m.content.trim() !== "..") {
                    return i === idx;
                  }
                }
                return false;
              })();
              // Show confirm buttons only when Valentina's LAST real message is a confirmation
              // question and there are no other pending questions in the message
              const needsConfirm = isLastReal && msg.role === "assistant" && !msg.isStreaming && !sending && (() => {
                const text = msg.content;
                // Must contain a confirmation question
                const hasConfirmQ = /confirm[aá]s.*\?/i.test(text);
                if (!hasConfirmQ) return false;
                // Count question marks — if more than 1, there are pending questions
                const questionMarks = (text.match(/\?/g) || []).length;
                return questionMarks <= 1;
              })();
              // Short confirmation messages render as compact badges
              const isShortConfirm = msg.role === "user" && /^(confirmo|sí|si|dale|ok|listo)$/i.test(msg.content.trim());
              // Hide DUAL_READ_CONFIRMED raw JSON — show green pill instead
              const isDualConfirm = msg.role === "user" && msg.content.startsWith("[DUAL_READ_CONFIRMED]");
              // Idem CONTEXT_CONFIRMED: pseudo-mensaje que manda la card de
              // contexto al confirmar — muestra pill en vez del JSON crudo.
              const isContextConfirm = msg.role === "user" && msg.content.startsWith("[CONTEXT_CONFIRMED]");
              // SYSTEM_TRIGGER (ej: zone_confirmed) — ocultar entero, no
              // muestra ni pill, es ruido puramente interno.
              const isSystemTriggerMsg = msg.role === "user" && msg.content.startsWith("[SYSTEM_TRIGGER");
              if (isSystemTriggerMsg) return null;

              // Hide ghost messages (dots from sanitization)
              const isDot = msg.content.trim() === "." || msg.content.trim() === "..";
              if (isDot) return null;

              // PR #379 — Filtros defensivos para quotes legacy cuyo historial
              // en DB quedó con placeholders vacíos o texto interno leakeado.
              // En quotes nuevos el backend ya persiste el JSON real de las
              // cards → estos strings no deberían aparecer. Dejamos el filtro
              // defensivo hasta que se corra un PR de rehydrate de quotes
              // viejos aparte.
              const trimmedContent = msg.content.trim();
              if (trimmedContent === "__DUAL_READ_CARD_SHOWN__") return null;
              if (trimmedContent === "__CONTEXT_ANALYSIS_SHOWN__") return null;
              // Fake user turn "(contexto confirmado)" persistido pre-#379
              // cuando el operador confirmaba el contexto. Ahora se usa
              // el [CONTEXT_CONFIRMED]<json> real que el frontend detecta
              // como pill.
              if (msg.role === "user" && trimmedContent === "(contexto confirmado)") return null;
              // Bloques internos del system prompt que pre-#379 se
              // persistían como user turn por un copy.deepcopy del
              // content completo (con el text extraído del PDF y hints
              // inyectados al LLM).
              if (msg.role === "user" && (
                trimmedContent.startsWith("[TEXTO EXTRAÍDO DEL PDF") ||
                trimmedContent.startsWith("[SISTEMA")
              )) return null;

              return (
                <div key={msg.id}>
                  {isDualConfirm ? (
                    <div className="flex justify-end">
                      <span className="px-3 py-1 rounded-full text-[11px] font-medium bg-grn/20 text-grn border border-grn/30">
                        Medidas verificadas {"\u2705"}
                      </span>
                    </div>
                  ) : isContextConfirm ? (
                    <div className="flex justify-end">
                      <span className="px-3 py-1 rounded-full text-[11px] font-medium bg-grn/20 text-grn border border-grn/30">
                        Contexto confirmado {"\u2705"}
                      </span>
                    </div>
                  ) : isShortConfirm ? (
                    <div className="flex justify-end">
                      <span className="px-3 py-1 rounded-full text-[11px] font-medium bg-grn/20 text-grn border border-grn/30">
                        {msg.content.trim()}
                      </span>
                    </div>
                  ) : msg.content.startsWith("__ZONE_SELECTOR__") ? (
                    (() => {
                      try {
                        const selectorData = JSON.parse(msg.content.replace("__ZONE_SELECTOR__", ""));
                        return (
                          <div className="msg-anim flex gap-3 items-start">
                            <div className="max-w-full">
                              <ZoneSelector
                                imageUrl={selectorData.image_url}
                                pageNum={selectorData.page_num}
                                instruction={selectorData.instruction}
                                onConfirm={async (bbox: { x1: number; y1: number; x2: number; y2: number }) => {
                                  try {
                                    await selectZone(quoteId, bbox, selectorData.page_num);
                                    send("[SYSTEM_TRIGGER:zone_confirmed]");
                                  } catch (err) {
                                    console.error("zone-select failed:", err);
                                  }
                                }}
                              />
                            </div>
                          </div>
                        );
                      } catch { return null; }
                    })()
                  ) : msg.content.startsWith("__CONTEXT_ANALYSIS__") ? (
                    (() => {
                      try {
                        const ctxData = JSON.parse(msg.content.replace("__CONTEXT_ANALYSIS__", ""));
                        return (
                          <div className="msg-anim flex gap-3 items-start">
                            <div className="max-w-full">
                              <ContextAnalysis
                                data={ctxData}
                                onConfirm={(payload) => {
                                  send(`[CONTEXT_CONFIRMED]${JSON.stringify(payload)}`);
                                }}
                              />
                            </div>
                          </div>
                        );
                      } catch { return null; }
                    })()
                  ) : msg.content.startsWith("__DUAL_READ__") ? (
                    (() => {
                      try {
                        const DualReadResult = require("@/components/chat/DualReadResult").default;
                        const dualData = JSON.parse(msg.content.replace("__DUAL_READ__", ""));
                        // PR #378 — lock si el quote ya tiene verified_context
                        // (ya se confirmó). Para editar hay que apretar
                        // "Editar despiece" que llama a /reopen-measurements.
                        const isLocked = !!quote?.quote_breakdown?.verified_context;
                        return (
                          <div className="msg-anim flex gap-3 items-start">
                            <div className="max-w-full">
                              <DualReadResult
                                data={dualData}
                                quoteId={quoteId}
                                locked={isLocked}
                                onConfirm={(verified: unknown) => {
                                  send(`[DUAL_READ_CONFIRMED]${JSON.stringify(verified)}`);
                                }}
                                onRetry={(newData: unknown) => {
                                  const updated = `__DUAL_READ__${JSON.stringify(newData)}`;
                                  setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, content: updated } : m));
                                }}
                              />
                            </div>
                          </div>
                        );
                      } catch { return null; }
                    })()
                  ) : (
                    <MessageBubble message={msg} actionText={msg.isStreaming ? actionText : undefined} />
                  )}
                  {needsConfirm && (
                    <>
                      <div className="mt-2 ml-[42px]">
                        <CopyButton
                          text={buildFullSnapshot(quote, messages)}
                          label="📋 Copiar todo"
                          fullWidth
                        />
                      </div>
                      <div className="flex gap-2 mt-2 ml-[42px]">
                        <button
                          onClick={() => send("Confirmo")}
                          className="flex-1 px-4 py-2.5 rounded-lg text-[13px] font-semibold bg-acc text-white border-none cursor-pointer hover:brightness-110 transition"
                        >
                          Confirmar
                        </button>
                        <button
                          onClick={() => { const ta = document.querySelector("textarea"); if (ta) ta.focus(); }}
                          className="px-4 py-2.5 rounded-lg text-[13px] font-medium bg-transparent border border-b2 text-t2 cursor-pointer hover:text-t1 hover:border-b3 transition"
                        >
                          Corregir
                        </button>
                      </div>
                    </>
                  )}
                  {isLastReal && lastFailedMsg && !msg.isStreaming && !sending && msg.content.includes(WARN) && (
                    <div className="flex gap-2 mt-2 ml-[42px]">
                      <button
                        onClick={() => { setLastFailedMsg(null); send(lastFailedMsg); }}
                        className="px-4 py-2 rounded-lg text-[13px] font-medium bg-acc text-white border-none cursor-pointer hover:brightness-110 transition"
                      >
                        Reintentar
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
            <div ref={endRef} />
          </div>
          {quote?.status === "draft" ? (
            <div className="shrink-0 px-4 md:px-7 pt-3 md:pt-3.5 pb-3 md:pb-[18px] border-t border-b1 bg-s1">
              {/* PR #378/#383/#390 — Los botones de reopen son acciones de
                  RECUPERACIÓN, no la acción primaria del turno. La acción
                  primaria es responder a Valentina (el chat input).
                  Historia de iteraciones:
                    #378 → abajo del último turn de Valentina, escondidos
                    #384 → arriba del chat input, en blockes grandes →
                           competían con responder (bug UX del operador)
                    #390 → pequeños, ghost, debajo del input al lado del
                           hint de teclado. Siempre disponibles, nunca
                           gritones. Al click el modal da el warning
                           destructivo completo. */}
              <ChatInput input={input} setInput={setInput} files={attachedFiles} setFiles={setAttachedFiles} multiPiece={multiPiece} setMultiPiece={setMultiPiece} dragActive={dragActive} setDragActive={setDragActive} dragCounterRef={dragCounter} sending={sending} send={send} onKey={onKey} fileRef={fileRef} />
              <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 mt-[7px]">
                <span className="text-[10px] text-t4">{`Enter para enviar ${DOT} Shift+Enter para nueva l${I}nea`}</span>
                {quote?.quote_breakdown?.verified_context && (
                  <button
                    type="button"
                    onClick={() => setReopenModal({ open: true, busy: false })}
                    className="text-[10px] text-t3 hover:text-amb transition underline-offset-2 hover:underline"
                    title="Invalida el cálculo actual y vuelve a edición del despiece"
                  >
                    ↩ Editar despiece
                  </button>
                )}
                {quote?.quote_breakdown?.verified_context_analysis && (
                  <button
                    type="button"
                    onClick={() => setContextModal({ open: true, busy: false })}
                    className="text-[10px] text-t3 hover:text-amb transition underline-offset-2 hover:underline"
                    title="Invalida Paso 2 y medidas; vuelve a edición del contexto"
                  >
                    ↩ Editar contexto
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="shrink-0 px-4 md:px-7 py-3 border-t border-b1 bg-s1 text-center">
              <span className="text-xs text-t3">{`Historial de conversaci${O}n ${DOT} Us${A} Modificaciones en la pesta${N}a Detalle para hacer cambios`}</span>
            </div>
          )}
        </div>
      ) : null}

      {/* PR #381 — Modal "Editar despiece" con el design system de la app.
          Antes usábamos window.confirm() nativo del navegador — rompía la
          estética dark premium del resto de la UI. Este modal sigue el
          mismo patrón que RegenerateButton (otra acción destructiva con
          advertencia). Click afuera cierra (salvo durante `busy`, para
          no cancelar el POST en vuelo). */}
      {reopenModal.open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={() => !reopenModal.busy && setReopenModal({ open: false, busy: false })}
          role="dialog"
          aria-modal="true"
          aria-labelledby="reopen-modal-title"
        >
          <div
            className="w-full max-w-md rounded-2xl border border-b1 bg-s2 p-6 shadow-[0_20px_40px_-20px_rgba(0,0,0,0.5)]"
            onClick={(e) => e.stopPropagation()}
          >
            <h3
              id="reopen-modal-title"
              className="text-[15px] font-semibold text-t1 mb-2"
            >
              Editar despiece
            </h3>
            <p className="text-[13px] text-t2 leading-relaxed mb-4">
              Vas a <strong className="text-t1">invalidar el cálculo actual</strong>{" "}
              y volver a edición del despiece. Vas a tener que reconfirmar
              las medidas para regenerar el presupuesto.
            </p>
            <div className="text-[12px] text-amb bg-amb/[0.08] border border-amb/30 rounded-lg px-3 py-2 mb-5 leading-relaxed">
              Se pierden los totales, MO y material de este Paso 2. El plano
              y el historial se mantienen.
            </div>

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setReopenModal({ open: false, busy: false })}
                disabled={reopenModal.busy}
                className="px-4 py-2 rounded-lg text-[13px] font-medium border border-b2 text-t2 hover:text-t1 hover:border-b3 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancelar
              </button>
              <button
                onClick={async () => {
                  setReopenModal({ open: true, busy: true });
                  try {
                    await reopenMeasurements(quoteId);
                    const fresh = await fetchQuote(quoteId);
                    setQuote(fresh);
                    // PR #383 — el backend ahora corta el historial desde
                    // la card de despiece y regenera con las medidas
                    // editadas. Re-parseamos messages para reflejarlo.
                    setMessages(parseMessages(fresh.messages || []));
                    setReopenModal({ open: false, busy: false });
                    toast(
                      "Despiece reabierto. Editá las medidas y volvé a confirmar.",
                      "success",
                    );
                  } catch (err) {
                    const msg = err instanceof Error ? err.message : "Error al reabrir edición";
                    setReopenModal({ open: false, busy: false });
                    toast(msg, "error");
                  }
                }}
                disabled={reopenModal.busy}
                className="px-4 py-2 rounded-lg text-[13px] font-semibold bg-amb hover:brightness-110 text-acc-ink transition disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {reopenModal.busy ? (
                  <>
                    <span className="inline-block w-3 h-3 border-2 border-acc-ink/40 border-t-acc-ink rounded-full animate-spin" />
                    Reabriendo…
                  </>
                ) : (
                  "↩ Editar despiece"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PR #383 — Modal "Editar contexto". Mismo patrón que el modal
          de despiece, pero el copy aclara que además de Paso 2 se pierden
          también las medidas confirmadas (cambiar contexto puede
          invalidar piezas/tramos del dual_read). */}
      {contextModal.open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={() => !contextModal.busy && setContextModal({ open: false, busy: false })}
          role="dialog"
          aria-modal="true"
          aria-labelledby="context-modal-title"
        >
          <div
            className="w-full max-w-md rounded-2xl border border-b1 bg-s2 p-6 shadow-[0_20px_40px_-20px_rgba(0,0,0,0.5)]"
            onClick={(e) => e.stopPropagation()}
          >
            <h3
              id="context-modal-title"
              className="text-[15px] font-semibold text-t1 mb-2"
            >
              Editar contexto
            </h3>
            <p className="text-[13px] text-t2 leading-relaxed mb-4">
              Vas a <strong className="text-t1">invalidar el Paso 2 y las
              medidas confirmadas</strong> para volver a editar los datos
              comerciales (material, anafes, ubicación, etc.). Después
              tenés que reconfirmar contexto y medidas para regenerar el
              presupuesto.
            </p>
            <div className="text-[12px] text-amb bg-amb/[0.08] border border-amb/30 rounded-lg px-3 py-2 mb-5 leading-relaxed">
              Se pierden totales, MO, material y confirmación de medidas.
              El plano, el brief y el despiece detectado se mantienen.
            </div>

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setContextModal({ open: false, busy: false })}
                disabled={contextModal.busy}
                className="px-4 py-2 rounded-lg text-[13px] font-medium border border-b2 text-t2 hover:text-t1 hover:border-b3 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancelar
              </button>
              <button
                onClick={async () => {
                  setContextModal({ open: true, busy: true });
                  try {
                    await reopenContext(quoteId);
                    const fresh = await fetchQuote(quoteId);
                    setQuote(fresh);
                    // Re-parsear messages: el backend ya cortó el historial
                    // desde la card de contexto y la regeneró. Actualizamos
                    // la vista para reflejarlo sin necesitar un reload.
                    setMessages(parseMessages(fresh.messages || []));
                    setContextModal({ open: false, busy: false });
                    toast(
                      "Contexto reabierto. Editá los datos y volvé a confirmar.",
                      "success",
                    );
                  } catch (err) {
                    const msg = err instanceof Error ? err.message : "Error al reabrir edición";
                    setContextModal({ open: false, busy: false });
                    toast(msg, "error");
                  }
                }}
                disabled={contextModal.busy}
                className="px-4 py-2 rounded-lg text-[13px] font-semibold bg-amb hover:brightness-110 text-acc-ink transition disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {contextModal.busy ? (
                  <>
                    <span className="inline-block w-3 h-3 border-2 border-acc-ink/40 border-t-acc-ink rounded-full animate-spin" />
                    Reabriendo…
                  </>
                ) : (
                  "↩ Editar contexto"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── DETAIL VIEW ─────────────────────────────────────────────────────────────

function DetailView({ quote, breakdown, onSwitchToChat, onGenerate, generating, onFieldUpdate }: { quote: QuoteDetail | null; breakdown: Record<string, any> | null; onSwitchToChat: () => void; onGenerate?: () => void; generating?: boolean; onFieldUpdate?: (patch: QuoteEditablePatch) => Promise<void> }) {
  if (!quote) return null;

  const pieces = breakdown?.sectors?.flatMap((s: any) => s.pieces || []) || [];
  const moItems = (breakdown?.mo_items || []).map((m: any) => ({ ...m, total: m.total ?? (m.quantity ?? 0) * (m.unit_price ?? 0) }));
  const merma = breakdown?.merma;
  const totalM2 = breakdown?.material_m2 || 0;
  const discountPct = breakdown?.discount_pct || 0;
  const totalMO = moItems.reduce((s: number, m: any) => s + (m.total || 0), 0);

  return (
    <div className="flex flex-col gap-5">
      <Section title="Resumen">
        <div className="grid grid-cols-4 gap-4">
          {onFieldUpdate ? (
            <EditableField label="Cliente" type="text" value={quote.client_name} placeholder="Nombre del cliente" onSave={(v) => onFieldUpdate({ client_name: v })} />
          ) : (
            <MetaItem label="Cliente" value={quote.client_name || DASH} />
          )}
          {onFieldUpdate ? (
            <EditableField label="Proyecto" type="text" value={quote.project} placeholder="Nombre del proyecto/obra" onSave={(v) => onFieldUpdate({ project: v })} />
          ) : (
            <MetaItem label="Proyecto" value={quote.project || DASH} />
          )}
          <MetaItem label="Material" value={quote.material || DASH} />
          <MetaItem label="Fecha" value={new Date(quote.created_at).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })} />
          <MetaItem label="Demora" value={breakdown?.delivery_days || DASH} />
          <MetaItem label="Origen" value={quote.source === "web" ? "Web (chatbot)" : "Operador"} />
          <MetaItem label="Total ARS" value={quote.total_ars ? fmtARS(quote.total_ars) : DASH} highlight />
          <MetaItem label="Total USD" value={quote.total_usd ? fmtUSD(quote.total_usd) : DASH} highlight />
          {quote.sink_type && (
            <MetaItem label="Tipo de bacha" value={`${quote.sink_type.basin_count === "doble" ? "Doble" : "Simple"} \u00b7 Pegada de ${quote.sink_type.mount_type}`} />
          )}
        </div>
      </Section>

      {onFieldUpdate ? (
        <Section title="Notas">
          <EditableField
            label="Notas del presupuesto"
            type="textarea"
            value={quote.notes}
            placeholder="Notas internas (aparecen en el PDF al regenerar)"
            onSave={(v) => onFieldUpdate({ notes: v })}
          />
        </Section>
      ) : (
        quote.notes && (
          <Section title="Notas del cliente">
            <p className="text-[13px] text-t2 leading-[1.65] whitespace-pre-wrap">{quote.notes}</p>
          </Section>
        )
      )}

      {/* PR #24 — Condiciones de Contratación: solo edificios. Se genera
          automáticamente al hacer generate_documents si is_building=true. */}
      {quote.is_building && quote.condiciones_pdf && (
        <CondicionesCard record={quote.condiciones_pdf} />
      )}

      {quote.resumen_obra && (
        <ResumenObraCard record={quote.resumen_obra} />
      )}

      {/* Email IA: solo aparece cuando existe un resumen de obra generado.
          El email se arma a partir de ese resumen + las notas del operador,
          así que sin resumen no tiene de dónde nutrirse. */}
      {quote.resumen_obra
        && quote.quote_kind !== "building_parent"
        && quote.id && (
        <EmailDraftCard
          quoteId={quote.id}
          reloadKey={quote.resumen_obra.generated_at}
        />
      )}

      {quote.source_files && quote.source_files.length > 0 && (
        <Section title="Archivos Fuente">
          <div className="flex flex-col gap-2">
            {quote.source_files.map((f: any, i: number) => (
              <div key={i} className={clsx("flex items-center gap-3 px-4 py-3 rounded-lg border border-b1", i % 2 === 0 ? "bg-white/[0.02]" : "bg-transparent")}>
                <span className="text-xl shrink-0">{f.type?.includes("pdf") ? PAGE : f.type?.includes("image") ? PICTURE : CLIP}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-medium text-t1 truncate">{f.filename}</div>
                  <div className="text-[11px] text-t3 mt-0.5">
                    {f.type?.includes("pdf") ? "PDF" : f.type?.includes("jpeg") || f.type?.includes("jpg") ? "JPG" : f.type?.includes("png") ? "PNG" : "Archivo"}
                    {f.size ? ` ${DOT} ${f.size < 1024 ? f.size + " B" : f.size < 1048576 ? (f.size / 1024).toFixed(1) + " KB" : (f.size / 1048576).toFixed(1) + " MB"}` : ""}
                  </div>
                </div>
                <a href={f.url} download className="flex items-center gap-[5px] px-3.5 py-1.5 rounded-md text-[11px] font-medium no-underline border border-acc-hover bg-transparent text-acc cursor-pointer shrink-0 hover:bg-acc/10 transition">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
                  Descargar
                </a>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Building children — for building_parent quotes */}
      {quote.quote_kind === "building_parent" && quote.children && quote.children.length > 0 && (
        <Section title={`Presupuestos por material (${quote.children.length})`}>
          <div className="flex flex-col gap-2">
            {quote.children.map((child: any) => (
              <div key={child.id} className="flex items-center gap-3 px-4 py-3 rounded-lg border border-b1 bg-white/[0.02] hover:bg-white/[0.04] cursor-pointer transition" onClick={() => window.location.href = `/quote/${child.id}`}>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-medium text-t1">{child.material || "\u2014"}</div>
                  <div className="text-[11px] text-t3 mt-0.5">
                    {child.total_usd ? `USD ${child.total_usd.toLocaleString()}` : ""}
                    {child.total_usd && child.total_ars ? " + " : ""}
                    {child.total_ars ? `$${child.total_ars.toLocaleString("es-AR")}` : ""}
                    {!child.total_usd && !child.total_ars ? "\u2014" : ""}
                  </div>
                </div>
                <div className="flex gap-1.5 shrink-0">
                  {(child.drive_pdf_url || child.pdf_url) && <a href={child.drive_pdf_url || child.pdf_url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} className="text-[11px] px-2 py-1 rounded border border-b1 text-t3 hover:text-t1 hover:border-b2 transition no-underline">{"\uD83D\uDCC4"} PDF</a>}
                  {(child.drive_excel_url || child.excel_url) && <a href={child.drive_excel_url || child.excel_url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} className="text-[11px] px-2 py-1 rounded border border-b1 text-t3 hover:text-t1 hover:border-b2 transition no-underline">{"\uD83D\uDCCA"} Excel</a>}
                </div>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-t4 shrink-0"><polyline points="9 18 15 12 9 6"/></svg>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* For building_child_material, show link back to parent */}
      {quote.quote_kind === "building_child_material" && quote.parent_quote_id && (
        <div className="px-1">
          <button onClick={() => window.location.href = `/quote/${quote.parent_quote_id}`} className="text-xs text-acc bg-transparent border-none cursor-pointer font-sans p-0 hover:underline">
            {"\u2190"} Volver al proyecto
          </button>
        </div>
      )}

      {breakdown && (
        <Section title="Solicitud">
          <div className="grid grid-cols-2 gap-3">
            <ReqField label="Material" value={breakdown.material_name || DASH} />
            <ReqField label="Superficie" value={totalM2 ? `${fmtQty(totalM2)} m${SUP2}` : DASH} />
            <ReqField label="Moneda" value={breakdown.material_currency || DASH} />
            <ReqField label={`Precio/m${SUP2}`} value={breakdown.material_price_unit ? (breakdown.material_currency === "USD" ? fmtUSD(breakdown.material_price_unit) : fmtARS(breakdown.material_price_unit)) : DASH} />
            <ReqField label="Plazo" value={breakdown.delivery_days || DASH} />
            <ReqField label="Proyecto" value={breakdown.project || DASH} />
          </div>
        </Section>
      )}

      {breakdown && (pieces.length > 0 || moItems.length > 0) ? (
        <Section title="Desglose del Presupuesto">
          {pieces.length > 0 && (
            <div className="mb-4">
              <div className="text-[13px] font-semibold text-t1 mb-2">{`Material ${DASH} ${fmtQty(totalM2)} m${SUP2}`}</div>
              <table className="w-full border-collapse border border-b1 rounded-lg overflow-hidden">
                <thead><tr className="bg-white/[0.03]">
                  <th className="px-3 py-2 text-[11px] font-semibold text-t3 uppercase tracking-wide text-left border-b border-b1">Pieza</th>
                  <th className="px-3 py-2 text-[11px] font-semibold text-t3 uppercase tracking-wide text-right border-b border-b1">Detalle</th>
                </tr></thead>
                <tbody>{pieces.map((p: string, i: number) => (
                  <tr key={i} className={i % 2 === 1 ? "bg-white/[0.03]" : ""}>
                    <td className="px-3 py-[9px] text-[13px] text-t2 border-b border-white/[0.04]">{p}</td>
                    <td className="px-3 py-[9px] text-[13px] text-t3 text-right border-b border-white/[0.04]"></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}

          {merma && <InfoBar icon={RULER} label="Merma" status={merma.aplica ? "APLICA" : "NO APLICA"} detail={merma.motivo || ""} />}

          {moItems.length > 0 && (
            <div className="my-4">
              <div className="text-[13px] font-semibold text-t1 mb-2">Mano de Obra</div>
              <table className="w-full border-collapse border border-b1 rounded-lg overflow-hidden">
                <thead><tr className="bg-white/[0.03]">
                  <th className="px-3 py-2 text-[11px] font-semibold text-t3 uppercase tracking-wide text-left border-b border-b1">{`${ITEM}tem`}</th>
                  <th className="px-3 py-2 text-[11px] font-semibold text-t3 uppercase tracking-wide text-right border-b border-b1">Cant</th>
                  <th className="px-3 py-2 text-[11px] font-semibold text-t3 uppercase tracking-wide text-right border-b border-b1">Precio</th>
                  <th className="px-3 py-2 text-[11px] font-semibold text-t3 uppercase tracking-wide text-right border-b border-b1">Total</th>
                </tr></thead>
                <tbody>
                  {moItems.map((m: any, i: number) => (
                    <tr key={i} className={i % 2 === 1 ? "bg-white/[0.03]" : ""}>
                      <td className="px-3 py-[9px] text-[13px] text-t2 border-b border-white/[0.04]">{m.description}</td>
                      <td className="px-3 py-[9px] text-[13px] text-t2 text-right border-b border-white/[0.04]">{fmtQty(m.quantity)}</td>
                      <td className="px-3 py-[9px] text-[13px] text-t2 text-right border-b border-white/[0.04]">{fmtARS(m.unit_price)}</td>
                      <td className="px-3 py-[9px] text-[13px] text-t2 text-right border-b border-white/[0.04]">{fmtARS(m.total)}</td>
                    </tr>
                  ))}
                  <tr className="bg-white/[0.05]">
                    <td className="px-3 py-[9px] text-[13px] font-semibold text-t1">TOTAL MO</td>
                    <td></td><td></td>
                    <td className="px-3 py-[9px] text-[13px] font-semibold text-t1 text-right">{fmtARS(totalMO)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          <InfoBar icon={TAG} label="Descuentos" status={discountPct > 0 ? `APLICA ${discountPct}%` : "NO APLICA"} detail={discountPct > 0 ? `${discountPct}% sobre material` : `Particular sin umbral de m${SUP2}`} />

          {(quote.total_ars || quote.total_usd) && (
            <div className="mt-5 px-5 py-4 rounded-[10px] bg-s3 border border-b2 flex justify-between items-center">
              <span className="text-sm font-semibold text-t1">PRESUPUESTO TOTAL</span>
              <div className="text-right">
                {quote.total_ars ? <div className="text-lg font-bold text-t1">{fmtARS(quote.total_ars)} <span className="text-t3 font-normal text-[13px]">mano de obra</span></div> : null}
                {quote.total_usd ? <div className="text-[15px] font-semibold text-acc mt-0.5">+ {fmtUSD(quote.total_usd)} <span className="text-t3 font-normal text-[13px]">material</span></div> : null}
              </div>
            </div>
          )}

          {/* CTA: Generate documents for web quotes without docs */}
          {onGenerate && !quote.pdf_url && (
            <div className="mt-6 p-5 rounded-[10px] text-center border border-dashed border-acc/30" style={{ background: "linear-gradient(135deg, rgba(124,110,240,0.08), rgba(124,110,240,0.03))" }}>
              <div className="text-sm font-semibold text-t1 mb-1.5">{`Presupuesto listo para generar`}</div>
              <div className="text-xs text-t3 mb-4">{`Revis${A} el desglose de arriba. Al confirmar se genera el PDF y se sube a Drive.`}</div>
              <button
                onClick={onGenerate}
                disabled={generating}
                className={clsx(
                  "inline-flex items-center gap-2 px-6 py-2.5 rounded-lg text-[13px] font-semibold text-white border-none cursor-pointer transition-all",
                  generating ? "bg-acc/50 cursor-wait" : "bg-acc hover:brightness-110",
                )}
              >
                {generating ? (
                  <><span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Validando...</>
                ) : (
                  <><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg> Validar presupuesto</>
                )}
              </button>
            </div>
          )}

          {/* Success banner after generation */}
          {onGenerate && quote.pdf_url && (
            <div className="mt-6 px-5 py-3.5 rounded-[10px] bg-grn/10 border border-grn/20 flex items-center gap-3">
              <span className="text-lg">{CIRCLE}</span>
              <span className="text-[13px] font-medium text-grn">Documentos generados y subidos a Drive</span>
            </div>
          )}
        </Section>
      ) : quote.source === "web" && quote.source_files && quote.source_files.length > 0 ? (
        <div className="p-5 rounded-[10px] text-center border border-dashed border-acc/30" style={{ background: "linear-gradient(135deg, rgba(95,125,160,0.08), rgba(95,125,160,0.03))" }}>
          <div className="flex justify-center mb-3">
            <div className="flex gap-1.5">
              <span className="w-2 h-2 rounded-full bg-acc animate-pulse" />
              <span className="w-2 h-2 rounded-full bg-acc animate-pulse [animation-delay:200ms]" />
              <span className="w-2 h-2 rounded-full bg-acc animate-pulse [animation-delay:400ms]" />
            </div>
          </div>
          <div className="text-sm font-semibold text-t1 mb-1.5">{`Analizando plano...`}</div>
          <div className="text-xs text-t3">{`Valentina est${A} extrayendo las piezas y calculando el presupuesto. Se actualiza autom${A}ticamente.`}</div>
        </div>
      ) : quote.source === "web" ? (
        <div className="p-5 rounded-[10px] text-center border border-dashed border-acc/30" style={{ background: "linear-gradient(135deg, rgba(124,110,240,0.08), rgba(124,110,240,0.03))" }}>
          <div className="text-sm font-semibold text-t1 mb-1.5">{quote.notes ? `Presupuesto pendiente de revisi${O}n` : `Presupuesto pendiente de medidas`}</div>
          <div className="text-xs text-t3 mb-4">{quote.notes ? `El cliente envi${O} datos y/o plano. Pas${A} al chat para que Valentina calcule.` : `Pas${A} al chat y dale a Valentina el enunciado o plano. Ella calcula y genera PDF y Drive.`}</div>
          <button
            onClick={onSwitchToChat}
            className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg text-[13px] font-semibold text-white bg-acc border-none cursor-pointer hover:brightness-110 transition-all"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
            Completar con Valentina
          </button>
        </div>
      ) : (
        <Section title="Desglose">
          <div className="text-[13px] text-t3">{`Este presupuesto no tiene datos de desglose estructurados. Consult${A} el historial de chat para ver los detalles.`}</div>
          <button onClick={onSwitchToChat} className="mt-2.5 bg-transparent border-none text-acc text-xs cursor-pointer font-sans p-0">{`Ver chat ${ARROW}`}</button>
        </Section>
      )}
    </div>
  );
}

// ── CHAT INPUT ──────────────────────────────────────────────────────────────

import { VALID_FILE_TYPES as VALID_TYPES, MAX_FILE_SIZE, MAX_FILES } from "@/lib/constants";

function ChatInput({ input, setInput, files, setFiles, multiPiece, setMultiPiece, dragActive, setDragActive, dragCounterRef, sending, send, onKey, fileRef, placeholder: customPlaceholder }: {
  input: string; setInput: (v: string) => void;
  files: File[]; setFiles: (f: File[]) => void;
  multiPiece: boolean; setMultiPiece: (v: boolean) => void;
  dragActive: boolean; setDragActive: (v: boolean) => void;
  dragCounterRef: React.MutableRefObject<number>;
  sending: boolean; send: () => void; onKey: (e: React.KeyboardEvent) => void;
  fileRef: React.RefObject<HTMLInputElement>;
  placeholder?: string;
}) {
  const [fileError, setFileError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea smoothly — reset to auto then measure scrollHeight
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    const next = Math.min(ta.scrollHeight, 110);
    ta.style.height = `${next}px`;
    ta.style.overflowY = ta.scrollHeight > 110 ? "auto" : "hidden";
  }, [input]);

  const addFiles = (newFiles: FileList | File[]) => {
    if (sending) return;
    const arr = Array.from(newFiles);
    const valid: File[] = [];
    for (const f of arr) {
      if (!VALID_TYPES.some(t => f.type.includes(t.split("/")[1]))) { setFileError(`"${f.name}" ${DASH} tipo no soportado`); setTimeout(() => setFileError(null), 3000); continue; }
      if (f.size > MAX_FILE_SIZE) { setFileError(`"${f.name}" ${DASH} m${A}ximo 10MB`); setTimeout(() => setFileError(null), 3000); continue; }
      if (files.length + valid.length >= MAX_FILES) { setFileError(`M${A}ximo 5 archivos`); setTimeout(() => setFileError(null), 3000); break; }
      if (files.some(ef => ef.name === f.name && ef.size === f.size)) continue;
      if (valid.some(ef => ef.name === f.name && ef.size === f.size)) continue;
      valid.push(f);
    }
    if (valid.length > 0) setFiles([...files, ...valid]);
  };

  const removeFile = (idx: number) => setFiles(files.filter((_, i) => i !== idx));
  const handleDragEnter = (e: React.DragEvent) => { e.preventDefault(); dragCounterRef.current++; setDragActive(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); dragCounterRef.current--; if (dragCounterRef.current <= 0) { dragCounterRef.current = 0; setDragActive(false); } };
  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); dragCounterRef.current = 0; setDragActive(false); if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files); };

  const fmtSize = (b: number) => b < 1024 ? `${b} B` : b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(1)} MB`;
  const fmtType = (t: string) => t.includes("pdf") ? "PDF" : t.includes("jpeg") || t.includes("jpg") ? "JPG" : t.includes("png") ? "PNG" : "WEBP";
  const fileIcon = (t: string) => t.includes("pdf") ? PAGE : PICTURE;

  return (
    // El drag overlay full-chat vive en el wrapper del chat tab (ver
    // DragDropOverlay). Acá sólo exponemos los handlers — el wrapper
    // parent ya intercepta por burbujeo, pero mantenerlos preserva el
    // dragCounter compartido y sirve de fallback si el ChatInput se
    // reutiliza fuera del chat (ej: modificaciones en detalle).
    <div onDragEnter={handleDragEnter} onDragLeave={handleDragLeave} onDragOver={e => e.preventDefault()} onDrop={handleDrop} className="relative">
      {(files.length > 0 || fileError) && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {files.map((f, i) => (
            <div key={`${f.name}-${i}`} className="flex items-center gap-1.5 px-2.5 py-[5px] rounded-md bg-s3 border border-b1 text-[11px] text-t2 max-w-[280px]">
              <span className="text-sm">{fileIcon(f.type)}</span>
              <span className="truncate flex-1">{f.name}</span>
              <span className="text-t3 shrink-0">{fmtType(f.type)} {DOT} {fmtSize(f.size)}</span>
              <button onClick={() => removeFile(i)} className="bg-transparent border-none text-t3 cursor-pointer text-[13px] px-[2px] hover:text-t1">{XMARK}</button>
            </div>
          ))}
          {fileError && (
            <div className="flex items-center gap-1.5 px-2.5 py-[5px] rounded-md bg-err/[0.08] border border-err/30 text-[11px] text-err">
              {WARN} {fileError}
            </div>
          )}
        </div>
      )}

      {files.length > 0 && (
        <label className={clsx("flex items-center gap-1.5 mb-2 cursor-pointer text-[11px]", multiPiece ? "text-acc" : "text-t3")}>
          <input type="checkbox" checked={multiPiece} onChange={e => setMultiPiece(e.target.checked)} className="accent-acc cursor-pointer" />
          {`Plano con m${A}s de 3 piezas (pedir capturas individuales)`}
        </label>
      )}

      <div className={clsx(
        "flex items-end gap-2 bg-s3 rounded-xl px-4 py-2.5 transition-[border-color,box-shadow] duration-150",
        dragActive ? "border border-acc shadow-[0_0_20px_rgba(95,125,160,0.15)]" : "border border-b2",
      )}>
        <textarea ref={textareaRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKey} rows={1} disabled={sending} autoFocus
          placeholder={customPlaceholder || `Escrib${I} el enunciado o arrastr${A} el plano ac${A}...`}
          className="flex-1 bg-transparent border-none outline-none font-sans text-[13px] text-t1 resize-none leading-[1.5] max-h-[110px] overflow-hidden placeholder:text-t4"
        />
        <div className="flex items-center gap-[5px] shrink-0">
          <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" multiple className="hidden" onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
          <IconBtn onClick={() => fileRef.current?.click()} title="Adjuntar plano" disabled={sending}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" /></svg>
          </IconBtn>
          <IconBtn onClick={send} primary disabled={sending || (!input.trim() && files.length === 0)}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
          </IconBtn>
        </div>
      </div>
    </div>
  );
}

// ── SUB-COMPONENTS ──────────────────────────────────────────────────────────

function Section({ title, children, className: extra }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx("bg-s1 border border-b1 rounded-xl px-[22px] py-[18px]", extra)}>
      <div className="text-[13px] font-semibold text-t1 uppercase tracking-[0.06em] mb-3.5 pb-2 border-b border-b1">{title}</div>
      {children}
    </div>
  );
}

function MetaItem({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div className="text-[10px] text-t3 uppercase tracking-[0.08em] mb-[3px]">{label}</div>
      <div className={clsx("text-sm", highlight ? "font-semibold text-t1" : "font-normal text-t2")}>{value}</div>
    </div>
  );
}

function ReqField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 text-[13px]">
      <span className="text-t3 min-w-[110px] shrink-0">{label}</span>
      <span className="text-t1">{value}</span>
    </div>
  );
}

function InfoBar({ icon, label, status, detail }: { icon: string; label: string; status: string; detail: string }) {
  const isNo = status.includes("NO");
  return (
    <div className={clsx(
      "flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg text-xs",
      isNo ? "bg-white/[0.02] border border-b1" : "bg-amb/[0.06] border border-amb/[0.16]",
    )}>
      <span>{icon}</span>
      <span className="font-semibold text-t1">{label} {DASH} {status}</span>
      <span className="text-t3">{detail}</span>
    </div>
  );
}

function TabBtn({ active, children, onClick, disabled }: { active: boolean; children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={disabled ? undefined : onClick}
      className={clsx(
        "px-5 py-2.5 text-[13px] font-medium border-none bg-transparent font-sans",
        active ? "border-b-2 border-b-acc text-acc" : "border-b-2 border-b-transparent text-t3",
        disabled ? "opacity-50 cursor-default text-t4" : "cursor-pointer",
      )}
    >
      {children}
    </button>
  );
}

function FileLink({ href, label, cls }: { href: string; label: string; cls: string }) {
  const emoji = label === "PDF" ? PAGE : label === "Excel" ? CHART : CLOUD;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={clsx("flex items-center gap-[5px] px-3 py-1.5 rounded-md text-[11px] font-medium no-underline border bg-transparent hover:bg-white/[0.04] transition", cls)}>
      {emoji} {label}
    </a>
  );
}

function IconBtn({ onClick, children, primary, disabled, title }: { onClick: () => void; children: React.ReactNode; primary?: boolean; disabled?: boolean; title?: string }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title} className={clsx(
      "w-8 h-8 rounded-full flex items-center justify-center transition-all duration-100",
      primary && !disabled ? "border-none bg-acc text-white" : primary && disabled ? "border-none bg-white/[0.06] text-t4" : "border border-b1 bg-transparent text-t2",
      disabled ? "cursor-not-allowed" : "cursor-pointer",
    )}>
      {children}
    </button>
  );
}

// ── DRAG & DROP OVERLAY ──────────────────────────────────────────────────────
// Full-chat overlay al arrastrar un archivo sobre el área del chat. Cubre
// toda la superficie (scroll + composer) con un borde dashed y una card
// centrada en Fraunces italic. Matches el mockup "Drag & drop del plano"
// del handoff v2.
function DragDropOverlay() {
  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none"
      style={{ backdropFilter: "blur(2px)", WebkitBackdropFilter: "blur(2px)" }}
    >
      {/* dashed border wrapper */}
      <div className="absolute inset-4 md:inset-6 border-2 border-dashed border-acc/70 rounded-xl bg-acc/[0.04]" />
      {/* card centrada */}
      <div className="relative z-10 px-8 py-7 rounded-2xl bg-s1 border border-b2 shadow-[0_20px_60px_rgba(0,0,0,.45)] flex flex-col items-center gap-2 max-w-[420px] text-center">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="text-acc mb-1">
          <path d="M12 16V4m0 0l-5 5m5-5l5 5" />
          <path d="M4 20h16" />
        </svg>
        <h3 className="font-serif italic text-[22px] md:text-[24px] font-medium text-t1 -tracking-[0.01em] leading-tight">
          Soltá el plano acá
        </h3>
        <p className="text-[12px] md:text-[13px] text-t3 font-sans">
          Acepto PDF, JPG, PNG o WEBP · hasta 10 MB
        </p>
      </div>
    </div>
  );
}
