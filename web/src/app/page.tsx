"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchQuotes, updateQuoteStatus, deleteQuote, type Quote } from "@/lib/api";
import { format } from "date-fns";
import { es } from "date-fns/locale";

const STATUS_LABEL: Record<Quote["status"], string> = {
  draft: "Borrador", validated: "Validado", sent: "Enviado",
};

const BADGE_STYLE: Record<Quote["status"], React.CSSProperties> = {
  draft:     { background: "var(--amb2)", color: "var(--amb)" },
  validated: { background: "var(--grn2)", color: "var(--grn)" },
  sent:      { background: "var(--acc2)", color: "var(--acc)" },
};

const STATUS_NEXT: Record<Quote["status"], Quote["status"]> = {
  draft: "validated", validated: "sent", sent: "draft",
};

export default function DashboardPage() {
  const router = useRouter();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    fetchQuotes().then(setQuotes).finally(() => setLoading(false));
  }, []);

  // Drafts older than 5 days
  const staleDrafts = quotes.filter(q => {
    if (q.status !== "draft") return false;
    const days = (Date.now() - new Date(q.created_at).getTime()) / 86400000;
    return days > 5;
  });

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  async function toggleStatus(e: React.MouseEvent, id: string, current: Quote["status"]) {
    e.stopPropagation();
    const next = STATUS_NEXT[current];
    await updateQuoteStatus(id, next);
    setQuotes(prev => prev.map(q => q.id === id ? { ...q, status: next } : q));
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (confirmDeleteId === id) {
      try {
        await deleteQuote(id);
        setQuotes(prev => prev.filter(q => q.id !== id));
      } catch (err) {
        console.error("Error deleting quote:", err);
        alert("Error al eliminar el presupuesto. Intentá de nuevo.");
      }
      setConfirmDeleteId(null);
    } else {
      setConfirmDeleteId(id);
      setTimeout(() => setConfirmDeleteId(null), 3000);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "20px 28px 18px",
        borderBottom: "1px solid var(--b1)", flexShrink: 0,
      }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 500, letterSpacing: "-0.03em" }}>Presupuestos</div>
          <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 2 }}>
            {new Date().toLocaleDateString("es-AR", { month: "long", year: "numeric" })} · {quotes.length} registros
          </div>
        </div>
        <button style={btnStyle} onClick={() => {}}>Exportar CSV</button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>

        {/* Needs action banner */}
        {staleDrafts.length > 0 && (
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            background: "rgba(245,166,35,.06)",
            border: "1px solid rgba(245,166,35,.16)",
            borderRadius: 8, padding: "10px 14px",
            marginBottom: 20, fontSize: 12, color: "var(--amb)",
          }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--amb)", flexShrink: 0 }} />
            <span>
              <strong style={{ color: "var(--amb)" }}>{staleDrafts.length} {staleDrafts.length === 1 ? "presupuesto en borrador lleva" : "presupuestos en borrador llevan"} más de 5 días sin acción</strong>
              {" — "}{staleDrafts.map(q => q.client_name || "Sin nombre").join(" y ")}
            </span>
          </div>
        )}

        {/* KPIs */}
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(4,1fr)",
          gap: 1, marginBottom: 24,
          background: "var(--b1)", borderRadius: 10, overflow: "hidden",
        }}>
          {[
            { label: "Total", value: quotes.length, sub: "presupuestos", main: true },
            { label: "Borradores", value: quotes.filter(q => q.status === "draft").length, sub: "en proceso" },
            { label: "Validados", value: quotes.filter(q => q.status === "validated").length, sub: "listos" },
            { label: "Enviados", value: quotes.filter(q => q.status === "sent").length, sub: "este mes" },
          ].map(k => (
            <div key={k.label} style={{
              background: k.main ? "var(--s3)" : "var(--s2)",
              padding: "18px 20px",
              borderLeft: k.main ? "2px solid var(--acc)" : undefined,
            }}>
              <div style={{ fontSize: 10, fontWeight: 500, color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.09em", marginBottom: 10 }}>{k.label}</div>
              <div style={{
                fontSize: k.main ? 34 : 26,
                fontWeight: 300, letterSpacing: "-0.04em",
                color: k.main ? "var(--acc)" : "var(--t1)",
                lineHeight: 1,
                fontFamily: "'Geist Mono', monospace",
              }}>{k.value}</div>
              <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 5 }}>{k.sub}</div>
            </div>
          ))}
        </div>

        {/* Table */}
        {loading ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 200, color: "var(--t3)", fontSize: 13 }}>
            Cargando...
          </div>
        ) : (
          <div style={{ background: "var(--s1)", border: "1px solid var(--b1)", borderRadius: 10, overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead style={{ background: "var(--s2)", borderBottom: "1px solid var(--b1)" }}>
                <tr>
                  {["Cliente", "Material", "Importe", "Estado", "Fecha", "Archivos", ""].map((h, i) => (
                    <th key={h} style={{
                      textAlign: i >= 2 ? "right" : "left",
                      padding: "10px 18px",
                      fontSize: 10, fontWeight: 500, color: "var(--t3)",
                      textTransform: "uppercase", letterSpacing: "0.09em",
                      ...(h === "Cliente" && { width: "28%" }),
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {quotes.map(q => {
                  const daysOld = (Date.now() - new Date(q.created_at).getTime()) / 86400000;
                  const isStale = q.status === "draft" && daysOld > 5;
                  return (
                    <tr key={q.id}
                      onClick={() => { setSelectedId(q.id); router.push(`/quote/${q.id}`); }}
                      style={{
                        borderBottom: "1px solid rgba(255,255,255,.045)",
                        cursor: "pointer",
                        background: selectedId === q.id ? "rgba(79,143,255,.07)" : undefined,
                        borderLeft: selectedId === q.id ? "2px solid var(--acc)" : "2px solid transparent",
                        transition: "background .08s",
                      }}
                      onMouseEnter={e => { if (selectedId !== q.id) (e.currentTarget as HTMLTableRowElement).style.background = "rgba(255,255,255,.035)"; }}
                      onMouseLeave={e => { if (selectedId !== q.id) (e.currentTarget as HTMLTableRowElement).style.background = ""; }}
                    >
                      <td style={{ padding: "13px 18px" }}>
                        <div style={{ fontSize: 13, fontWeight: 500, color: "var(--t1)", letterSpacing: "-0.01em" }}>
                          {q.client_name || <span style={{ color: "var(--t3)", fontStyle: "italic" }}>Sin nombre</span>}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 1 }}>{q.project}</div>
                      </td>
                      <td style={{ padding: "13px 18px", fontSize: 12, color: "var(--t2)" }}>{q.material || "—"}</td>
                      <td style={{ padding: "13px 18px", textAlign: "right" }}>
                        <div style={{ fontSize: 13, color: "var(--t1)", fontFamily: "'Geist Mono',monospace", letterSpacing: "-0.02em" }}>
                          {q.total_ars ? `$${q.total_ars.toLocaleString("es-AR")}` : "—"}
                        </div>
                        {q.total_usd && (
                          <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 1 }}>USD {q.total_usd.toLocaleString()}</div>
                        )}
                      </td>
                      <td style={{ padding: "13px 18px" }}>
                        <button onClick={(e) => toggleStatus(e, q.id, q.status)} style={{
                          display: "inline-flex", alignItems: "center", gap: 5,
                          padding: "3px 9px", borderRadius: 999,
                          fontSize: 11, fontWeight: 500, cursor: "pointer",
                          border: "none", fontFamily: "inherit",
                          ...BADGE_STYLE[q.status],
                        }}>
                          <span style={{ width: 5, height: 5, borderRadius: "50%", background: "currentColor", display: "inline-block" }} />
                          {STATUS_LABEL[q.status]}
                        </button>
                      </td>
                      <td style={{ padding: "13px 18px", fontSize: 11, textAlign: "right", color: isStale ? "var(--amb)" : "var(--t3)" }}>
                        {format(new Date(q.created_at), "d MMM", { locale: es })}
                        {isStale && ` ·${Math.floor(daysOld)}d`}
                      </td>
                      <td style={{ padding: "13px 18px" }}>
                        <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }} onClick={e => e.stopPropagation()}>
                          {q.pdf_url && <FileBtn href={q.pdf_url} emoji="📄" />}
                          {q.excel_url && <FileBtn href={q.excel_url} emoji="📊" />}
                          {q.drive_url && <FileBtn href={q.drive_url} emoji="☁" />}
                        </div>
                      </td>
                      <td style={{ padding: "13px 10px", width: 40 }}>
                        <button
                          onClick={(e) => handleDelete(e, q.id)}
                          title={confirmDeleteId === q.id ? "Click de nuevo para confirmar" : "Eliminar presupuesto"}
                          style={{
                            width: 28, height: 28, borderRadius: 6,
                            border: confirmDeleteId === q.id ? "1px solid rgba(255,69,58,.5)" : "1px solid var(--b1)",
                            background: confirmDeleteId === q.id ? "rgba(255,69,58,.12)" : "transparent",
                            color: confirmDeleteId === q.id ? "#ff453a" : "var(--t3)",
                            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 12, transition: "all .15s",
                          }}
                        >
                          {confirmDeleteId === q.id ? "✓" : "✕"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function FileBtn({ href, emoji }: { href: string; emoji: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer"
      style={{
        width: 26, height: 26, borderRadius: 5,
        border: "1px solid var(--b1)", background: "transparent",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 11, cursor: "pointer", textDecoration: "none", color: "var(--t2)",
        transition: "all .1s",
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--b2)";
        (e.currentTarget as HTMLAnchorElement).style.background = "rgba(255,255,255,.06)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--b1)";
        (e.currentTarget as HTMLAnchorElement).style.background = "transparent";
      }}
    >{emoji}</a>
  );
}

const btnStyle: React.CSSProperties = {
  padding: "7px 13px", borderRadius: 6,
  fontSize: 12, fontWeight: 500, fontFamily: "inherit",
  cursor: "pointer", border: "1px solid var(--b1)",
  background: "transparent", color: "var(--t2)", letterSpacing: "-0.01em",
};
