"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { fetchQuote, streamChat, markQuoteAsRead, fetchQuoteComparison, validateQuote, type QuoteDetail, type QuoteCompareResponse } from "@/lib/api";
import { useQuotes } from "@/lib/quotes-context";
import MessageBubble from "@/components/chat/MessageBubble";
import CompareView from "@/components/quote/CompareView";
import clsx from "clsx";
import { A, I, O, DOT, SUP2, DASH, ITEM, WARN, CIRCLE, ARROW, XMARK, CLOUD, WAVE, PAGE, PICTURE, CLIP, RULER, TAG, FOLDER, CHART } from "@/lib/chars";

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

const STATUS_CLASS: Record<string, { label: string; cls: string }> = {
  draft:     { label: "Borrador",  cls: "bg-amb-bg text-amb" },
  pending:   { label: "Pendiente", cls: "bg-acc-bg text-acc" },
  validated: { label: "Validado",  cls: "bg-grn-bg text-grn" },
  sent:      { label: "Enviado",   cls: "bg-acc-bg text-acc" },
};

// ── MAIN ─────────────────────────────────────────────────────────────────────

export default function QuotePage() {
  const router = useRouter();
  const params = useParams();
  const quoteId = params.id as string;

  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [comparison, setComparison] = useState<QuoteCompareResponse | null>(null);
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [tab, setTab] = useState<"detail" | "chat" | "compare">("chat");
  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const dragCounter = useRef(0);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionText, setActionText] = useState("");
  const [generating, setGenerating] = useState(false);
  const { refresh: refreshQuotes, markRead } = useQuotes();

  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const userInteracted = useRef(false);

  useEffect(() => {
    fetchQuote(quoteId).then(q => {
      setQuote(q);
      if (!q.is_read) { markQuoteAsRead(quoteId).catch(() => {}); markRead(quoteId); }
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
      if (q.status === "validated" || q.status === "sent" || q.status === "pending" || q.source === "web") setTab("detail");
    }).catch((err: any) => {
      setLoadError(err.message || "Error al cargar presupuesto");
    }).finally(() => setLoading(false));

    fetchQuoteComparison(quoteId).then(c => setComparison(c)).catch(() => {});
  }, [quoteId]);

  // Abort SSE stream on unmount or quoteId change
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, [quoteId]);

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

  const send = useCallback(async () => {
    if ((!input.trim() && attachedFiles.length === 0) || sending) return;
    userInteracted.current = true;
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
    if (tab !== "chat") setTab("chat");

    try {
      // Abort previous stream if any
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      let acc = "";
      let gotDone = false;
      let rafPending = false;
      const flushAcc = () => {
        rafPending = false;
        setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc } : m));
      };
      for await (const chunk of streamChat(quoteId, text, filesToSend.length > 0 ? filesToSend : undefined, controller.signal)) {
        if (chunk.type === "text") {
          acc += chunk.content;
          setActionText("");
          // Throttle state updates to 1 per animation frame
          if (!rafPending) { rafPending = true; requestAnimationFrame(flushAcc); }
        } else if (chunk.type === "action") {
          setActionText(chunk.content);
        } else if (chunk.type === "done") {
          gotDone = true;
          setActionText("");
          // Final flush with complete content + streaming=false
          setMessages(p => p.map(m => m.id === aid ? { ...m, content: acc, isStreaming: false } : m));
          const [updated] = await Promise.all([
            fetchQuote(quoteId),
            refreshQuotes(),
            fetchQuoteComparison(quoteId).then(c => setComparison(c)).catch(() => {}),
          ]);
          setQuote(updated);
        }
      }
      if (!gotDone) {
        setActionText("");
        const errorMsg = acc ? acc + `\n\n${WARN} _La conexi${O}n se interrumpi${O}._` : `${WARN} La conexi${O}n se interrumpi${O}. Intent${A} de nuevo.`;
        setMessages(p => p.map(m => m.id === aid ? { ...m, content: errorMsg, isStreaming: false } : m));
      }
    } catch {
      setActionText("");
      setMessages(p => p.map(m => m.id === aid ? { ...m, content: `${WARN} Error de conexi${O}n. Intent${A} de nuevo.`, isStreaming: false } : m));
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
      {/* Header */}
      <div className="flex items-center justify-between px-7 py-3.5 border-b border-b1 shrink-0 bg-s1">
        <div className="flex items-center gap-3.5">
          <button onClick={() => router.push("/")} className="w-[30px] h-[30px] rounded-md border border-b1 bg-transparent text-t2 cursor-pointer flex items-center justify-center hover:border-b2 hover:text-t1 transition">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold text-t1 truncate max-w-[500px]">{quote?.client_name || "Nuevo presupuesto"}</span>
              <span className={clsx("inline-flex items-center gap-1 px-2 py-[2px] rounded-full text-[10px] font-semibold shrink-0", st.cls)}>{CIRCLE} {st.label}</span>
              {quote?.source === "web" && <span className="inline-flex items-center gap-1 px-2 py-[2px] rounded-full text-[10px] font-semibold bg-purple-500/15 text-purple-400 shrink-0">WEB</span>}
            </div>
            <div className="text-xs text-t3 mt-0.5 truncate max-w-[600px]">
              {quote?.project}{quote?.material ? ` ${DOT} ${quote.material}` : ""}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          {quote?.pdf_url && <FileLink href={quote.pdf_url} label="PDF" cls="border-red-400/20 text-red-400" />}
          {quote?.excel_url && <FileLink href={quote.excel_url} label="Excel" cls="border-grn/20 text-grn" />}
          {quote?.drive_url && <FileLink href={quote.drive_url} label="Drive" cls="border-acc/20 text-acc" />}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-b1 bg-s1 pl-7">
        <TabBtn active={tab === "detail"} onClick={() => setTab("detail")} disabled={!quote || (quote.status === "draft" && quote.source !== "web")}>Detalle</TabBtn>
        <TabBtn active={tab === "chat"} onClick={() => setTab("chat")}>Chat</TabBtn>
        {comparison && <TabBtn active={tab === "compare"} onClick={() => setTab("compare")}>Comparar</TabBtn>}
      </div>

      {/* Content */}
      {tab === "compare" && comparison ? (
        <div className="flex-1 overflow-y-auto px-7 py-6">
          <CompareView data={comparison} />
        </div>
      ) : tab === "detail" ? (
        <div className="flex-1 overflow-y-auto px-7 py-6">
          <DetailView quote={quote} breakdown={bd} onSwitchToChat={() => setTab("chat")} onGenerate={quote?.status === "pending" || quote?.status === "draft" ? handleGenerate : undefined} generating={generating} />
          {/* Show modifications section only when quote has breakdown (already calculated) */}
          {bd && (
            <Section title="Modificaciones" className="mt-5">
              <div className="text-xs text-t3 mb-2.5">{quote?.pdf_url ? `Escrib${I} un cambio y Valentina regenera los documentos autom${A}ticamente.` : `Escrib${I} un cambio y Valentina ajusta el presupuesto.`}</div>
              <ChatInput input={input} setInput={setInput} files={attachedFiles} setFiles={setAttachedFiles} dragActive={dragActive} setDragActive={setDragActive} dragCounterRef={dragCounter} sending={sending} send={send} onKey={onKey} fileRef={fileRef} />
              <button onClick={() => setTab("chat")} className="mt-2 bg-transparent border-none text-acc text-xs cursor-pointer font-sans p-0">{`Ver historial completo ${ARROW}`}</button>
            </Section>
          )}
        </div>
      ) : tab === "chat" ? (
        <>
          <div className="flex-1 overflow-y-auto px-7 pt-7 pb-4 flex flex-col gap-5">
            {messages.length === 0 && (
              <div className="px-[18px] py-3.5 bg-s2 rounded-xl text-[13px] text-t2">
                {`Hola ${WAVE} Soy Valentina. Pasame el enunciado del trabajo y/o el plano.`}
              </div>
            )}
            {messages.map(msg => <MessageBubble key={msg.id} message={msg} actionText={msg.isStreaming ? actionText : undefined} />)}
            <div ref={endRef} />
          </div>
          <div className="shrink-0 px-7 pt-3.5 pb-[18px] border-t border-b1 bg-s1">
            <ChatInput input={input} setInput={setInput} files={attachedFiles} setFiles={setAttachedFiles} dragActive={dragActive} setDragActive={setDragActive} dragCounterRef={dragCounter} sending={sending} send={send} onKey={onKey} fileRef={fileRef} />
            <div className="text-[10px] text-t4 text-center mt-[7px]">{`Enter para enviar ${DOT} Shift+Enter para nueva l${I}nea`}</div>
          </div>
        </>
      ) : null}
    </div>
  );
}

