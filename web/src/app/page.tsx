"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { type Quote, deriveMaterial } from "@/lib/api";
import { useQuotes } from "@/lib/quotes-context";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import clsx from "clsx";

const STATUS_LABEL: Record<Quote["status"], string> = {
  draft: "Borrador", pending: "Pendiente", validated: "Validado", sent: "Enviado",
};

const BADGE_CLASS: Record<Quote["status"], string> = {
  draft:     "bg-amb-bg text-amb",
  pending:   "bg-acc-bg text-acc",
  validated: "bg-grn-bg text-grn",
  sent:      "bg-acc-bg text-acc",
};

const STATUS_NEXT: Record<Quote["status"], Quote["status"] | null> = {
  draft: "validated", pending: "validated", validated: "sent", sent: null,
};

export default function DashboardPage() {
  const router = useRouter();
  const { quotes, loading, error: loadError, refresh, removeQuote, setStatus, addQuote } = useQuotes();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [statusTarget, setStatusTarget] = useState<{ id: string; current: Quote["status"]; next: Quote["status"] } | null>(null);
  const [changingStatus, setChangingStatus] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("todos");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [deriveTarget, setDeriveTarget] = useState<{ id: string; material: string; client: string } | null>(null);
  const [deriveMat, setDeriveMat] = useState("");
  const [deriveThickness, setDeriveThickness] = useState("");
  const [deriving, setDeriving] = useState(false);
  const [deriveError, setDeriveError] = useState("");

  const staleDrafts = useMemo(() => quotes.filter(q => {
    if (q.status !== "draft") return false;
    return (Date.now() - new Date(q.created_at).getTime()) / 86400000 > 5;
  }), [quotes]);

  const filteredQuotes = useMemo(() => quotes.filter(q => {
    if (statusFilter === "web" && q.source !== "web") return false;
    else if (statusFilter !== "todos" && statusFilter !== "web" && q.status !== statusFilter) return false;
    if (dateFrom) {
      const from = new Date(dateFrom);
      if (new Date(q.created_at) < from) return false;
    }
    if (dateTo) {
      const to = new Date(dateTo + "T23:59:59");
      if (new Date(q.created_at) > to) return false;
    }
    if (search) {
      const s = search.toLowerCase();
      return (q.client_name || "").toLowerCase().includes(s) ||
             (q.material || "").toLowerCase().includes(s) ||
             (q.project || "").toLowerCase().includes(s);
    }
    return true;
  }), [quotes, statusFilter, search, dateFrom, dateTo]);

  const statusCounts = useMemo(() => ({
    todos: quotes.length,
    draft: quotes.filter(q => q.status === "draft").length,
    pending: quotes.filter(q => q.status === "pending").length,
    validated: quotes.filter(q => q.status === "validated").length,
    sent: quotes.filter(q => q.status === "sent").length,
    web: quotes.filter(q => q.source === "web").length,
  }), [quotes]);

  function toggleStatus(e: React.MouseEvent, id: string, current: Quote["status"]) {
    e.stopPropagation();
    const next = STATUS_NEXT[current];
    if (!next) return;
    setStatusTarget({ id, current, next });
  }

  async function confirmStatusChange() {
    if (!statusTarget) return;
    setChangingStatus(true);
    try {
      await setStatus(statusTarget.id, statusTarget.next);
    } catch { /* toast already shown by context */ }
    setChangingStatus(false);
    setStatusTarget(null);
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
      await removeQuote(deleteTarget.id);
    } catch { /* toast already shown by context */ }
    setDeleting(false);
    setDeleteTarget(null);
  }

  function askDerive(e: React.MouseEvent, id: string, material: string, client: string) {
    e.stopPropagation();
    e.preventDefault();
    setDeriveTarget({ id, material: material || "", client: client || "Sin nombre" });
    setDeriveMat("");
    setDeriveThickness("");
    setDeriveError("");
  }

  function closeDerive() {
    setDeriveTarget(null);
    setDeriveMat("");
    setDeriveThickness("");
    setDeriveError("");
    setDeriving(false);
  }

  async function confirmDerive() {
    if (!deriveTarget) return;
    const mat = deriveMat.trim();
    if (!mat) { setDeriveError("Ingres\u00E1 un material."); return; }
    const thk = deriveThickness.trim();
    let thickness_mm: number | undefined;
    if (thk) {
      const n = Number(thk);
      if (!Number.isFinite(n) || n <= 0) { setDeriveError("El espesor debe ser un n\u00FAmero mayor a 0."); return; }
      thickness_mm = Math.round(n);
    }
    setDeriving(true);
    setDeriveError("");
    try {
      const res = await deriveMaterial(deriveTarget.id, { material: mat, ...(thickness_mm ? { thickness_mm } : {}) });
      closeDerive();
      refresh();
      router.push(`/quote/${res.quote_id}`);
    } catch (err: any) {
      setDeriveError(err.message || "Error al crear variante");
    } finally {
      setDeriving(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 md:px-7 pt-4 md:pt-5 pb-3 md:pb-[18px] border-b border-b1 shrink-0">
        <div>
          <div className="text-base md:text-lg font-medium -tracking-[0.03em]">Presupuestos</div>
          <div className="text-[11px] text-t3 mt-0.5">
            {new Date().toLocaleDateString("es-AR", { month: "long", year: "numeric" })} · {quotes.length} registros
          </div>
        </div>
        <button
          onClick={() => {
            const rows = [["Cliente","Proyecto","Material","ARS","USD","Estado","Fuente","Fecha"]];
            filteredQuotes.forEach(q => rows.push([
              q.client_name, q.project, q.material || "", String(q.total_ars || ""), String(q.total_usd || ""),
              q.status, q.source || "operator", new Date(q.created_at).toLocaleDateString("es-AR"),
            ]));
            const csv = rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
            const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
            const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
            a.download = `presupuestos-${new Date().toISOString().slice(0,10)}.csv`; a.click();
          }}
          className="px-3 py-[7px] rounded-md text-xs font-medium font-sans cursor-pointer border border-b1 bg-transparent text-t2 -tracking-[0.01em] hover:border-b2 hover:text-t1 transition"
        >
          Exportar CSV
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 md:px-7 py-4 md:py-6">
        {/* Stale drafts banner */}
        {staleDrafts.length > 0 && (
          <div className="flex items-center gap-2.5 bg-amb/[0.06] border border-amb/[0.16] rounded-lg px-3.5 py-2.5 mb-5 text-xs text-amb">
            <div className="w-1.5 h-1.5 rounded-full bg-amb shrink-0" />
            <span>
              <strong>{staleDrafts.length} {staleDrafts.length === 1 ? "presupuesto en borrador lleva" : "presupuestos en borrador llevan"} más de 5 días sin acción</strong>
              {" — "}{staleDrafts.map(q => q.client_name || "Sin nombre").join(" y ")}
            </span>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center h-[200px] text-t3 text-[13px]">Cargando...</div>
        ) : loadError ? (
          <div className="flex flex-col items-center justify-center h-[200px] gap-3">
            <div className="text-err text-[13px]">✕ {loadError}</div>
            <button onClick={() => refresh()} className="px-3 py-1.5 rounded-md text-xs font-medium border border-b1 bg-transparent text-t2 cursor-pointer hover:border-b2 hover:text-t1 transition">
              Reintentar
            </button>
          </div>
        ) : (
          <div className="bg-s1 border border-b1 rounded-[10px] overflow-hidden">
            {/* Filter bar */}
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 px-3 md:px-4 py-2.5 bg-s2 border-b border-b1">
              <div className="flex gap-1.5 overflow-x-auto pb-1 md:pb-0">
                {([
                  { key: "todos", label: "Todos" },
                  { key: "draft", label: "Borrador" },
                  { key: "pending", label: "Pendiente" },
                  { key: "validated", label: "Validado" },
                  { key: "sent", label: "Enviado" },
                  { key: "web", label: "Web" },
                ] as const).map(f => (
                  <button
                    key={f.key}
                    onClick={() => setStatusFilter(f.key)}
                    className={clsx(
                      "flex items-center gap-1.5 px-3 py-[5px] rounded-md text-xs font-medium font-sans cursor-pointer border transition",
                      statusFilter === f.key
                        ? "border-acc-hover bg-acc-bg text-acc"
                        : "border-b1 bg-transparent text-t3 hover:text-t2 hover:border-b2",
                    )}
                  >
                    {f.label}
                    <span className={clsx(
                      "text-[10px] px-1.5 py-px rounded-full",
                      statusFilter === f.key ? "bg-acc/20" : "bg-white/[0.06]",
                    )}>
                      {statusCounts[f.key]}
                    </span>
                  </button>
                ))}
              </div>
              <div className="hidden md:flex items-center gap-2">
                <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="px-2 py-[5px] rounded-md text-[11px] font-sans border border-b1 bg-s3 text-t2 outline-none w-[120px] [color-scheme:dark]" title="Desde" />
                <span className="text-t4 text-[10px]">—</span>
                <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="px-2 py-[5px] rounded-md text-[11px] font-sans border border-b1 bg-s3 text-t2 outline-none w-[120px] [color-scheme:dark]" title="Hasta" />
                {(dateFrom || dateTo) && (
                  <button onClick={() => { setDateFrom(""); setDateTo(""); }} className="text-t3 text-[11px] bg-transparent border-none cursor-pointer hover:text-t2 p-0">✕</button>
                )}
              </div>
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-b1 bg-s3 w-full md:w-60">
                <svg className="text-t3 shrink-0" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Buscar cliente, material..."
                  aria-label="Buscar presupuestos"
                  className="bg-transparent border-none outline-none text-t1 text-xs font-sans w-full placeholder:text-t4"
                />
                {search && (
                  <button onClick={() => setSearch("")} className="bg-transparent border-none text-t3 cursor-pointer text-[11px] p-0 hover:text-t2">
                    ✕
                  </button>
                )}
              </div>
            </div>

            {/* Mobile Cards */}
            <div className="md:hidden divide-y divide-white/[0.045]">
              {filteredQuotes.map(q => {
                const isUnread = !q.is_read;
                return (
                  <div key={q.id} onClick={() => { setSelectedId(q.id); router.push(`/quote/${q.id}`); }}
                    className={clsx("flex items-center gap-3 px-3 py-3 cursor-pointer active:bg-white/[0.04] transition", isUnread && "bg-acc/[0.04]")}>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        {isUnread && <span className="w-[6px] h-[6px] rounded-full bg-acc shrink-0" />}
                        <span className={clsx("text-[13px] truncate", isUnread ? "font-semibold text-t1" : "font-medium text-t1")}>{q.client_name || "Sin nombre"}</span>
                        {q.source === "web" && <span className="text-[8px] font-semibold px-1 py-px rounded bg-purple-500/15 text-purple-400">WEB</span>}
                      </div>
                      <div className="text-[11px] text-t3 truncate mt-0.5">{q.material || "\u2014"}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-[13px] font-mono text-t1">{q.total_ars ? `$${q.total_ars.toLocaleString("es-AR")}` : "\u2014"}</div>
                      {q.total_usd ? <div className="text-[10px] text-t3">USD {q.total_usd.toLocaleString()}</div> : null}
                    </div>
                    {q.material && (
                      <button
                        onClick={(e) => askDerive(e, q.id, q.material || "", q.client_name)}
                        title="Duplicar con otro material"
                        className="w-7 h-7 rounded-md border border-b1 bg-transparent text-t3 cursor-pointer flex items-center justify-center text-[10px] shrink-0 transition-all hover:border-acc/50 hover:text-acc"
                      >
                        +M
                      </button>
                    )}
                    <span className={clsx("text-[10px] font-medium px-1.5 py-[2px] rounded-full shrink-0", BADGE_CLASS[q.status])}>{STATUS_LABEL[q.status]}</span>
                  </div>
                );
              })}
            </div>

            {/* Desktop Table */}
            <table className="w-full border-collapse hidden md:table">
              <thead className="bg-s2 border-b border-b1">
                <tr>
                  <th className="text-left px-[18px] py-2.5 text-[10px] font-medium text-t3 uppercase tracking-[0.09em] w-[28%]">Cliente</th>
                  <th className="text-left px-[18px] py-2.5 text-[10px] font-medium text-t3 uppercase tracking-[0.09em]">Material</th>
                  <th className="text-right px-[18px] py-2.5 text-[10px] font-medium text-t3 uppercase tracking-[0.09em]">Importe</th>
                  <th className="text-center px-[18px] py-2.5 text-[10px] font-medium text-t3 uppercase tracking-[0.09em]">Estado</th>
                  <th className="text-right px-[18px] py-2.5 text-[10px] font-medium text-t3 uppercase tracking-[0.09em]">Fecha</th>
                  <th className="text-right px-[18px] py-2.5 text-[10px] font-medium text-t3 uppercase tracking-[0.09em]">Archivos</th>
                  <th className="px-[18px] py-2.5 w-10"></th>
                </tr>
              </thead>
              <tbody>
                {filteredQuotes.map(q => {
                  const daysOld = (Date.now() - new Date(q.created_at).getTime()) / 86400000;
                  const isStale = q.status === "draft" && daysOld > 5;
                  const isUnread = !q.is_read;
                  const isSelected = selectedId === q.id;
                  return (
                    <tr
                      key={q.id}
                      onClick={() => { setSelectedId(q.id); router.push(`/quote/${q.id}`); }}
                      className={clsx(
                        "border-b border-white/[0.045] cursor-pointer transition-[background] duration-75",
                        isSelected
                          ? "bg-acc/[0.07] border-l-2 border-l-acc"
                          : isUnread
                            ? "bg-acc/[0.04] border-l-2 border-l-transparent hover:bg-acc/[0.07]"
                            : "border-l-2 border-l-transparent hover:bg-white/[0.035]",
                      )}
                    >
                      {/* Cliente */}
                      <td className="px-[18px] py-[13px] max-w-[300px]">
                        <div className="flex items-center">
                          {isUnread && <span className="w-[7px] h-[7px] rounded-full bg-acc shrink-0 mr-2" />}
                          <div className="min-w-0">
                            <div className={clsx("text-[13px] text-t1 -tracking-[0.01em] truncate", isUnread ? "font-semibold" : "font-medium")}>
                              {q.client_name || <span className="text-t3 italic">Sin nombre</span>}
                              {q.source === "web" && (
                                <span className="ml-1.5 text-[9px] font-semibold px-[5px] py-px rounded bg-purple-500/15 text-purple-400 tracking-wide">WEB</span>
                              )}
                              {isUnread && (
                                <span className="ml-1.5 text-[9px] font-semibold px-1.5 py-px rounded bg-acc-bg text-acc tracking-wide">NUEVO</span>
                              )}
                            </div>
                            <div className="text-[11px] text-t3 mt-px truncate">{q.project}</div>
                          </div>
                        </div>
                      </td>
                      {/* Material */}
                      <td className={clsx("px-[18px] py-[13px] text-xs max-w-[250px] truncate", isUnread ? "text-t1 font-medium" : "text-t2")}>
                        {q.quote_kind === "building_parent" ? (
                          <span className="flex items-center gap-1.5">
                            <span className="text-[9px] font-semibold px-1.5 py-px rounded bg-purple-500/15 text-purple-400">OBRA</span>
                            {q.material || q.project || "Edificio"}
                          </span>
                        ) : (
                          q.material || "\u2014"
                        )}
                      </td>
                      {/* Importe */}
                      <td className="px-[18px] py-[13px] text-right">
                        <div className="text-[13px] text-t1 font-mono -tracking-[0.02em]">
                          {q.total_ars ? `$${q.total_ars.toLocaleString("es-AR")}` : "\u2014"}
                        </div>
                        {q.total_usd ? (
                          <div className="text-[11px] text-t3 mt-px">USD {q.total_usd.toLocaleString()}</div>
                        ) : null}
                      </td>
                      {/* Estado */}
                      <td className="px-[18px] py-[13px] text-center">
                        <button
                          onClick={(e) => toggleStatus(e, q.id, q.status)}
                          title={STATUS_NEXT[q.status] ? `Cambiar a ${STATUS_LABEL[STATUS_NEXT[q.status]!]}` : "Estado final"}
                          className={clsx(
                            "inline-flex items-center gap-[5px] px-2 py-[3px] rounded-full text-[11px] font-medium border-none font-sans",
                            STATUS_NEXT[q.status] ? "cursor-pointer" : "cursor-default",
                            BADGE_CLASS[q.status],
                          )}
                        >
                          <span className="w-[5px] h-[5px] rounded-full bg-current" />
                          {STATUS_LABEL[q.status]}
                        </button>
                      </td>
                      {/* Fecha */}
                      <td className={clsx("px-[18px] py-[13px] text-[11px] text-right", isStale ? "text-amb" : "text-t3")}>
                        {format(new Date(q.created_at), "d MMM", { locale: es })}
                        {isStale && ` ·${Math.floor(daysOld)}d`}
                      </td>
                      {/* Archivos */}
                      <td className="px-[18px] py-[13px]">
                        <div className="flex gap-1 justify-end" onClick={e => e.stopPropagation()}>
                          {(q.drive_pdf_url || q.pdf_url) && <FileBtn href={q.drive_pdf_url || q.pdf_url!} emoji="📄" label="PDF" />}
                          {(q.drive_excel_url || q.excel_url) && <FileBtn href={q.drive_excel_url || q.excel_url!} emoji="📊" label="Excel" />}
                        </div>
                      </td>
                      {/* Duplicar material */}
                      <td className="px-1 py-[13px] w-10">
                        {q.material ? (
                          <button
                            onClick={(e) => askDerive(e, q.id, q.material || "", q.client_name)}
                            title="Duplicar con otro material"
                            className="w-7 h-7 rounded-md border border-b1 bg-transparent text-t3 cursor-pointer flex items-center justify-center text-[10px] font-medium transition-all hover:border-acc/50 hover:text-acc"
                          >
                            +M
                          </button>
                        ) : null}
                      </td>
                      {/* Delete */}
                      <td className="px-2.5 py-[13px] w-10">
                        <button
                          onClick={(e) => askDelete(e, q.id, q.client_name)}
                          title="Eliminar presupuesto"
                          className="w-7 h-7 rounded-md border border-b1 bg-transparent text-t3 cursor-pointer flex items-center justify-center text-xs transition-all hover:border-err/50 hover:text-err"
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filteredQuotes.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16 gap-2 text-t3">
                <span className="text-2xl">📋</span>
                <div className="text-[13px]">{quotes.length === 0 ? "No hay presupuestos todavía" : "Sin resultados para los filtros aplicados"}</div>
                {(search || dateFrom || dateTo || statusFilter !== "todos") && (
                  <button onClick={() => { setSearch(""); setDateFrom(""); setDateTo(""); setStatusFilter("todos"); }}
                    className="mt-1 text-xs text-acc bg-transparent border-none cursor-pointer font-sans hover:underline">
                    Limpiar filtros
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Mobile FAB — Nuevo presupuesto */}
      <button
        onClick={async () => {
          try { const id = await addQuote(); router.push(`/quote/${id}`); } catch {}
        }}
        className="md:hidden fixed bottom-6 right-4 z-40 bg-acc text-white border-none rounded-full px-5 py-3 text-[13px] font-medium font-sans cursor-pointer flex items-center gap-2 shadow-[0_8px_24px_rgba(79,143,255,.35)] active:scale-95 transition-transform"
        style={{ paddingBottom: `calc(12px + var(--safe-bottom, 0px))` }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        Nuevo presupuesto
      </button>

      {/* Delete modal */}
      {deleteTarget && (
        <div
          onClick={() => setDeleteTarget(null)}
          className="fixed inset-0 z-[999] bg-black/60 backdrop-blur-[4px] flex items-center justify-center"
        >
          <div
            onClick={e => e.stopPropagation()}
            className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-6 md:py-7 w-[calc(100vw-32px)] max-w-[380px] shadow-[0_20px_60px_rgba(0,0,0,.5)]"
          >
            <div className="text-[15px] font-medium text-t1 mb-2">Eliminar presupuesto</div>
            <div className="text-[13px] text-t2 leading-relaxed mb-6">
              ¿Eliminar el presupuesto de <strong className="text-t1">{deleteTarget.name}</strong>? Esta acción no se puede deshacer.
            </div>
            <div className="flex gap-2.5 justify-end">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition"
              >
                Cancelar
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleting}
                className={clsx(
                  "px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans border-none text-white transition",
                  deleting ? "bg-err/60 cursor-wait" : "bg-err cursor-pointer hover:bg-red-500",
                )}
              >
                {deleting ? "Eliminando..." : "Eliminar"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Status change modal */}
      {statusTarget && (
        <div
          onClick={() => setStatusTarget(null)}
          className="fixed inset-0 z-[999] bg-black/60 backdrop-blur-[4px] flex items-center justify-center"
        >
          <div
            onClick={e => e.stopPropagation()}
            className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-6 md:py-7 w-[calc(100vw-32px)] max-w-[380px] shadow-[0_20px_60px_rgba(0,0,0,.5)]"
          >
            <div className="text-[15px] font-medium text-t1 mb-2">Cambiar estado</div>
            <div className="text-[13px] text-t2 leading-relaxed mb-1.5">
              {`¿Cambiar de `}<strong className="text-t1">{STATUS_LABEL[statusTarget.current]}</strong>{` a `}<strong className="text-t1">{STATUS_LABEL[statusTarget.next]}</strong>?
            </div>
            {statusTarget.next === "sent" && (
              <div className="text-[12px] text-amb mb-4">Esta acci{"\u00F3"}n no se puede deshacer.</div>
            )}
            <div className={clsx("flex gap-2.5 justify-end", statusTarget.next !== "sent" && "mt-5")}>
              <button
                onClick={() => setStatusTarget(null)}
                className="px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition"
              >
                Cancelar
              </button>
              <button
                onClick={confirmStatusChange}
                disabled={changingStatus}
                className={clsx(
                  "px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans border-none text-white transition",
                  changingStatus ? "bg-acc/60 cursor-wait" : "bg-acc cursor-pointer hover:bg-blue-500",
                )}
              >
                {changingStatus ? "Cambiando..." : "Confirmar"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Derive material modal */}
      {deriveTarget && (
        <div
          onClick={closeDerive}
          className="fixed inset-0 z-[999] bg-black/60 backdrop-blur-[4px] flex items-center justify-center"
        >
          <div
            onClick={e => e.stopPropagation()}
            className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-6 md:py-7 w-[calc(100vw-32px)] max-w-[420px] shadow-[0_20px_60px_rgba(0,0,0,.5)]"
          >
            <div className="text-[15px] font-medium text-t1 mb-1">Duplicar con otro material</div>
            <div className="text-[12px] text-t3 mb-4">
              Cliente: <strong className="text-t2">{deriveTarget.client}</strong>
              {deriveTarget.material && <> {"\u00B7"} Material actual: <strong className="text-t2">{deriveTarget.material}</strong></>}
            </div>

            <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">Material nuevo</label>
            <input
              type="text"
              value={deriveMat}
              onChange={e => { setDeriveMat(e.target.value); setDeriveError(""); }}
              placeholder="Ej: Purastone Blanco Paloma"
              autoFocus
              onKeyDown={e => { if (e.key === "Enter" && !deriving) confirmDerive(); }}
              className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4 mb-3"
            />

            <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">Espesor mm <span className="text-t4 normal-case">(opcional)</span></label>
            <input
              type="number"
              value={deriveThickness}
              onChange={e => { setDeriveThickness(e.target.value); setDeriveError(""); }}
              placeholder="20"
              min={1}
              onKeyDown={e => { if (e.key === "Enter" && !deriving) confirmDerive(); }}
              className="w-24 px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4 mb-4"
            />

            {deriveError && (
              <div className="text-[12px] text-err mb-3 leading-relaxed">{deriveError}</div>
            )}

            <div className="flex gap-2.5 justify-end">
              <button
                onClick={closeDerive}
                className="px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition"
              >
                Cancelar
              </button>
              <button
                onClick={confirmDerive}
                disabled={deriving}
                className={clsx(
                  "px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans border-none text-white transition",
                  deriving ? "bg-acc/60 cursor-wait" : "bg-acc cursor-pointer hover:bg-blue-500",
                )}
              >
                {deriving ? "Creando..." : "Crear variante"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FileBtn({ href, emoji, label }: { href: string; emoji: string; label?: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={label}
      className={clsx(
        "rounded-[5px] border border-b1 bg-transparent flex items-center justify-center text-[11px] cursor-pointer no-underline text-t2 transition-all hover:border-b2 hover:bg-white/[0.06]",
        label ? "px-1.5 h-[26px] gap-1" : "w-[26px] h-[26px]",
      )}
    >
      {emoji}{label && <span className="text-[9px] font-medium">{label}</span>}
    </a>
  );
}
