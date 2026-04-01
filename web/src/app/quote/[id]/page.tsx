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

// ── HELPERS ──────────────────────────────────────────────────────────────────

const fmtARS = (n: number) => `$${Math.round(n).toLocaleString("es-AR")}`;
const fmtUSD = (n: number) => `USD ${Math.round(n).toLocaleString("es-AR")}`;
const fmtQty = (n: number) => {
  if (Math.abs(n - Math.round(n)) < 0.05) return String(Math.round(n));
  return n.toFixed(2).replace(".", ",");
};

const STATUS: Record<string, { label: string; bg: string; color: string }> = {
  draft: { label: "Borrador", bg: "var(--amb2)", color: "var(--amb)" },
  validated: { label: "Validado", bg: "var(--grn2)", color: "var(--grn)" },
  sent: { label: "Enviado", bg: "var(--acc2)", color: "var(--acc)" },
};

// ── MAIN ─────────────────────────────────────────────────────────────────────

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
      // Show detail tab only for validated/sent quotes
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

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--t3)", fontSize: 13 }}>
      Cargando...
    </div>
  );

  const st = STATUS[quote?.status || "draft"];
  const bd = quote?.quote_breakdown || null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* ── HEADER ──────────────────────────────────────────── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 28px", borderBottom: "1px solid var(--b1)",
        flexShrink: 0, background: "var(--s1)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <button onClick={() => router.push("/")} style={backBtnStyle}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>
          </button>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 16, fontWeight: 600, color: "var(--t1)" }}>{quote?.client_name || "Nuevo presupuesto"}</span>
              <span style={{ ...badgeStyle, background: st.bg, color: st.color }}>● {st.label}</span>
              {quote?.source === "web" && <span style={{ ...badgeStyle, background: "rgba(138,43,226,.15)", color: "#a855f7" }}>WEB</span>}
            </div>
            <div style={{ fontSize: 12, color: "var(--t3)", marginTop: 2 }}>
              {quote?.project}{quote?.material ? ` · ${quote.material}` : ""}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {quote?.pdf_url && <FileLink href={quote.pdf_url} label="PDF" color="#ff6b63" />}
          {quote?.excel_url && <FileLink href={quote.excel_url} label="Excel" color="var(--grn)" />}
          {quote?.drive_url && <FileLink href={quote.drive_url} label="Drive" color="var(--acc)" />}
        </div>
      </div>

      {/* ── TABS ────────────────────────────────────────────── */}
      <div style={{
        display: "flex", gap: 0, borderBottom: "1px solid var(--b1)",
        background: "var(--s1)", paddingLeft: 28,
      }}>
        <TabBtn active={tab === "detail"} onClick={() => setTab("detail")} disabled={!quote || quote.status === "draft"}>Detalle</TabBtn>
        <TabBtn active={tab === "chat"} onClick={() => setTab("chat")}>Chat</TabBtn>
      </div>

      {/* ── CONTENT ─────────────────────────────────────────── */}
      {tab === "detail" ? (
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>
          <DetailView quote={quote} breakdown={bd} onSwitchToChat={() => setTab("chat")} />

          {/* Quick chat at bottom */}
          <Section title="Modificaciones" style={{ marginTop: 20 }}>
            <div style={{ fontSize: 12, color: "var(--t3)", marginBottom: 10 }}>
              Escribí un cambio y Valentina regenera los documentos automáticamente.
            </div>
            <ChatInput
              input={input} setInput={setInput}
              files={attachedFiles} setFiles={setAttachedFiles}
              dragActive={dragActive} setDragActive={setDragActive}
              dragCounterRef={dragCounter}
              sending={sending} send={send} onKey={onKey}
              fileRef={fileRef}
            />
            <button onClick={() => setTab("chat")} style={{
              marginTop: 8, background: "none", border: "none", color: "var(--acc)",
              fontSize: 12, cursor: "pointer", fontFamily: "inherit", padding: 0,
            }}>
              Ver historial completo →
            </button>
          </Section>
        </div>
      ) : (
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
            <ChatInput
              input={input} setInput={setInput}
              files={attachedFiles} setFiles={setAttachedFiles}
              dragActive={dragActive} setDragActive={setDragActive}
              dragCounterRef={dragCounter}
              sending={sending} send={send} onKey={onKey}
              fileRef={fileRef}
            />
            <div style={{ fontSize: 10, color: "var(--t4)", textAlign: "center", marginTop: 7 }}>
              Enter para enviar · Shift+Enter para nueva línea
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── DETAIL VIEW ─────────────────────────────────────────────────────────────

function DetailView({ quote, breakdown, onSwitchToChat }: {
  quote: QuoteDetail | null;
  breakdown: Record<string, any> | null;
  onSwitchToChat: () => void;
}) {
  if (!quote) return null;

  const pieces = breakdown?.sectors?.flatMap((s: any) => s.pieces || []) || [];
  const moItems = breakdown?.mo_items || [];
  const merma = breakdown?.merma;
  const totalM2 = breakdown?.material_m2 || 0;
  const discountPct = breakdown?.discount_pct || 0;
  const totalMO = moItems.reduce((s: number, m: any) => s + (m.total || 0), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* A. RESUMEN */}
      <Section title="Resumen">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 16 }}>
          <MetaItem label="Cliente" value={quote.client_name || "—"} />
          <MetaItem label="Proyecto" value={quote.project || "—"} />
          <MetaItem label="Material" value={quote.material || "—"} />
          <MetaItem label="Fecha" value={new Date(quote.created_at).toLocaleDateString("es-AR")} />
          <MetaItem label="Demora" value={breakdown?.delivery_days || "—"} />
          <MetaItem label="Origen" value={quote.source === "web" ? "Web (chatbot)" : "Operador"} />
          <MetaItem label="Total ARS" value={quote.total_ars ? fmtARS(quote.total_ars) : "—"} highlight />
          <MetaItem label="Total USD" value={quote.total_usd ? fmtUSD(quote.total_usd) : "—"} highlight />
        </div>
      </Section>

      {/* A2. SOURCE FILES */}
      {quote.source_files && quote.source_files.length > 0 && (
        <Section title="Archivos Fuente">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {quote.source_files.map((f: any, i: number) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "12px 16px", borderRadius: 8,
                background: i % 2 === 0 ? "rgba(255,255,255,.02)" : "transparent",
                border: "1px solid var(--b1)",
              }}>
                <span style={{ fontSize: 20, flexShrink: 0 }}>
                  {f.type?.includes("pdf") ? "📄" : f.type?.includes("image") ? "🖼️" : "📎"}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "var(--t1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {f.filename}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 2 }}>
                    {f.type?.includes("pdf") ? "PDF" : f.type?.includes("jpeg") || f.type?.includes("jpg") ? "JPG" : f.type?.includes("png") ? "PNG" : "Archivo"}
                    {f.size ? ` · ${f.size < 1024 ? f.size + " B" : f.size < 1048576 ? (f.size / 1024).toFixed(1) + " KB" : (f.size / 1048576).toFixed(1) + " MB"}` : ""}
                  </div>
                </div>
                <a href={f.url} download style={{
                  display: "flex", alignItems: "center", gap: 5,
                  padding: "6px 14px", borderRadius: 6,
                  fontSize: 11, fontWeight: 500, textDecoration: "none",
                  border: "1px solid var(--acc3)", background: "transparent",
                  color: "var(--acc)", cursor: "pointer", flexShrink: 0,
                }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                  Descargar
                </a>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* B. SOLICITUD (only if breakdown available) */}
      {breakdown && (
        <Section title="Solicitud">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <ReqField label="Material" value={breakdown.material_name || "—"} />
            <ReqField label="Superficie" value={totalM2 ? `${fmtQty(totalM2)} m²` : "—"} />
            <ReqField label="Moneda" value={breakdown.material_currency || "—"} />
            <ReqField label="Precio/m²" value={breakdown.material_price_unit ? (breakdown.material_currency === "USD" ? fmtUSD(breakdown.material_price_unit) : fmtARS(breakdown.material_price_unit)) : "—"} />
            <ReqField label="Plazo" value={breakdown.delivery_days || "—"} />
            <ReqField label="Proyecto" value={breakdown.project || "—"} />
          </div>
        </Section>
      )}

      {/* C. DESGLOSE */}
      {breakdown && (pieces.length > 0 || moItems.length > 0) ? (
        <Section title="Desglose del Presupuesto">
          {/* Pieces */}
          {pieces.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--t1)", marginBottom: 8 }}>
                Material — {fmtQty(totalM2)} m²
              </div>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Pieza</th>
                    <th style={{ ...thStyle, textAlign: "right" }}>Detalle</th>
                  </tr>
                </thead>
                <tbody>
                  {pieces.map((p: string, i: number) => (
                    <tr key={i} style={{ background: i % 2 === 1 ? "rgba(255,255,255,.03)" : "transparent" }}>
                      <td style={tdStyle}>{p}</td>
                      <td style={{ ...tdStyle, textAlign: "right", color: "var(--t3)" }}></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Merma */}
          {merma && (
            <InfoBar
              icon="📐"
              label="Merma"
              status={merma.aplica ? "APLICA" : "NO APLICA"}
              detail={merma.motivo || ""}
            />
          )}

          {/* MO */}
          {moItems.length > 0 && (
            <div style={{ marginTop: 16, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--t1)", marginBottom: 8 }}>Mano de Obra</div>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Ítem</th>
                    <th style={{ ...thStyle, textAlign: "right" }}>Cant</th>
                    <th style={{ ...thStyle, textAlign: "right" }}>Precio</th>
                    <th style={{ ...thStyle, textAlign: "right" }}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {moItems.map((m: any, i: number) => (
                    <tr key={i} style={{ background: i % 2 === 1 ? "rgba(255,255,255,.03)" : "transparent" }}>
                      <td style={tdStyle}>{m.description}</td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>{fmtQty(m.quantity)}</td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>{fmtARS(m.unit_price)}</td>
                      <td style={{ ...tdStyle, textAlign: "right" }}>{fmtARS(m.total)}</td>
                    </tr>
                  ))}
                  <tr style={{ background: "rgba(255,255,255,.05)" }}>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>TOTAL MO</td>
                    <td style={tdStyle}></td>
                    <td style={tdStyle}></td>
                    <td style={{ ...tdStyle, textAlign: "right", fontWeight: 600 }}>{fmtARS(totalMO)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          {/* Discount */}
          <InfoBar
            icon="🏷️"
            label="Descuentos"
            status={discountPct > 0 ? `APLICA ${discountPct}%` : "NO APLICA"}
            detail={discountPct > 0 ? `${discountPct}% sobre material` : "Particular sin umbral de m²"}
          />

          {/* Grand total */}
          {(quote.total_ars || quote.total_usd) && (
            <div style={{
              marginTop: 20, padding: "16px 20px", borderRadius: 10,
              background: "var(--s3)", border: "1px solid var(--b2)",
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: "var(--t1)" }}>PRESUPUESTO TOTAL</span>
              <div style={{ textAlign: "right" }}>
                {quote.total_ars && (
                  <div style={{ fontSize: 18, fontWeight: 700, color: "var(--t1)" }}>
                    {fmtARS(quote.total_ars)} <span style={{ color: "var(--t3)", fontWeight: 400, fontSize: 13 }}>mano de obra</span>
                  </div>
                )}
                {quote.total_usd && (
                  <div style={{ fontSize: 15, fontWeight: 600, color: "var(--acc)", marginTop: 2 }}>
                    + {fmtUSD(quote.total_usd)} <span style={{ color: "var(--t3)", fontWeight: 400, fontSize: 13 }}>material</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </Section>
      ) : (
        /* Fallback for legacy quotes without breakdown */
        <Section title="Desglose">
          <div style={{ fontSize: 13, color: "var(--t3)" }}>
            Este presupuesto no tiene datos de desglose estructurados. Consultá el historial de chat para ver los detalles.
          </div>
          <button onClick={onSwitchToChat} style={{
            marginTop: 10, background: "none", border: "none", color: "var(--acc)",
            fontSize: 12, cursor: "pointer", fontFamily: "inherit", padding: 0,
          }}>
            Ver chat →
          </button>
        </Section>
      )}
    </div>
  );
}

// ── CHAT INPUT ──────────────────────────────────────────────────────────────

const VALID_TYPES = ["application/pdf", "image/jpeg", "image/jpg", "image/png", "image/webp"];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
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

  const addFiles = (newFiles: FileList | File[]) => {
    const arr = Array.from(newFiles);
    for (const f of arr) {
      if (!VALID_TYPES.some(t => f.type.includes(t.split("/")[1]))) {
        setFileError(`"${f.name}" — tipo no soportado`);
        setTimeout(() => setFileError(null), 3000);
        continue;
      }
      if (f.size > MAX_FILE_SIZE) {
        setFileError(`"${f.name}" — máximo 10MB`);
        setTimeout(() => setFileError(null), 3000);
        continue;
      }
      if (files.length >= MAX_FILES) {
        setFileError("Máximo 5 archivos");
        setTimeout(() => setFileError(null), 3000);
        break;
      }
      if (files.some(ef => ef.name === f.name && ef.size === f.size)) continue;
      setFiles([...files, f]);
    }
  };

  const removeFile = (idx: number) => setFiles(files.filter((_, i) => i !== idx));

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current++;
    setDragActive(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current--;
    if (dragCounterRef.current <= 0) { dragCounterRef.current = 0; setDragActive(false); }
  };
  const handleDragOver = (e: React.DragEvent) => e.preventDefault();
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current = 0;
    setDragActive(false);
    if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files);
  };

  const fmtSize = (b: number) => b < 1024 ? `${b} B` : b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(1)} MB`;
  const fmtType = (t: string) => t.includes("pdf") ? "PDF" : t.includes("jpeg") || t.includes("jpg") ? "JPG" : t.includes("png") ? "PNG" : "WEBP";
  const fileIcon = (t: string) => t.includes("pdf") ? "📄" : "🖼️";

  return (
    <div
      onDragEnter={handleDragEnter} onDragLeave={handleDragLeave}
      onDragOver={handleDragOver} onDrop={handleDrop}
      style={{ position: "relative" }}
    >
      {/* Drag overlay */}
      {dragActive && (
        <div style={{
          position: "absolute", inset: 0, zIndex: 10,
          background: "rgba(79,143,255,0.08)", border: "2px dashed var(--acc)",
          borderRadius: 12, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", gap: 6,
          pointerEvents: "none",
        }}>
          <span style={{ fontSize: 28 }}>📁</span>
          <span style={{ fontSize: 14, fontWeight: 500, color: "var(--acc)" }}>Soltá tu plano PDF o imagen acá</span>
          <span style={{ fontSize: 11, color: "var(--t3)" }}>PDF, JPG, PNG · Máximo 10MB</span>
        </div>
      )}

      {/* File chips */}
      {(files.length > 0 || fileError) && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
          {files.map((f, i) => (
            <div key={`${f.name}-${i}`} style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "5px 10px", borderRadius: 6,
              background: "var(--s3)", border: "1px solid var(--b1)",
              fontSize: 11, color: "var(--t2)", maxWidth: 280,
            }}>
              <span style={{ fontSize: 14 }}>{fileIcon(f.type)}</span>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{f.name}</span>
              <span style={{ color: "var(--t3)", flexShrink: 0 }}>{fmtType(f.type)} · {fmtSize(f.size)}</span>
              <button onClick={() => removeFile(i)} style={{ background: "none", border: "none", color: "var(--t3)", cursor: "pointer", fontSize: 13, padding: "0 2px" }}>✕</button>
            </div>
          ))}
          {fileError && (
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "5px 10px", borderRadius: 6,
              background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.3)",
              fontSize: 11, color: "var(--red)",
            }}>
              ⚠️ {fileError}
            </div>
          )}
        </div>
      )}

      {/* Input row */}
      <div style={{
        display: "flex", alignItems: "flex-end", gap: 8,
        background: "var(--s3)",
        border: dragActive ? "1px solid var(--acc)" : "1px solid var(--b2)",
        boxShadow: dragActive ? "0 0 20px rgba(79,143,255,0.15)" : "none",
        borderRadius: 12, padding: "10px 10px 10px 16px",
        transition: "border-color 0.15s, box-shadow 0.15s",
      }}>
        <textarea value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={onKey} rows={1} disabled={sending}
          placeholder="Escribí el enunciado o arrastrá el plano acá..."
          style={{
            flex: 1, background: "transparent", border: "none", outline: "none",
            fontFamily: "inherit", fontSize: 13, color: "var(--t1)",
            resize: "none", lineHeight: 1.5, maxHeight: 110,
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 5, flexShrink: 0 }}>
          <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" multiple style={{ display: "none" }}
            onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
          />
          <IconBtn onClick={() => fileRef.current?.click()} title="Adjuntar plano">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
            </svg>
          </IconBtn>
          <IconBtn onClick={send} primary disabled={sending || (!input.trim() && files.length === 0)}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </IconBtn>
        </div>
      </div>
    </div>
  );
}

// ── SUB-COMPONENTS ──────────────────────────────────────────────────────────

function Section({ title, children, style: extraStyle }: { title: string; children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: "var(--s1)", border: "1px solid var(--b1)",
      borderRadius: 12, padding: "18px 22px", ...extraStyle,
    }}>
      <div style={{
        fontSize: 13, fontWeight: 600, color: "var(--t1)",
        textTransform: "uppercase", letterSpacing: "0.06em",
        marginBottom: 14, paddingBottom: 8, borderBottom: "1px solid var(--b1)",
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function MetaItem({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: highlight ? 600 : 400, color: highlight ? "var(--t1)" : "var(--t2)" }}>{value}</div>
    </div>
  );
}

function ReqField({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", gap: 8, fontSize: 13 }}>
      <span style={{ color: "var(--t3)", minWidth: 110, flexShrink: 0 }}>{label}</span>
      <span style={{ color: "var(--t1)" }}>{value}</span>
    </div>
  );
}

function InfoBar({ icon, label, status, detail }: { icon: string; label: string; status: string; detail: string }) {
  const isNo = status.includes("NO");
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "10px 14px", borderRadius: 8,
      background: isNo ? "rgba(255,255,255,.02)" : "rgba(245,166,35,.06)",
      border: `1px solid ${isNo ? "var(--b1)" : "rgba(245,166,35,.16)"}`,
      fontSize: 12,
    }}>
      <span>{icon}</span>
      <span style={{ fontWeight: 600, color: "var(--t1)" }}>{label} — {status}</span>
      <span style={{ color: "var(--t3)" }}>{detail}</span>
    </div>
  );
}

function TabBtn({ active, children, onClick, disabled }: { active: boolean; children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={disabled ? undefined : onClick} style={{
      padding: "10px 20px", fontSize: 13, fontWeight: 500,
      border: "none", borderBottom: active ? "2px solid var(--acc)" : "2px solid transparent",
      background: "transparent",
      color: disabled ? "var(--t4)" : active ? "var(--acc)" : "var(--t3)",
      cursor: disabled ? "default" : "pointer",
      fontFamily: "inherit",
      opacity: disabled ? 0.5 : 1,
    }}>
      {children}
    </button>
  );
}

function FileLink({ href, label, color }: { href: string; label: string; color: string }) {
  const emoji = label === "PDF" ? "📄" : label === "Excel" ? "📊" : "☁";
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" style={{
      display: "flex", alignItems: "center", gap: 5,
      padding: "6px 12px", borderRadius: 6,
      fontSize: 11, fontWeight: 500, textDecoration: "none",
      border: `1px solid ${color}33`, background: "transparent", color,
    }}>
      {emoji} {label}
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

// ── STYLES ───────────────────────────────────────────────────────────────────

const backBtnStyle: React.CSSProperties = {
  width: 30, height: 30, borderRadius: 6,
  border: "1px solid var(--b1)", background: "transparent",
  color: "var(--t2)", cursor: "pointer",
  display: "flex", alignItems: "center", justifyContent: "center",
};

const badgeStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 4,
  padding: "2px 8px", borderRadius: 999, fontSize: 10, fontWeight: 600,
};

const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse",
  border: "1px solid var(--b1)", borderRadius: 8, overflow: "hidden",
};

const thStyle: React.CSSProperties = {
  padding: "8px 12px", fontSize: 11, fontWeight: 600,
  color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.05em",
  background: "rgba(255,255,255,.03)", borderBottom: "1px solid var(--b1)",
  textAlign: "left",
};

const tdStyle: React.CSSProperties = {
  padding: "9px 12px", fontSize: 13, color: "var(--t2)",
  borderBottom: "1px solid rgba(255,255,255,.04)",
};
