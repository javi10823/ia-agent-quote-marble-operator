"use client";

import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  type Quote,
  type ResumenObraRecord,
  deriveMaterial,
  clientMatchCheck,
  mergeClient,
} from "@/lib/api";
import { useQuotes } from "@/lib/quotes-context";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import clsx from "clsx";
import { ResumenObraModal } from "@/components/quote/ResumenObraModal";
import { ResumenObraSuccessModal } from "@/components/quote/ResumenObraSuccessModal";
import { areFuzzySameClient } from "@/lib/clientMatch";

const STATUS_LABEL: Record<Quote["status"], string> = {
  draft: "Borrador", pending: "Pendiente", validated: "Validado", sent: "Enviado",
};

const BADGE_CLASS: Record<Quote["status"], string> = {
  draft:     "bg-amb-bg text-amb",
  pending:   "bg-acc-bg text-acc",
  validated: "bg-grn-bg text-grn",
  sent:      "bg-acc-bg text-acc",
};

// Color del dot inline (editorial — reemplaza al pill en las filas).
const STATUS_DOT: Record<Quote["status"], string> = {
  draft:     "var(--amb)",
  pending:   "#b299ff",
  validated: "var(--grn)",
  sent:      "var(--acc)",
};
const STATUS_TEXT: Record<Quote["status"], string> = {
  draft:     "text-amb",
  pending:   "text-[#b299ff]",
  validated: "text-grn",
  sent:      "text-acc",
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

  // ── Multi-select state for "Resumen de obra" ─────────────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectionMode, setSelectionMode] = useState(false); // mobile-only toggle
  const [resumenModalOpen, setResumenModalOpen] = useState(false);
  const [resumenSuccess, setResumenSuccess] =
    useState<{ record: ResumenObraRecord; affected: number } | null>(null);

  // Anchor quote for the current selection — used to fuzzy-match candidates.
  const selectionAnchor = useMemo(() => {
    if (selectedIds.size === 0) return null;
    return quotes.find((q) => selectedIds.has(q.id)) || null;
  }, [selectedIds, quotes]);

  const selectedQuotes = useMemo(
    () => quotes.filter((q) => selectedIds.has(q.id)),
    [quotes, selectedIds]
  );

  const isSelectable = useCallback(
    (q: Quote) => {
      if (q.status !== "validated") return false;
      if (
        selectionAnchor &&
        !areFuzzySameClient(q.client_name, selectionAnchor.client_name)
      )
        return false;
      return true;
    },
    [selectionAnchor]
  );

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  // Keyboard: Esc clears selection, ⌘A / Ctrl+A selects all validated quotes
  // of the currently active client (or all validated if nothing selected yet).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Do not hijack shortcuts when typing in form fields
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      const isTyping =
        tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable;
      if (isTyping) return;
      if (e.key === "Escape" && selectedIds.size > 0) {
        clearSelection();
      }
      // Pagination: Left/Right arrows
      if (e.key === "ArrowLeft") { setPage(p => Math.max(0, p - 1)); }
      if (e.key === "ArrowRight") { setPage(p => Math.min(totalPages - 1, p + 1)); }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a") {
        // Only act when there's a visible selection context
        if (selectionAnchor || !resumenModalOpen) {
          e.preventDefault();
          setSelectedIds((prev) => {
            const next = new Set(prev);
            for (const q of quotes) {
              if (q.status !== "validated") continue;
              if (
                selectionAnchor &&
                !areFuzzySameClient(q.client_name, selectionAnchor.client_name)
              )
                continue;
              next.add(q.id);
            }
            return next;
          });
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clearSelection, quotes, resumenModalOpen, selectionAnchor, selectedIds.size]);

  // Auto-exit mobile selection mode when selection is empty
  useEffect(() => {
    if (selectionMode && selectedIds.size === 0) {
      // keep mode on intentionally — user may be picking; don't auto-exit
    }
  }, [selectionMode, selectedIds.size]);

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

  // ── Paginación dinámica ─────────────────────────────────────────────────
  // Calcula cuántas filas caben según viewport, recalcula en resize.
  const listRef = useRef<HTMLDivElement>(null);
  const [pageSize, setPageSize] = useState(8);
  const [page, setPage] = useState(0);

  useEffect(() => {
    function calc() {
      // Row heights: desktop ~57px, mobile ~72px
      const isMobile = window.innerWidth < 768;
      const rowH = isMobile ? 72 : 57;
      // Reservar espacio para header, tabs, filter bar, pagination bar, etc.
      const reserved = isMobile ? 280 : 340;
      const available = window.innerHeight - reserved;
      const size = Math.max(3, Math.min(50, Math.floor(available / rowH)));
      setPageSize(size);
    }
    calc();
    let timer: ReturnType<typeof setTimeout>;
    function onResize() {
      clearTimeout(timer);
      timer = setTimeout(calc, 200);
    }
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); clearTimeout(timer); };
  }, []);

  // Reset page cuando cambian filtros
  useEffect(() => { setPage(0); }, [statusFilter, search, dateFrom, dateTo]);

  // Clamp page si datos cambian (ej: quote eliminado)
  const totalPages = Math.max(1, Math.ceil(filteredQuotes.length / pageSize));
  useEffect(() => {
    if (page >= totalPages) setPage(Math.max(0, totalPages - 1));
  }, [page, totalPages]);

  const pageQuotes = useMemo(
    () => filteredQuotes.slice(page * pageSize, (page + 1) * pageSize),
    [filteredQuotes, page, pageSize]
  );

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

  // ── Formatters — matching dash-airy.jsx exact ──────────────────────────
  // Mes/año en eyebrow "ABRIL 2029". Se calcula solo del lado client (en
  // mount) para evitar hydration mismatch — SSR y client pueden tener
  // timezones distintos y producir meses distintos en el boundary.
  const [mesHeader, setMesHeader] = useState("");
  useEffect(() => {
    const d = new Date();
    const mes = d.toLocaleDateString("es-AR", { month: "long" }).toUpperCase();
    setMesHeader(`${mes} ${d.getFullYear()}`);
  }, []);
  const fmtARS = (n: number | null | undefined) => n == null ? "\u2014" : `$\u00A0${n.toLocaleString("es-AR")}`;
  const fmtUSD = (n: number | null | undefined) => n == null ? null : `USD\u00A0${n.toLocaleString("en-US")}`;
  const fmtDia = (iso: string) => format(new Date(iso), "d MMM", { locale: es });
  const toTitleCase = (s: string | null | undefined) => {
    if (!s) return "";
    return s.toLowerCase().replace(/\b[\wáéíóúñ]/g, (ch) => ch.toUpperCase());
  };

  const handleExport = () => {
    const rows = [["Cliente","Proyecto","Material","ARS","USD","Estado","Fuente","Fecha"]];
    filteredQuotes.forEach(q => rows.push([
      q.client_name, q.project, q.material || "", String(q.total_ars || ""), String(q.total_usd || ""),
      q.status, q.source || "operator", new Date(q.created_at).toLocaleDateString("es-AR"),
    ]));
    const csv = rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `presupuestos-${new Date().toISOString().slice(0,10)}.csv`; a.click();
  };

  const handleNew = async () => {
    try { const id = await addQuote(); router.push(`/quote/${id}`); } catch { /* toast shown by context */ }
  };

  return (
    <div className="flex flex-col h-full" style={{ background: "var(--bg)" }}>
      {/* Header — exact match con AiryHeader. Padding 36px 40px 22px, eyebrow
          mono uppercase size 11 weight 600 letterSpacing 1px, título Fraunces
          italic 40px tracking -0.8, botones Exportar (height 32) y Nuevo
          presupuesto (height 36, color bg sobre accent). */}
      <div
        className="hidden md:flex items-end shrink-0"
        style={{ padding: "36px 40px 22px", gap: 16 }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            className="font-mono uppercase"
            style={{
              fontSize: 11, color: "var(--t3)",
              letterSpacing: "1px", marginBottom: 6, fontWeight: 600,
            }}
          >
            {mesHeader} · {quotes.length} registros
            {quotes.filter(q => !q.is_read).length > 0 && (
              <> · <span style={{ color: "var(--acc)" }}>{quotes.filter(q => !q.is_read).length} sin leer</span></>
            )}
          </div>
          <h1
            className="font-serif italic"
            style={{
              margin: 0, fontStyle: "italic", fontWeight: 400,
              fontSize: 40, color: "var(--t1)",
              letterSpacing: "-0.8px", lineHeight: 1.1,
            }}
          >
            Presupuestos
          </h1>
        </div>
        <button
          onClick={handleExport}
          className="inline-flex items-center cursor-pointer"
          style={{
            height: 32, padding: "0 12px", borderRadius: 8,
            border: "1px solid var(--b1)", background: "transparent",
            color: "var(--t2)", fontSize: 12.5,
            gap: 6,
          }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 4v12m0 0l-5-5m5 5l5-5M4 20h16"/></svg>
          <span>Exportar</span>
        </button>
        <button
          onClick={handleNew}
          className="inline-flex items-center cursor-pointer"
          style={{
            height: 36, padding: "0 16px", borderRadius: 8, border: "none",
            background: "var(--acc)", color: "var(--bg)",
            gap: 7, fontSize: 13.5, fontWeight: 600,
          }}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>Nuevo presupuesto</span>
        </button>
      </div>
      {/* Mobile header — compacto */}
      <div className="md:hidden flex items-end justify-between shrink-0" style={{ padding: "20px 16px 14px" }}>
        <div className="min-w-0">
          <div className="font-mono uppercase" style={{ fontSize: 10, color: "var(--t3)", letterSpacing: "1px", marginBottom: 4, fontWeight: 600 }}>
            {mesHeader} · {quotes.length}
          </div>
          <h1 className="font-serif italic" style={{ fontSize: 28, color: "var(--t1)", letterSpacing: "-0.5px", lineHeight: 1.1, fontWeight: 400 }}>Presupuestos</h1>
        </div>
        <button onClick={handleNew} className="inline-flex items-center cursor-pointer" style={{ height: 32, padding: "0 12px", borderRadius: 8, border: "none", background: "var(--acc)", color: "var(--bg)", gap: 5, fontSize: 12.5, fontWeight: 600 }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Nuevo
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Stale drafts banner — minimal inline, no border lg rounded */}
        {staleDrafts.length > 0 && (
          <div className="flex items-center gap-2.5 mx-4 md:mx-10 mt-2 bg-amb/[0.06] border border-amb/[0.14] rounded-md px-4 py-2.5 text-[12px] text-amb">
            <div className="w-1.5 h-1.5 rounded-full bg-amb shrink-0" />
            <span>
              <strong className="font-medium">{staleDrafts.length} {staleDrafts.length === 1 ? "borrador lleva" : "borradores llevan"} más de 5 días sin acción</strong>
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
          <div className="bg-transparent">
            {/* Filter strip — exact match AiryFilters: padding 0 40px 20px,
                gap 14 entre pills. Activo: border-bottom 1.5px accent.
                Date range: mono text "01 abr — 30 abr" con calendar icon
                (sin inputs visibles — click reveals). Search: inline con
                border-bottom sutil, placeholder "Buscar…". */}
            <div
              className="hidden md:flex items-center"
              style={{ padding: "0 40px 20px", gap: 16, borderBottom: "1px solid var(--b1)" }}
            >
              <div className="flex items-center" style={{ gap: 14 }}>
                {([
                  { key: "todos", label: "Todos", dot: null as string | null },
                  { key: "draft", label: "Borrador", dot: "var(--amb)" },
                  { key: "pending", label: "Pendiente", dot: "#b299ff" },
                  { key: "validated", label: "Validado", dot: "var(--grn)" },
                  { key: "sent", label: "Enviado", dot: "var(--acc)" },
                  { key: "web", label: "Web", dot: "#b48fe0" },
                ]).map(f => {
                  const active = statusFilter === f.key;
                  return (
                    <button
                      key={f.key}
                      onClick={() => setStatusFilter(f.key)}
                      className="inline-flex items-center bg-transparent cursor-pointer"
                      style={{
                        gap: 7,
                        fontSize: 13,
                        color: active ? "var(--t1)" : "var(--t2)",
                        fontWeight: active ? 600 : 400,
                        paddingBottom: 2,
                        borderBottom: active ? "1.5px solid var(--acc)" : "1.5px solid transparent",
                        border: "none",
                        borderBottomWidth: "1.5px",
                        borderBottomStyle: "solid",
                        borderBottomColor: active ? "var(--acc)" : "transparent",
                      }}
                    >
                      {f.dot && (
                        <span
                          style={{
                            width: 7, height: 7, borderRadius: 999,
                            background: f.dot, display: "inline-block",
                          }}
                        />
                      )}
                      <span>{f.label}</span>
                      <span
                        className="font-mono"
                        style={{ fontSize: 11, color: "var(--t3)", fontVariantNumeric: "tabular-nums" }}
                      >
                        {statusCounts[f.key as keyof typeof statusCounts]}
                      </span>
                    </button>
                  );
                })}
              </div>
              <div style={{ flex: 1 }} />
              {/* Date range display + input overlay */}
              <DateRangeField dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo} />
              {/* Search — inline minimal con border-bottom sutil */}
              <div
                className="inline-flex items-center"
                style={{
                  gap: 8, padding: "6px 0",
                  borderBottom: "1px solid var(--b1)",
                  fontSize: 13, color: "var(--t3)",
                  minWidth: 200,
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Buscar…"
                  className="bg-transparent outline-none"
                  style={{ fontSize: 13, color: "var(--t1)", width: "100%", border: "none" }}
                />
                {search && (
                  <button onClick={() => setSearch("")} className="bg-transparent border-none cursor-pointer p-0" style={{ color: "var(--t3)", fontSize: 11 }}>✕</button>
                )}
              </div>
            </div>
            {/* Mobile — filter pills scroll + search */}
            <div className="md:hidden flex items-center overflow-x-auto" style={{ padding: "0 16px 14px", gap: 16 }}>
              {([
                { key: "todos", label: "Todos", dot: null as string | null },
                { key: "draft", label: "Borrador", dot: "var(--amb)" },
                { key: "pending", label: "Pendiente", dot: "#b299ff" },
                { key: "validated", label: "Validado", dot: "var(--grn)" },
                { key: "sent", label: "Enviado", dot: "var(--acc)" },
                { key: "web", label: "Web", dot: "#b48fe0" },
              ]).map(f => {
                const active = statusFilter === f.key;
                return (
                  <button
                    key={f.key}
                    onClick={() => setStatusFilter(f.key)}
                    className="inline-flex items-center bg-transparent border-none cursor-pointer shrink-0"
                    style={{
                      gap: 6,
                      fontSize: 12.5,
                      color: active ? "var(--t1)" : "var(--t2)",
                      fontWeight: active ? 600 : 400,
                      paddingBottom: 2,
                      borderBottomWidth: "1.5px",
                      borderBottomStyle: "solid",
                      borderBottomColor: active ? "var(--acc)" : "transparent",
                    }}
                  >
                    {f.dot && <span style={{ width: 7, height: 7, borderRadius: 999, background: f.dot, display: "inline-block" }} />}
                    <span>{f.label}</span>
                    <span className="font-mono" style={{ fontSize: 11, color: "var(--t3)" }}>{statusCounts[f.key as keyof typeof statusCounts]}</span>
                  </button>
                );
              })}
            </div>

            {/* Mobile — Selection mode toggle */}
            <div className="md:hidden flex items-center justify-between px-3 py-2 border-b border-b1 bg-s2">
              {selectionMode ? (
                <>
                  <button
                    onClick={() => { clearSelection(); setSelectionMode(false); }}
                    className="text-[12px] text-t3 bg-transparent border-none cursor-pointer p-0"
                  >
                    ✕ Cancelar
                  </button>
                  <span className="text-[12px] font-semibold text-t1">
                    {selectedIds.size} seleccionado{selectedIds.size === 1 ? "" : "s"}
                  </span>
                  <button
                    onClick={() => {
                      setSelectedIds(prev => {
                        const next = new Set(prev);
                        for (const q of filteredQuotes) {
                          if (isSelectable(q) || next.has(q.id)) next.add(q.id);
                        }
                        return next;
                      });
                    }}
                    className="text-[12px] text-acc bg-transparent border-none cursor-pointer p-0"
                  >
                    Todos
                  </button>
                </>
              ) : (
                <button
                  onClick={() => setSelectionMode(true)}
                  className="text-[12px] text-t2 bg-transparent border border-b1 rounded-md px-3 py-1 cursor-pointer"
                >
                  ☑ Seleccionar
                </button>
              )}
            </div>

            {/* Mobile Cards — editorial: cliente serif, importe serif, status dot+text */}
            <div className="md:hidden divide-y divide-b1/50">
              {pageQuotes.map(q => {
                const isUnread = !q.is_read;
                const isChecked = selectedIds.has(q.id);
                const selectable = isSelectable(q);
                const checkboxDisabled = !isChecked && !selectable;
                return (
                  <div
                    key={q.id}
                    onClick={() => {
                      if (selectionMode) {
                        if (!checkboxDisabled) toggleSelect(q.id);
                      } else {
                        setSelectedId(q.id);
                        router.push(`/quote/${q.id}`);
                      }
                    }}
                    className={clsx(
                      "flex items-start gap-3 px-5 py-5 cursor-pointer active:bg-white/[0.03] transition",
                      isChecked && "bg-acc/[0.08]",
                      !isChecked && isUnread && "bg-acc/[0.03]",
                      selectionMode && checkboxDisabled && "opacity-45"
                    )}
                  >
                    {selectionMode && (
                      <input
                        type="checkbox"
                        checked={isChecked}
                        disabled={checkboxDisabled}
                        onChange={() => toggleSelect(q.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="w-4 h-4 accent-acc shrink-0 mt-1"
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline gap-2">
                        {isUnread && <span className="w-[6px] h-[6px] rounded-full bg-acc shrink-0" />}
                        <span className="font-serif italic text-[17px] text-t1 font-medium -tracking-[0.01em] truncate leading-tight">{q.client_name || "Sin nombre"}</span>
                        {q.source === "web" && <span className="text-[9px] font-semibold font-mono px-1.5 py-[1px] rounded border border-[#b48fe0]/30 text-[#b48fe0] tracking-wider not-italic">WEB</span>}
                      </div>
                      <div className="text-[12px] text-t3 truncate mt-1 font-sans">{q.material || q.project || "\u2014"}</div>
                      <div className="flex items-center gap-3 mt-2">
                        <span className={clsx("inline-flex items-center gap-1.5 text-[12px] font-sans", STATUS_TEXT[q.status])}>
                          <span className="w-[6px] h-[6px] rounded-full shrink-0" style={{ background: STATUS_DOT[q.status] }} />
                          {STATUS_LABEL[q.status]}
                        </span>
                        <span className="text-[11px] text-t4 font-mono tabular-nums">
                          {format(new Date(q.created_at), "d MMM", { locale: es })}
                        </span>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="font-serif text-[16px] text-t1 -tracking-[0.01em] leading-none whitespace-nowrap">{q.total_ars ? `$\u00A0${q.total_ars.toLocaleString("es-AR")}` : "\u2014"}</div>
                      {q.total_usd ? <div className="text-[10px] text-t3 mt-1.5 font-mono">USD {q.total_usd.toLocaleString()}</div> : null}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Desktop rows — CSS Grid exacto como AiryRow.
                gridTemplateColumns "2fr 2.5fr 1fr 1.2fr 0.9fr 1.3fr 28px"
                gap 20, padding 20px 4px, border-bottom b1. */}
            <div className="hidden md:block" style={{ padding: "4px 40px 20px" }}>
              {pageQuotes.map(q => {
                const daysOld = (Date.now() - new Date(q.created_at).getTime()) / 86400000;
                const isStale = q.status === "draft" && daysOld > 5;
                const isUnread = !q.is_read;
                const isSelected = selectedId === q.id;
                const isChecked = selectedIds.has(q.id);
                const isBuilding = q.quote_kind === "building_parent" || q.is_building;
                return (
                  <div
                    key={q.id}
                    onClick={() => { setSelectedId(q.id); router.push(`/quote/${q.id}`); }}
                    className={clsx(
                      "grid items-center cursor-pointer transition-colors",
                      isChecked ? "bg-acc/[0.08]"
                        : isSelected ? "bg-acc/[0.05]"
                        : isUnread ? "bg-acc/[0.03] hover:bg-acc/[0.05]"
                        : "hover:bg-white/[0.02]",
                    )}
                    style={{
                      gridTemplateColumns: "2fr 2.5fr 1fr 1.2fr 0.9fr 1.3fr 28px",
                      gap: 20,
                      padding: "20px 4px",
                      borderBottom: "1px solid var(--b1)",
                    }}
                  >
                    {/* Cliente + sublabel */}
                    <div style={{ minWidth: 0 }}>
                      <div
                        className="font-serif italic truncate"
                        style={{
                          fontSize: 17, fontWeight: 500, color: "var(--t1)",
                          letterSpacing: "-0.2px", lineHeight: 1.15,
                        }}
                      >
                        {q.client_name || "Sin nombre"}
                      </div>
                      <div
                        className="truncate"
                        style={{ fontSize: 11.5, color: "var(--t3)", marginTop: 2 }}
                      >
                        {q.project}
                      </div>
                    </div>

                    {/* Material con chip OBRA */}
                    <div className="flex items-center" style={{ gap: 10, minWidth: 0 }}>
                      {isBuilding && (
                        <span
                          className="font-mono shrink-0"
                          style={{
                            fontSize: 9.5, fontWeight: 700, letterSpacing: "0.8px",
                            padding: "3px 6px", borderRadius: 3,
                            background: "transparent",
                            border: "1px solid var(--acc)",
                            color: "var(--acc)",
                            lineHeight: 1,
                          }}
                        >
                          OBRA
                        </span>
                      )}
                      <span
                        className="truncate"
                        style={{ fontSize: 13, color: "var(--t2)" }}
                      >
                        {toTitleCase(q.material) || "\u2014"}
                      </span>
                    </div>

                    {/* Importe ARS + USD */}
                    <div className="text-right" style={{ fontVariantNumeric: "tabular-nums" }}>
                      <div
                        className="font-serif"
                        style={{
                          fontSize: 14.5, fontWeight: 500, color: "var(--t1)",
                          letterSpacing: "-0.1px",
                        }}
                      >
                        {fmtARS(q.total_ars)}
                      </div>
                      {q.total_usd != null && (
                        <div
                          className="font-mono"
                          style={{ fontSize: 10.5, color: "var(--t3)", marginTop: 1 }}
                        >
                          {fmtUSD(q.total_usd)}
                        </div>
                      )}
                    </div>

                    {/* Estado — dot + texto */}
                    <button
                      onClick={(e) => toggleStatus(e, q.id, q.status)}
                      title={STATUS_NEXT[q.status] ? `Cambiar a ${STATUS_LABEL[STATUS_NEXT[q.status]!]}` : "Estado final"}
                      className={clsx(
                        "inline-flex items-center bg-transparent border-none p-0",
                        STATUS_NEXT[q.status] ? "cursor-pointer" : "cursor-default",
                        STATUS_TEXT[q.status],
                      )}
                      style={{ gap: 8, fontSize: 12.5 }}
                    >
                      <span
                        style={{
                          width: 7, height: 7, borderRadius: 999,
                          background: STATUS_DOT[q.status], display: "inline-block",
                        }}
                      />
                      {STATUS_LABEL[q.status]}
                    </button>

                    {/* Fecha */}
                    <div
                      className={clsx("font-mono", isStale ? "text-amb" : "")}
                      style={{
                        fontSize: 12.5,
                        color: isStale ? undefined : "var(--t3)",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {format(new Date(q.created_at), "d MMM", { locale: es })}
                    </div>

                    {/* Archivos */}
                    <div className="flex flex-wrap" style={{ gap: 5 }}>
                      <FileCell q={q} />
                    </div>

                    {/* Menu 3-dots */}
                    <RowMenu
                      onDerive={q.material ? (e) => askDerive(e, q.id, q.material || "", q.client_name) : undefined}
                      onDelete={(e) => askDelete(e, q.id, q.client_name)}
                    />
                  </div>
                );
              })}
            </div>
            {/* Pagination — exact match AiryFooter: padding 16px 40px 20px,
                "1–8 de 18" | flex-1 | "Página 1 / 3" | chevL ghost | chevR accent. */}
            {filteredQuotes.length > 0 && totalPages > 1 && (
              <div
                className="flex items-center"
                style={{ padding: "16px 40px 20px", gap: 12, fontSize: 12, color: "var(--t2)" }}
              >
                <span className="font-mono" style={{ fontVariantNumeric: "tabular-nums" }}>
                  {page * pageSize + 1}–{Math.min((page + 1) * pageSize, filteredQuotes.length)} de {filteredQuotes.length}
                </span>
                <div style={{ flex: 1 }} />
                <span className="font-mono" style={{ color: "var(--t3)", fontVariantNumeric: "tabular-nums" }}>
                  Página {page + 1} / {totalPages}
                </span>
                <button
                  disabled={page === 0}
                  onClick={() => setPage(p => p - 1)}
                  className="grid place-items-center cursor-pointer disabled:opacity-30 disabled:cursor-default"
                  style={{
                    height: 28, width: 28, borderRadius: 6,
                    border: "1px solid var(--b1)", background: "transparent",
                    color: "var(--t2)",
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
                </button>
                <button
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage(p => p + 1)}
                  className="grid place-items-center cursor-pointer disabled:opacity-30 disabled:cursor-default"
                  style={{
                    height: 28, width: 28, borderRadius: 6,
                    border: "1px solid var(--acc)",
                    background: "var(--acc)",
                    color: "var(--bg)",
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                </button>
              </div>
            )}

            {filteredQuotes.length === 0 && (
              <div className="flex flex-col items-center justify-center py-24 gap-3 text-t3">
                <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" className="text-acc/60">
                  <path d="M3 14l2-8h14l2 8" strokeLinejoin="round"/>
                  <path d="M3 14h6l1 2h4l1-2h6v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4z" strokeLinejoin="round"/>
                </svg>
                <div className="font-serif italic text-[18px] text-t2 -tracking-[0.01em]">
                  {quotes.length === 0 ? "Sin presupuestos todavía" : "Sin resultados para los filtros aplicados"}
                </div>
                <div className="text-[12px] text-t4 font-sans max-w-[360px] text-center">
                  {quotes.length === 0
                    ? "Subí un plano o dictá un enunciado y Valentina arma el primero."
                    : "Probá cambiar el filtro o limpiar la búsqueda."}
                </div>
                {(search || dateFrom || dateTo || statusFilter !== "todos") && (
                  <button onClick={() => { setSearch(""); setDateFrom(""); setDateTo(""); setStatusFilter("todos"); }}
                    className="mt-2 text-xs text-acc bg-transparent border-none cursor-pointer font-sans hover:underline">
                    Limpiar filtros
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Selection action bar (desktop + tablet) — sticky bottom */}
      {selectedIds.size > 0 && (
        <div
          className="hidden md:flex sticky bottom-0 left-0 right-0 z-30 items-center justify-between px-5 py-3 border-t border-b2 bg-s2/95 backdrop-blur-[8px]"
        >
          <div className="flex items-center gap-3 text-[13px]">
            <span className="px-2 py-[2px] rounded-full text-[11px] font-medium bg-grn-bg text-grn">
              {selectedIds.size} seleccionado{selectedIds.size === 1 ? "" : "s"}
            </span>
            <span className="text-t3">·</span>
            <span className="text-t3">
              {(() => {
                const names = Array.from(
                  new Set(
                    selectedQuotes
                      .map((q) => q.client_name)
                      .filter(Boolean) as string[]
                  )
                );
                if (names.length === 0) return "—";
                if (names.length === 1)
                  return (
                    <>
                      Cliente:{" "}
                      <span className="text-t1">{names[0]}</span>
                    </>
                  );
                return (
                  <>
                    Clientes (fuzzy):{" "}
                    <span className="text-t1">{names.join(" · ")}</span>
                  </>
                );
              })()}
            </span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={clearSelection}
              className="px-3 py-1.5 rounded-md text-xs font-medium font-sans cursor-pointer border border-b1 bg-transparent text-t2 hover:border-b2 hover:text-t1 transition"
            >
              Limpiar
            </button>
            <button
              onClick={() => setResumenModalOpen(true)}
              className="px-4 py-1.5 rounded-md text-xs font-medium font-sans border-none bg-acc text-white cursor-pointer hover:bg-blue-500 transition inline-flex items-center gap-1.5"
            >
              📑 Generar resumen de obra
            </button>
          </div>
        </div>
      )}

      {/* Mobile — FAB resumen when selection active, else "Nuevo presupuesto" */}
      {selectionMode && selectedIds.size > 0 ? (
        <button
          onClick={() => setResumenModalOpen(true)}
          className="md:hidden fixed bottom-6 left-4 right-4 z-40 bg-acc text-white border-none rounded-full px-5 py-3 text-[13px] font-medium font-sans cursor-pointer flex items-center justify-center gap-2 shadow-[0_8px_24px_rgba(95,125,160,0.35)] active:scale-95 transition-transform"
          style={{ paddingBottom: `calc(12px + var(--safe-bottom, 0px))` }}
        >
          📑 Generar resumen ({selectedIds.size})
        </button>
      ) : (
        <button
          onClick={async () => {
            try { const id = await addQuote(); router.push(`/quote/${id}`); } catch {}
          }}
          className="md:hidden fixed bottom-6 right-4 z-40 bg-acc text-white border-none rounded-full px-5 py-3 text-[13px] font-medium font-sans cursor-pointer flex items-center gap-2 shadow-[0_8px_24px_rgba(95,125,160,0.35)] active:scale-95 transition-transform"
          style={{ paddingBottom: `calc(12px + var(--safe-bottom, 0px))` }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Nuevo presupuesto
        </button>
      )}

      {/* Resumen de obra — Confirmation + Success modals */}
      <ResumenObraModal
        open={resumenModalOpen}
        quotes={selectedQuotes}
        onClose={() => setResumenModalOpen(false)}
        onSuccess={(record, affectedIds) => {
          setResumenModalOpen(false);
          setResumenSuccess({ record, affected: affectedIds.length });
          clearSelection();
          setSelectionMode(false);
          refresh();
        }}
        onClientsMerged={() => {
          // Rename happened server-side; refresh so the new canonical name
          // shows up in the list and the action bar updates.
          refresh();
        }}
      />
      <ResumenObraSuccessModal
        open={!!resumenSuccess}
        record={resumenSuccess?.record || null}
        affectedCount={resumenSuccess?.affected || 0}
        onClose={() => setResumenSuccess(null)}
      />

      {/* Delete modal */}
      {deleteTarget && (
        <div
          onClick={() => setDeleteTarget(null)}
          className="fixed inset-0 z-[999] bg-black/60 backdrop-blur-[4px] flex items-center justify-center"
        >
          <div
            onClick={e => e.stopPropagation()}
            className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-7 md:py-7 w-[calc(100vw-32px)] max-w-[380px] shadow-[0_20px_60px_rgba(0,0,0,.5)]"
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
            className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-7 md:py-7 w-[calc(100vw-32px)] max-w-[380px] shadow-[0_20px_60px_rgba(0,0,0,.5)]"
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
            className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-7 md:py-7 w-[calc(100vw-32px)] max-w-[420px] shadow-[0_20px_60px_rgba(0,0,0,.5)]"
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
      className="inline-flex items-center cursor-pointer no-underline"
      style={{
        gap: 4, height: 24, padding: label ? "0 8px 0 6px" : 0,
        width: label ? undefined : 24,
        borderRadius: 4, border: "1px solid var(--b1)",
        background: "transparent", color: "var(--t2)",
        fontSize: 11,
      }}
    >
      <span style={{ fontSize: 11, lineHeight: 1 }}>{emoji}</span>
      {label && <span style={{ fontSize: 10.5, fontWeight: 500 }}>{label}</span>}
    </a>
  );
}

// ── FileCell — PDF + Excel + "+N" para archivos extra ──────────────────────
function FileCell({ q }: { q: any }) {
  const files: { href: string; label: string; emoji: string }[] = [];
  if (q.drive_pdf_url || q.pdf_url) files.push({ href: q.drive_pdf_url || q.pdf_url, label: "PDF", emoji: "📄" });
  if (q.drive_excel_url || q.excel_url) files.push({ href: q.drive_excel_url || q.excel_url, label: "Excel", emoji: "📊" });
  if (q.resumen_obra_pdf_url) files.push({ href: q.resumen_obra_pdf_url, label: "Resumen", emoji: "📑" });
  if (q.condiciones_pdf_url) files.push({ href: q.condiciones_pdf_url, label: "Condiciones", emoji: "📋" });

  if (files.length === 0) return <div className="flex justify-end"><span className="text-t4 text-[12px] font-mono">—</span></div>;

  // Primeros 2 visibles, resto colapsado en chip "+N"
  const visible = files.slice(0, 2);
  const extra = files.length - visible.length;
  return (
    <div className="flex gap-1.5 justify-end" onClick={e => e.stopPropagation()}>
      {visible.map((f) => <FileBtn key={f.label} href={f.href} emoji={f.emoji} label={f.label} />)}
      {extra > 0 && (
        <span
          title={files.slice(2).map(f => f.label).join(" · ")}
          className="h-[26px] px-2 rounded-[5px] border border-b1 bg-transparent flex items-center justify-center text-[11px] font-medium font-mono text-t3"
        >
          +{extra}
        </span>
      )}
    </div>
  );
}

// ── RowMenu — 3-dot popover siempre visible ──────────────────────────────
function RowMenu({ onDerive, onDelete }: {
  onDerive?: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div className="relative flex justify-end" ref={ref} onClick={e => e.stopPropagation()}>
      <button
        onClick={(e) => { e.stopPropagation(); setOpen(v => !v); }}
        title="Acciones"
        aria-label="Acciones"
        className="w-7 h-7 rounded-md border border-b1 bg-transparent text-t3 cursor-pointer flex items-center justify-center transition-all hover:border-b2 hover:text-t1"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="12" cy="5" r="1.4" />
          <circle cx="12" cy="12" r="1.4" />
          <circle cx="12" cy="19" r="1.4" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1.5 z-50 min-w-[168px] bg-s2 border border-b2 rounded-lg shadow-[0_14px_40px_rgba(0,0,0,0.5)] py-1 animate-[fadeUp_0.12s_ease]">
          {onDerive && (
            <button
              onClick={(e) => { setOpen(false); onDerive(e); }}
              className="w-full text-left px-3.5 py-2 text-[12.5px] font-sans text-t2 bg-transparent border-none cursor-pointer hover:bg-white/[0.04] hover:text-t1 transition flex items-center gap-2.5"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/></svg>
              Duplicar con otro material
            </button>
          )}
          <button
            onClick={(e) => { setOpen(false); onDelete(e); }}
            className="w-full text-left px-3.5 py-2 text-[12.5px] font-sans text-err bg-transparent border-none cursor-pointer hover:bg-err/10 transition flex items-center gap-2.5"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M6 6l1 14a2 2 0 002 2h6a2 2 0 002-2l1-14"/></svg>
            Eliminar
          </button>
        </div>
      )}
    </div>
  );
}

// ── DateRangeField — display "01 abr — 30 abr" mono con click reveal ───
function DateRangeField({ dateFrom, setDateFrom, dateTo, setDateTo }: {
  dateFrom: string; setDateFrom: (v: string) => void;
  dateTo: string; setDateTo: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const label = (() => {
    if (!dateFrom && !dateTo) return "Todo el mes";
    const fmt = (d: string) => d ? format(new Date(d), "d MMM", { locale: es }) : "…";
    return `${fmt(dateFrom)} — ${fmt(dateTo)}`;
  })();
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="inline-flex items-center cursor-pointer bg-transparent border-none"
        style={{ gap: 8, fontSize: 12.5, color: "var(--t2)", fontFamily: "var(--font-mono)" }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" style={{ color: "var(--t3)" }}>
          <rect x="3" y="5" width="18" height="16" rx="2"/>
          <path d="M3 10h18M8 3v4M16 3v4" strokeLinecap="round"/>
        </svg>
        <span>{label}</span>
      </button>
      {open && (
        <div
          className="absolute top-full right-0 z-50 mt-2 animate-[fadeUp_0.12s_ease]"
          style={{
            background: "var(--s2)", border: "1px solid var(--b2)",
            borderRadius: 10, padding: 14,
            boxShadow: "0 14px 40px rgba(0,0,0,0.5)",
            display: "flex", gap: 10, alignItems: "center",
          }}
          onMouseLeave={() => setOpen(false)}
        >
          <input
            type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="[color-scheme:dark]"
            style={{
              background: "var(--bg)", border: "1px solid var(--b1)",
              borderRadius: 6, padding: "6px 10px",
              color: "var(--t1)", fontSize: 12, fontFamily: "var(--font-mono)",
              outline: "none",
            }}
          />
          <span style={{ color: "var(--t3)", fontSize: 12 }}>—</span>
          <input
            type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="[color-scheme:dark]"
            style={{
              background: "var(--bg)", border: "1px solid var(--b1)",
              borderRadius: 6, padding: "6px 10px",
              color: "var(--t1)", fontSize: 12, fontFamily: "var(--font-mono)",
              outline: "none",
            }}
          />
          {(dateFrom || dateTo) && (
            <button
              onClick={() => { setDateFrom(""); setDateTo(""); }}
              className="bg-transparent border-none cursor-pointer"
              style={{ color: "var(--t3)", fontSize: 11 }}
            >Limpiar</button>
          )}
        </div>
      )}
    </div>
  );
}
