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

const STATUS_NEXT: Record<Quote["status"], Quote["status"] | null> = {
  draft: "validated", validated: "sent", sent: null,
};

export default function DashboardPage() {
  const router = useRouter();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("todos");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchQuotes().then(setQuotes).finally(() => setLoading(false));
  }, []);

  // Drafts older than 5 days
  const staleDrafts = quotes.filter(q => {
    if (q.status !== "draft") return false;
    const days = (Date.now() - new Date(q.created_at).getTime()) / 86400000;
    return days > 5;
  });

  // Filter by status/source + search
  const filteredQuotes = quotes.filter(q => {
    if (statusFilter === "web" && q.source !== "web") return false;
    else if (statusFilter !== "todos" && statusFilter !== "web" && q.status !== statusFilter) return false;
    if (search) {
      const s = search.toLowerCase();
      return (
        (q.client_name || "").toLowerCase().includes(s) ||
        (q.material || "").toLowerCase().includes(s) ||
        (q.project || "").toLowerCase().includes(s)
      );
    }
    return true;
  });

  const statusCounts = {
    todos: quotes.length,
    draft: quotes.filter(q => q.status === "draft").length,
    validated: quotes.filter(q => q.status === "validated").length,
    sent: quotes.filter(q => q.status === "sent").length,
    web: quotes.filter(q => q.source === "web").length,
  };

  async function toggleStatus(e: React.MouseEvent, id: string, current: Quote["status"]) {
    e.stopPropagation();
    const next = STATUS_NEXT[current];
    if (!next) return; // "sent" is final — no more transitions
    await updateQuoteStatus(id, next);
    setQuotes(prev => prev.map(q => q.id === id ? { ...q, status: next } : q));
  }

  function askDelete(e: React.MouseEvent, id: string, clientName: string) {
    e.stopPropagation();
    e.preventDefault();
    setDeleteTarget({ id, name: clientName || "Sin nombre" });
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteQuote(deleteTarget.id);
      setQuotes(prev => prev.filter(q => q.id !== deleteTarget.id));
    } catch (err) {
      console.error("Error deleting quote:", err);
    }
    setDeleting(false);
    setDeleteTarget(null);
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

        {/* KPIs removed — info is now in the filter chips */}

        {/* Filter bar + Table */}
        {loading ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 200, color: "var(--t3)", fontSize: 13 }}>
            Cargando...
          </div>
        ) : (
          <div style={{ background: "var(--s1)", border: "1px solid var(--b1)", borderRadius: 10, overflow: "hidden" }}>
            {/* Filter bar */}
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "10px 16px", background: "var(--s2)",
              borderBottom: "1px solid var(--b1)",
            }}>
              <div style={{ display: "flex", gap: 6 }}>
                {([
                  { key: "todos", label: "Todos" },
                  { key: "draft", label: "Borrador" },
                  { key: "validated", label: "Validado" },
                  { key: "sent", label: "Enviado" },
                  { key: "web", label: "Web" },
                ] as const).map(f => (
                  <button key={f.key} onClick={() => setStatusFilter(f.key)} style={{
                    padding: "5px 12px", borderRadius: 6, fontSize: 12, fontWeight: 500,
                    border: statusFilter === f.key ? "1px solid var(--acc3)" : "1px solid var(--b1)",
                    background: statusFilter === f.key ? "var(--acc2)" : "transparent",
                    color: statusFilter === f.key ? "var(--acc)" : "var(--t3)",
                    cursor: "pointer", fontFamily: "inherit",
                    display: "flex", alignItems: "center", gap: 6,
                  }}>
                    {f.label}
                    <span style={{
                      fontSize: 10, padding: "1px 6px", borderRadius: 99,
                      background: statusFilter === f.key ? "rgba(79,143,255,.2)" : "rgba(255,255,255,.06)",
                    }}>{statusCounts[f.key]}</span>
                  </button>
                ))}
              </div>
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "6px 12px", borderRadius: 8,
                border: "1px solid var(--b1)", background: "var(--s3)", width: 240,
              }}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--t3)", flexShrink: 0 }}>
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Buscar cliente, material..."
                  style={{
                    background: "transparent", border: "none", outline: "none",
                    color: "var(--t1)", fontSize: 12, fontFamily: "inherit", width: "100%",
                  }}
                />
                {search && (
                  <button onClick={() => setSearch("")} style={{
                    background: "none", border: "none", color: "var(--t3)",
                    cursor: "pointer", fontSize: 11, padding: 0,
                  }}>✕</button>
                )}
              </div>
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead style={{ background: "var(--s2)", borderBottom: "1px solid var(--b1)" }}>
                <tr>
                  {["Cliente", "Material", "Importe", "Estado", "Fecha", "Archivos", ""].map((h, i) => (
                    <th key={h} style={{
                      textAlign: h === "Estado" ? "center" : i >= 2 ? "right" : "left",
                      padding: "10px 18px",
                      fontSize: 10, fontWeight: 500, color: "var(--t3)",
                      textTransform: "uppercase", letterSpacing: "0.09em",
                      ...(h === "Cliente" && { width: "28%" }),
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredQuotes.map(q => {
                  const daysOld = (Date.now() - new Date(q.created_at).getTime()) / 86400000;
                  const isStale = q.status === "draft" && daysOld > 5;
                  const isUnread = !q.is_read;
                  return (
                    <tr key={q.id}
                      onClick={() => { setSelectedId(q.id); router.push(`/quote/${q.parent_quote_id || q.id}`); }}
                      style={{
                        borderBottom: "1px solid rgba(255,255,255,.045)",
                        cursor: "pointer",
                        background: selectedId === q.id
                          ? "rgba(79,143,255,.07)"
                          : isUnread ? "rgba(79,143,255,.04)" : undefined,
                        borderLeft: selectedId === q.id ? "2px solid var(--acc)" : "2px solid transparent",
                        transition: "background .08s",
                      }}
                      onMouseEnter={e => { if (selectedId !== q.id) (e.currentTarget as HTMLTableRowElement).style.background = isUnread ? "rgba(79,143,255,.07)" : "rgba(255,255,255,.035)"; }}
                      onMouseLeave={e => { if (selectedId !== q.id) (e.currentTarget as HTMLTableRowElement).style.background = isUnread ? "rgba(79,143,255,.04)" : ""; }}
                    >
                      <td style={{ padding: "13px 18px", paddingLeft: 18 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
                          {isUnread && (
                            <span style={{
                              width: 7, height: 7, borderRadius: "50%",
                              background: "var(--acc)", flexShrink: 0,
                              marginRight: 8,
                            }} />
                          )}
                          <div>
                            <div style={{ fontSize: 13, fontWeight: isUnread ? 600 : 500, color: "var(--t1)", letterSpacing: "-0.01em" }}>
                              {q.client_name || <span style={{ color: "var(--t3)", fontStyle: "italic" }}>Sin nombre</span>}
                              {q.source === "web" && (
                                <span style={{
                                  marginLeft: 6, fontSize: 9, fontWeight: 600,
                                  padding: "1px 5px", borderRadius: 4,
                                  background: "rgba(138,43,226,.15)", color: "#a855f7",
                                  letterSpacing: "0.03em",
                                }}>WEB</span>
                              )}
                              {isUnread && (
                                <span style={{
                                  marginLeft: 6, fontSize: 9, fontWeight: 600,
                                  padding: "1px 6px", borderRadius: 4,
                                  background: "var(--acc2)", color: "var(--acc)",
                                  letterSpacing: "0.03em",
                                }}>NUEVO</span>
                              )}
                            </div>
                            <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 1 }}>{q.project}</div>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: "13px 18px", fontSize: 12, color: isUnread ? "var(--t1)" : "var(--t2)", fontWeight: isUnread ? 500 : 400 }}>{q.material || "—"}</td>
                      <td style={{ padding: "13px 18px", textAlign: "right" }}>
                        <div style={{ fontSize: 13, color: "var(--t1)", fontFamily: "'Geist Mono',monospace", letterSpacing: "-0.02em" }}>
                          {q.total_ars ? `$${q.total_ars.toLocaleString("es-AR")}` : "—"}
                        </div>
                        {q.total_usd && (
                          <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 1 }}>USD {q.total_usd.toLocaleString()}</div>
                        )}
                      </td>
                      <td style={{ padding: "13px 18px", textAlign: "center" }}>
                        <button
                          onClick={(e) => toggleStatus(e, q.id, q.status)}
                          title={STATUS_NEXT[q.status] ? `Cambiar a ${STATUS_LABEL[STATUS_NEXT[q.status]!]}` : "Estado final"}
                          style={{
                          display: "inline-flex", alignItems: "center", gap: 5,
                          padding: "3px 9px", borderRadius: 999,
                          fontSize: 11, fontWeight: 500,
                          cursor: STATUS_NEXT[q.status] ? "pointer" : "default",
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
                          onClick={(e) => askDelete(e, q.id, q.client_name)}
                          title="Eliminar presupuesto"
                          style={{
                            width: 28, height: 28, borderRadius: 6,
                            border: "1px solid var(--b1)",
                            background: "transparent",
                            color: "var(--t3)",
                            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 12, transition: "all .15s",
                          }}
                          onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(255,69,58,.5)"; e.currentTarget.style.color = "#ff453a"; }}
                          onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--b1)"; e.currentTarget.style.color = "var(--t3)"; }}
                        >
                          ✕
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

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div
          onClick={() => setDeleteTarget(null)}
          style={{
            position: "fixed", inset: 0, zIndex: 999,
            background: "rgba(0,0,0,.6)", backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: "var(--s2)", border: "1px solid var(--b2)",
              borderRadius: 14, padding: "28px 32px", width: 380,
              boxShadow: "0 20px 60px rgba(0,0,0,.5)",
            }}
          >
            <div style={{ fontSize: 15, fontWeight: 500, color: "var(--t1)", marginBottom: 8 }}>
              Eliminar presupuesto
            </div>
            <div style={{ fontSize: 13, color: "var(--t2)", lineHeight: 1.6, marginBottom: 24 }}>
              ¿Eliminar el presupuesto de <strong style={{ color: "var(--t1)" }}>{deleteTarget.name}</strong>? Esta acción no se puede deshacer.
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button
                onClick={() => setDeleteTarget(null)}
                style={{
                  padding: "8px 18px", borderRadius: 8,
                  fontSize: 13, fontWeight: 500, fontFamily: "inherit",
                  cursor: "pointer", border: "1px solid var(--b2)",
                  background: "transparent", color: "var(--t2)",
                }}
              >
                Cancelar
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleting}
                style={{
                  padding: "8px 18px", borderRadius: 8,
                  fontSize: 13, fontWeight: 500, fontFamily: "inherit",
                  cursor: deleting ? "wait" : "pointer", border: "none",
                  background: "var(--red)", color: "#fff",
                  opacity: deleting ? 0.6 : 1,
                }}
              >
                {deleting ? "Eliminando..." : "Eliminar"}
              </button>
            </div>
          </div>
        </div>
      )}
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