// ── DETAIL VIEW ─────────────────────────────────────────────────────────────

function DetailView({ quote, breakdown, onSwitchToChat, onGenerate, generating }: { quote: QuoteDetail | null; breakdown: Record<string, any> | null; onSwitchToChat: () => void; onGenerate?: () => void; generating?: boolean }) {
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
          <MetaItem label="Cliente" value={quote.client_name || DASH} />
          <MetaItem label="Proyecto" value={quote.project || DASH} />
          <MetaItem label="Material" value={quote.material || DASH} />
          <MetaItem label="Fecha" value={new Date(quote.created_at).toLocaleDateString("es-AR")} />
          <MetaItem label="Demora" value={breakdown?.delivery_days || DASH} />
          <MetaItem label="Origen" value={quote.source === "web" ? "Web (chatbot)" : "Operador"} />
          <MetaItem label="Total ARS" value={quote.total_ars ? fmtARS(quote.total_ars) : DASH} highlight />
          <MetaItem label="Total USD" value={quote.total_usd ? fmtUSD(quote.total_usd) : DASH} highlight />
        </div>
      </Section>

      {quote.notes && (
        <Section title="Notas del cliente">
          <p className="text-[13px] text-t2 leading-[1.65] whitespace-pre-wrap">{quote.notes}</p>
        </Section>
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
              <div className="text-xs text-t3 mb-4">{`Revis${A} el desglose de arriba. Al confirmar se genera el PDF, Excel y se sube a Drive.`}</div>
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
      ) : quote.source === "web" ? (
        <div className="p-5 rounded-[10px] text-center border border-dashed border-acc/30" style={{ background: "linear-gradient(135deg, rgba(124,110,240,0.08), rgba(124,110,240,0.03))" }}>
          <div className="text-sm font-semibold text-t1 mb-1.5">{`Presupuesto pendiente de medidas`}</div>
          <div className="text-xs text-t3 mb-4">{`Pas${A} al chat y dale a Valentina el enunciado o plano. Ella calcula y genera PDF, Excel y Drive.`}</div>
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

const VALID_TYPES = ["application/pdf", "image/jpeg", "image/jpg", "image/png", "image/webp"];
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const MAX_FILES = 5;

function ChatInput({ input, setInput, files, setFiles, dragActive, setDragActive, dragCounterRef, sending, send, onKey, fileRef }: {
  input: string; setInput: (v: string) => void;
  files: File[]; setFiles: (f: File[]) => void;
  dragActive: boolean; setDragActive: (v: boolean) => void;
  dragCounterRef: React.MutableRefObject<number>;
  sending: boolean; send: () => void; onKey: (e: React.KeyboardEvent) => void;
  fileRef: React.RefObject<HTMLInputElement>;
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
    for (const f of arr) {
      if (!VALID_TYPES.some(t => f.type.includes(t.split("/")[1]))) { setFileError(`"${f.name}" ${DASH} tipo no soportado`); setTimeout(() => setFileError(null), 3000); continue; }
      if (f.size > MAX_FILE_SIZE) { setFileError(`"${f.name}" ${DASH} m${A}ximo 10MB`); setTimeout(() => setFileError(null), 3000); continue; }
      if (files.length >= MAX_FILES) { setFileError(`M${A}ximo 5 archivos`); setTimeout(() => setFileError(null), 3000); break; }
      if (files.some(ef => ef.name === f.name && ef.size === f.size)) continue;
      setFiles([...files, f]);
    }
  };

  const removeFile = (idx: number) => setFiles(files.filter((_, i) => i !== idx));
  const handleDragEnter = (e: React.DragEvent) => { e.preventDefault(); dragCounterRef.current++; setDragActive(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); dragCounterRef.current--; if (dragCounterRef.current <= 0) { dragCounterRef.current = 0; setDragActive(false); } };
  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); dragCounterRef.current = 0; setDragActive(false); if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files); };

  const fmtSize = (b: number) => b < 1024 ? `${b} B` : b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(1)} MB`;
  const fmtType = (t: string) => t.includes("pdf") ? "PDF" : t.includes("jpeg") || t.includes("jpg") ? "JPG" : t.includes("png") ? "PNG" : "WEBP";
  const fileIcon = (t: string) => t.includes("pdf") ? PAGE : PICTURE;

  return (
    <div onDragEnter={handleDragEnter} onDragLeave={handleDragLeave} onDragOver={e => e.preventDefault()} onDrop={handleDrop} className="relative">
      {dragActive && (
        <div className="absolute inset-0 z-10 bg-acc/[0.08] border-2 border-dashed border-acc rounded-xl flex flex-col items-center justify-center gap-1.5 pointer-events-none">
          <span className="text-[28px]">{FOLDER}</span>
          <span className="text-sm font-medium text-acc">{`Solt${A} tu plano PDF o imagen ac${A}`}</span>
          <span className="text-[11px] text-t3">{`PDF, JPG, PNG ${DOT} M${A}ximo 10MB`}</span>
        </div>
      )}

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

      <div className={clsx(
        "flex items-end gap-2 bg-s3 rounded-xl px-4 py-2.5 transition-[border-color,box-shadow] duration-150",
        dragActive ? "border border-acc shadow-[0_0_20px_rgba(79,143,255,0.15)]" : "border border-b2",
      )}>
        <textarea ref={textareaRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKey} rows={1} disabled={sending} autoFocus
          placeholder={`Escrib${I} el enunciado o arrastr${A} el plano ac${A}...`}
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
