"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import clsx from "clsx";
import { importPreview, importApply, type ImportPreviewResult, type ImportCatalogDiff } from "@/lib/api";

interface Props {
  onDone: () => void;  // Called after successful import — parent should refresh
  onClose: () => void;
}

type Step = "upload" | "detect" | "preview" | "importing" | "done";

const FORMAT_LABELS: Record<string, string> = {
  dux_materials_usd: "Dux Materiales (USD)",
  dux_servicios_ars: "Dux Servicios / Flete (ARS)",
  csv_generic: "CSV genérico",
};

export default function ImportModal({ onDone, onClose }: Props) {
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResult | null>(null);
  const [selectedCatalogs, setSelectedCatalogs] = useState<Set<string>>(new Set());
  const [includeNew, setIncludeNew] = useState(true);
  const [activeTab, setActiveTab] = useState<string>("");
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);
  const [applyResult, setApplyResult] = useState<Record<string, any> | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const dragCounter = useRef(0);
  const fileRef = useRef<HTMLInputElement>(null);

  // Escape to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !importing) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, importing]);

  // ── Upload + preview ──────────────────────────────────────────────────────

  const handleFile = useCallback(async (f: File) => {
    setFile(f);
    setError("");
    setStep("detect");

    try {
      const result = await importPreview(f);
      setPreview(result);

      // Auto-select catalogs that have changes
      const cats = new Set<string>();
      for (const [name, diff] of Object.entries(result.catalogs)) {
        if (diff.updated.length > 0 || diff.new.length > 0) {
          cats.add(name);
        }
      }
      setSelectedCatalogs(cats);

      // Set first tab
      const catNames = Object.keys(result.catalogs);
      setActiveTab(catNames[0] || "_unmatched");
      setStep("preview");
    } catch (err: any) {
      setError(err.message || "Error al analizar archivo");
      setStep("upload");
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current = 0;
    setDragActive(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }, [handleFile]);

  const handleFiles = useCallback((files: FileList | null) => {
    if (files?.[0]) handleFile(files[0]);
  }, [handleFile]);

  // ── Apply ─────────────────────────────────────────────────────────────────

  const handleApply = useCallback(async () => {
    if (!file || !preview || selectedCatalogs.size === 0) return;
    setImporting(true);
    setError("");
    setStep("importing");

    try {
      const result = await importApply(file, Array.from(selectedCatalogs), includeNew, file.name);
      setApplyResult(result.results);
      setStep("done");
      onDone();
    } catch (err: any) {
      setError(err.message || "Error al importar");
      setStep("preview");  // Go back to preview on error
    } finally {
      setImporting(false);
    }
  }, [file, preview, selectedCatalogs, includeNew, onDone]);

  // ── Toggle catalog ────────────────────────────────────────────────────────

  const toggleCatalog = (name: string) => {
    setSelectedCatalogs(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  // ── Render helpers ────────────────────────────────────────────────────────

  const catNames = preview ? Object.keys(preview.catalogs) : [];
  const hasUnmatched = (preview?.unmatched?.length ?? 0) > 0;
  const currentDiff: ImportCatalogDiff | null = preview?.catalogs[activeTab] ?? null;

  const fmtPrice = (n: number | null | undefined) => {
    if (n == null) return "\u2014";
    return n.toLocaleString("es-AR", { maximumFractionDigits: 0 });
  };

  // ── Step subtitle ─────────────────────────────────────────────────────────

  const subtitle = step === "upload" ? "Arrastr\u00E1 un archivo exportado de Dux (.xls, .xlsx, .csv)"
    : step === "detect" ? "Analizando archivo..."
    : step === "preview" && preview ? `${FORMAT_LABELS[preview.format] || preview.format} \u00B7 ${preview.total_items} items`
    : step === "importing" ? "Importando..."
    : "Importaci\u00F3n completada";

  return (
    <div
      className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget && !importing) onClose(); }}
    >
      <div
        className="bg-s2 border border-b1 rounded-xl w-full max-w-[780px] max-h-[85vh] overflow-hidden shadow-[0_24px_80px_rgba(0,0,0,0.5)] flex flex-col animate-[fadeUp_0.2s_ease-out]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-b1 shrink-0">
          <div>
            <div className="text-[15px] font-medium text-t1">Importar precios</div>
            <div className="text-[11px] text-t3 mt-0.5">{subtitle}</div>
          </div>
          {!importing && (
            <button onClick={onClose} className="w-7 h-7 rounded-md flex items-center justify-center text-t3 bg-transparent border-none cursor-pointer hover:text-t1 hover:bg-white/[0.05] transition">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          )}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">

          {/* ── Step: Upload ─────────────────────────────────── */}
          {step === "upload" && (
            <div>
              <input ref={fileRef} type="file" accept=".xls,.xlsx,.csv" className="hidden" onChange={e => handleFiles(e.target.files)} />
              <div
                onDragEnter={e => { e.preventDefault(); dragCounter.current++; setDragActive(true); }}
                onDragLeave={e => { e.preventDefault(); dragCounter.current--; if (dragCounter.current <= 0) { dragCounter.current = 0; setDragActive(false); } }}
                onDragOver={e => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileRef.current?.click()}
                className={clsx(
                  "flex flex-col items-center justify-center gap-3 py-16 px-8 rounded-xl cursor-pointer transition-all duration-200",
                  dragActive ? "border-2 border-acc bg-acc/[0.06]" : "border-2 border-dashed border-b2 bg-white/[0.01] hover:border-b3 hover:bg-white/[0.02]",
                )}
              >
                <div className={clsx("w-12 h-12 rounded-xl flex items-center justify-center transition-colors", dragActive ? "bg-acc/[0.15] text-acc" : "bg-white/[0.04] text-t3")}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                </div>
                <div className="text-center">
                  <div className={clsx("text-sm font-medium", dragActive ? "text-acc" : "text-t1")}>{dragActive ? "Solt\u00E1 el archivo ac\u00E1" : "Arrastr\u00E1 un archivo o hac\u00E9 click"}</div>
                  <div className="text-[11px] text-t3 mt-1">.xls \u00B7 .xlsx \u00B7 .csv \u2014 exportado de Dux</div>
                </div>
              </div>
              <p className="text-[11px] text-t3 mt-3 leading-relaxed">Los precios se toman SIN IVA. No se modifica ning\u00FAn cat\u00E1logo hasta confirmar.</p>
              {error && <div className="mt-3 px-3.5 py-2.5 rounded-lg bg-red-500/[0.08] border border-red-500/20 text-xs text-red-400 flex items-start gap-2">{error}</div>}
            </div>
          )}

          {/* ── Step: Detecting ──────────────────────────────── */}
          {step === "detect" && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <div className="w-8 h-8 border-2 border-acc border-t-transparent rounded-full animate-spin" />
              <div className="text-sm text-t2">Analizando {file?.name}...</div>
            </div>
          )}

          {/* ── Step: Preview ────────────────────────────────── */}
          {step === "preview" && preview && (
            <div className="flex flex-col gap-4">
              {/* File info */}
              <div className="flex items-center gap-3 px-3.5 py-2.5 bg-s3 rounded-lg border border-b1">
                <span className="text-lg shrink-0">{"\uD83D\uDCC4"}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-medium text-t1 truncate">{file?.name}</div>
                  <div className="text-[11px] text-t3">{FORMAT_LABELS[preview.format] || preview.format} \u00B7 {preview.total_items} items \u00B7 Precio: <strong className="text-t2">sin IVA</strong></div>
                </div>
              </div>

              {/* IVA warning */}
              {preview.iva_warning && (
                <div className="px-3.5 py-3 rounded-lg bg-red-500/[0.08] border border-red-500/20 text-xs text-red-400 leading-relaxed">
                  <strong>{"\uD83D\uDD34"} Precio con IVA detectado</strong><br/>
                  El archivo solo tiene la columna {"\u201C"}Precio De Venta Con IVA{"\u201D"}. Los cat{"\u00E1"}logos almacenan precios SIN IVA. No se puede importar sin confirmaci{"\u00F3"}n expl{"\u00ED"}cita.
                </div>
              )}

              {/* Catalog tabs */}
              <div className="flex gap-1 p-1 bg-white/[0.03] rounded-lg border border-b1 self-start flex-wrap">
                {catNames.map(name => {
                  const diff = preview.catalogs[name];
                  const hasChanges = diff.updated.length > 0 || diff.new.length > 0;
                  return (
                    <button key={name} onClick={() => setActiveTab(name)}
                      className={clsx("px-3 py-[6px] rounded-md text-xs font-medium font-sans border-none cursor-pointer transition-all",
                        activeTab === name ? "bg-acc/[0.15] text-acc shadow-sm" : "bg-transparent text-t3 hover:text-t2"
                      )}>
                      {name}
                      {hasChanges && <span className="ml-1 w-[5px] h-[5px] rounded-full bg-amb inline-block" />}
                    </button>
                  );
                })}
                {hasUnmatched && (
                  <button onClick={() => setActiveTab("_unmatched")}
                    className={clsx("px-3 py-[6px] rounded-md text-xs font-medium font-sans border-none cursor-pointer transition-all",
                      activeTab === "_unmatched" ? "bg-acc/[0.15] text-acc shadow-sm" : "bg-transparent text-t3 hover:text-t2"
                    )}>
                    Sin asignar ({preview.unmatched.length})
                  </button>
                )}
              </div>

              {/* Diff table for selected catalog */}
              {currentDiff && activeTab !== "_unmatched" && (
                <div>
                  {/* Stats bar */}
                  <div className="flex items-center gap-3 mb-3">
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input type="checkbox" checked={selectedCatalogs.has(activeTab)} onChange={() => toggleCatalog(activeTab)}
                        className="w-3.5 h-3.5 rounded accent-[var(--acc)]" />
                      <span className="text-xs font-medium text-t2">Importar</span>
                    </label>
                    <div className="flex gap-3 text-[11px] text-t3 ml-auto">
                      {currentDiff.updated.length > 0 && <span><strong className="text-amb">{currentDiff.updated.length}</strong> actualizados</span>}
                      {currentDiff.new.length > 0 && <span><strong className="text-grn">{currentDiff.new.length}</strong> nuevos</span>}
                      <span><strong>{currentDiff.unchanged}</strong> sin cambio</span>
                      {currentDiff.missing.length > 0 && <span><strong className="text-t3">{currentDiff.missing.length}</strong> faltantes</span>}
                      {currentDiff.zero_price.length > 0 && <span><strong className="text-red-400">{currentDiff.zero_price.length}</strong> $0</span>}
                    </div>
                  </div>

                  {/* Table */}
                  <div className="overflow-x-auto rounded-lg border border-b1">
                    <table className="w-full border-collapse text-[12px]">
                      <thead>
                        <tr className="bg-white/[0.03]">
                          <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">SKU</th>
                          <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Nombre</th>
                          <th className="text-right px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Actual</th>
                          <th className="text-right px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Nuevo</th>
                          <th className="text-right px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Cambio</th>
                        </tr>
                      </thead>
                      <tbody>
                        {/* Updated items */}
                        {currentDiff.updated.map(item => (
                          <tr key={item.sku} className="bg-amber-500/[0.04]">
                            <td className="px-3 py-2 font-mono text-[11px] border-b border-white/[0.03]">{item.sku}</td>
                            <td className="px-3 py-2 border-b border-white/[0.03] text-t2">{item.name}</td>
                            <td className="px-3 py-2 text-right font-mono text-[11px] border-b border-white/[0.03] text-t3 line-through">{currentDiff.currency === "USD" ? `USD ${fmtPrice(item.old_price)}` : `$${fmtPrice(item.old_price)}`}</td>
                            <td className="px-3 py-2 text-right font-mono text-[11px] border-b border-white/[0.03] text-amb font-semibold">{currentDiff.currency === "USD" ? `USD ${fmtPrice(item.new_price)}` : `$${fmtPrice(item.new_price)}`}</td>
                            <td className="px-3 py-2 text-right border-b border-white/[0.03]">
                              <span className={clsx("text-[10px] px-1.5 py-0.5 rounded font-semibold", (item.change_pct ?? 0) > 0 ? "bg-amber-500/10 text-amb" : "bg-green-500/10 text-grn")}>
                                {(item.change_pct ?? 0) > 0 ? "+" : ""}{item.change_pct}%
                              </span>
                            </td>
                          </tr>
                        ))}
                        {/* New items */}
                        {currentDiff.new.map(item => (
                          <tr key={item.sku} className="bg-green-500/[0.04]">
                            <td className="px-3 py-2 font-mono text-[11px] border-b border-white/[0.03]">{item.sku}</td>
                            <td className="px-3 py-2 border-b border-white/[0.03] text-t2">{item.name}</td>
                            <td className="px-3 py-2 text-right border-b border-white/[0.03] text-t4">\u2014</td>
                            <td className="px-3 py-2 text-right font-mono text-[11px] border-b border-white/[0.03] text-grn font-semibold">{fmtPrice(item.price)}</td>
                            <td className="px-3 py-2 text-right border-b border-white/[0.03]"><span className="text-[10px] text-grn">Nuevo</span></td>
                          </tr>
                        ))}
                        {/* Zero price */}
                        {currentDiff.zero_price.map(item => (
                          <tr key={item.sku} className="bg-red-500/[0.04]">
                            <td className="px-3 py-2 font-mono text-[11px] border-b border-white/[0.03]">{item.sku}</td>
                            <td className="px-3 py-2 border-b border-white/[0.03] text-t3">{item.name}</td>
                            <td className="px-3 py-2 text-right border-b border-white/[0.03]" colSpan={2}><span className="text-[10px] text-red-400">$0 \u2014 se ignora</span></td>
                            <td className="px-3 py-2 border-b border-white/[0.03]"></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Missing items note */}
                  {currentDiff.missing.length > 0 && (
                    <div className="mt-3 px-3.5 py-2.5 rounded-lg bg-s3 border border-b1 text-[11px] text-t3 leading-relaxed">
                      <strong className="text-t2">Faltantes</strong> ({currentDiff.missing.length} items en cat\u00E1logo pero no en archivo): {currentDiff.missing.slice(0, 5).map(m => m.sku).join(" \u00B7 ")}{currentDiff.missing.length > 5 ? ` \u00B7 +${currentDiff.missing.length - 5} m\u00E1s` : ""}. <strong>Se mantienen sin cambios.</strong>
                    </div>
                  )}
                </div>
              )}

              {/* Unmatched tab */}
              {activeTab === "_unmatched" && preview.unmatched.length > 0 && (
                <div>
                  <div className="overflow-x-auto rounded-lg border border-b1">
                    <table className="w-full border-collapse text-[12px]">
                      <thead>
                        <tr className="bg-white/[0.03]">
                          <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">SKU</th>
                          <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Nombre</th>
                          <th className="text-right px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Precio</th>
                          <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Estado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.unmatched.map(item => (
                          <tr key={item.sku} className={item.price === 0 || item.price === null ? "bg-red-500/[0.04]" : ""}>
                            <td className="px-3 py-2 font-mono text-[11px] border-b border-white/[0.03]">{item.sku}</td>
                            <td className="px-3 py-2 border-b border-white/[0.03] text-t2">{item.name}</td>
                            <td className="px-3 py-2 text-right font-mono text-[11px] border-b border-white/[0.03]">{item.price ? `$${fmtPrice(item.price)}` : <span className="text-red-400">$0</span>}</td>
                            <td className="px-3 py-2 border-b border-white/[0.03] text-[10px]">
                              {item.price === 0 || item.price === null ? <span className="text-red-400">Se ignora</span> : <span className="text-acc">Sin cat\u00E1logo</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mt-3 px-3.5 py-2.5 rounded-lg bg-acc/[0.06] border border-acc/20 text-[11px] text-acc leading-relaxed">
                    {"\u2139\uFE0F"} Estos items no se importan autom\u00E1ticamente. Si son v\u00E1lidos, agregalos manualmente al cat\u00E1logo correspondiente.
                  </div>
                </div>
              )}

              {/* Warnings */}
              {preview.warnings.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  {preview.warnings.map((w, i) => (
                    <div key={i} className="px-3.5 py-2 rounded-lg bg-amber-500/[0.06] border border-amber-500/20 text-[11px] text-amb leading-relaxed">
                      {"\u26A0"} {w}
                    </div>
                  ))}
                </div>
              )}

              {/* Include new toggle */}
              {catNames.some(n => preview.catalogs[n].new.length > 0) && (
                <label className="flex items-center gap-2 cursor-pointer mt-1">
                  <input type="checkbox" checked={includeNew} onChange={e => setIncludeNew(e.target.checked)} className="w-3.5 h-3.5 rounded accent-[var(--acc)]" />
                  <span className="text-[12px] text-t2">Incluir items nuevos que no existen en el cat\u00E1logo actual</span>
                </label>
              )}

              {error && <div className="px-3.5 py-2.5 rounded-lg bg-red-500/[0.08] border border-red-500/20 text-xs text-red-400">{error}</div>}
            </div>
          )}

          {/* ── Step: Importing ──────────────────────────────── */}
          {step === "importing" && (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
              <div className="w-8 h-8 border-2 border-acc border-t-transparent rounded-full animate-spin" />
              <div className="text-sm text-t2">Creando backups e importando...</div>
              <div className="text-[11px] text-t3">{selectedCatalogs.size} cat\u00E1logos seleccionados</div>
            </div>
          )}

          {/* ── Step: Done ───────────────────────────────────── */}
          {step === "done" && applyResult && (
            <div className="flex flex-col items-center py-8 gap-4">
              <div className="text-4xl">{"\u2705"}</div>
              <div className="text-[16px] font-semibold">Importaci\u00F3n completada</div>

              <div className="w-full max-w-[400px] flex flex-col gap-2 px-4 py-3 bg-s3 rounded-lg border border-b1">
                <div className="flex justify-between text-[12px]"><span className="text-t3">Archivo</span><span className="text-t1 font-medium">{file?.name}</span></div>
                <div className="flex justify-between text-[12px]"><span className="text-t3">Fecha</span><span className="text-t1">{new Date().toLocaleString("es-AR")}</span></div>
                <div className="border-t border-b1 my-1" />
                {Object.entries(applyResult).map(([cat, stats]: [string, any]) => (
                  <div key={cat} className="flex justify-between text-[12px]">
                    <span className="text-t2">{cat}</span>
                    <span className="text-t1">{stats.ok ? `${stats.updated || 0} actualizados \u00B7 ${stats.added || 0} nuevos` : <span className="text-red-400">Error</span>}</span>
                  </div>
                ))}
                <div className="border-t border-b1 my-1" />
                <div className="flex justify-between text-[12px]"><span className="text-t3">Backups</span><span className="text-t1">{Object.keys(applyResult).length} backups creados</span></div>
              </div>

              <p className="text-[11px] text-t3">Pod\u00E9s restaurar desde <strong className="text-t2">Historial de backups</strong> en cada cat\u00E1logo.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-b1 flex justify-end gap-2.5 shrink-0">
          {step === "preview" && (
            <>
              <button onClick={onClose} className="px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition">Cancelar</button>
              <button onClick={() => { setStep("upload"); setPreview(null); setError(""); }} className="px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition">{"\u2190"} Cambiar archivo</button>
              <button
                onClick={handleApply}
                disabled={selectedCatalogs.size === 0 || !!preview?.iva_warning}
                className={clsx(
                  "px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans border-none text-white transition",
                  selectedCatalogs.size === 0 || preview?.iva_warning ? "bg-acc/30 cursor-not-allowed" : "bg-acc cursor-pointer hover:bg-blue-500",
                )}
              >
                Importar ({selectedCatalogs.size})
              </button>
            </>
          )}
          {step === "done" && (
            <button onClick={onClose} className="px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans border-none bg-acc text-white cursor-pointer hover:bg-blue-500 transition">Cerrar</button>
          )}
        </div>
      </div>
    </div>
  );
}
