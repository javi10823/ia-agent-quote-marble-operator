"use client";

import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { fetchCatalogs, fetchCatalog, validateCatalog, updateCatalog, listBackups, restoreBackup, type BackupEntry } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import CatalogSidebar from "@/components/catalog/CatalogSidebar";
import CatalogToolbar from "@/components/catalog/CatalogToolbar";
import ImportModal from "@/components/catalog/ImportModal";

// Dynamic import to avoid SSR issues with CodeMirror
const CatalogEditor = dynamic(() => import("@/components/catalog/CatalogEditor"), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-5 h-5 border-2 border-acc/30 border-t-acc rounded-full animate-spin" />
        <span className="text-xs text-t3">Cargando editor...</span>
      </div>
    </div>
  ),
});

interface CatalogMeta {
  name: string;
  item_count: number;
  last_updated: string | null;
  size_kb: number;
}

interface Validation {
  valid: boolean;
  warnings: { type: string; sku?: string; message: string }[];
}

export default function ConfigPage() {
  const [catalogs, setCatalogs] = useState<CatalogMeta[]>([]);
  const [selected, setSelected] = useState("labor");
  const [content, setContent] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [validation, setValidation] = useState<Validation | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [warningsExpanded, setWarningsExpanded] = useState(true);
  const [backups, setBackups] = useState<BackupEntry[]>([]);
  const [restoreTarget, setRestoreTarget] = useState<BackupEntry | null>(null);
  const [restoring, setRestoring] = useState(false);
  const toast = useToast();

  const hasChanges = content !== originalContent;
  const meta = catalogs.find(c => c.name === selected);

  // Load catalog list
  useEffect(() => {
    fetchCatalogs().then(setCatalogs).catch((err: any) => {
      toast(err.message || "Error al cargar catalogos");
    });
  }, [toast]);

  // Load selected catalog
  const loadCatalog = useCallback((name: string) => {
    setLoading(true);
    setValidation(null);
    setLoadError(null);
    fetchCatalog(name)
      .then(d => {
        const s = JSON.stringify(d, null, 2);
        setContent(s);
        setOriginalContent(s);
      })
      .catch((err: any) => {
        setLoadError(err.message || "Error al cargar catalogo");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadCatalog(selected);
  }, [selected, loadCatalog]);

  // Switch catalog with unsaved guard
  const handleSelectCatalog = useCallback(
    (name: string) => {
      if (name === selected) return;
      if (hasChanges) {
        const ok = window.confirm(
          "Tenes cambios sin guardar. Si cambias de catalogo se van a perder.\n\n¿Continuar?"
        );
        if (!ok) return;
      }
      setSelected(name);
    },
    [selected, hasChanges]
  );

  // Validate
  const handleValidate = useCallback(async () => {
    setValidating(true);
    try {
      const parsed = JSON.parse(content);
      const result = await validateCatalog(selected, parsed);
      setValidation(result);
      setWarningsExpanded(true);
    } catch {
      setValidation({
        valid: false,
        warnings: [{ type: "error", message: "JSON invalido — revisa la sintaxis" }],
      });
    } finally {
      setValidating(false);
    }
  }, [content, selected]);

  // Save
  const handleSave = useCallback(async () => {
    if (!validation?.valid) return;
    setSaving(true);
    try {
      await updateCatalog(selected, JSON.parse(content));
      setOriginalContent(content);
      setValidation(null);
      const updated = await fetchCatalogs();
      setCatalogs(updated);
      toast("Catalogo guardado correctamente", "success");
    } catch (err: any) {
      toast(err.message || "Error al guardar catalogo");
    } finally {
      setSaving(false);
    }
  }, [validation, content, selected, toast]);

  // Load backups for selected catalog
  const loadBackups = useCallback(() => {
    listBackups(selected).then(setBackups).catch(() => setBackups([]));
  }, [selected]);
  useEffect(() => { loadBackups(); }, [loadBackups]);

  // After import completes: refresh catalog + backups
  const handleImportDone = useCallback(() => {
    loadCatalog(selected);
    loadBackups();
    fetchCatalogs().then(setCatalogs).catch(() => {});
  }, [selected, loadCatalog, loadBackups]);

  // Restore backup
  const handleRestore = useCallback(async () => {
    if (!restoreTarget) return;
    setRestoring(true);
    try {
      await restoreBackup(restoreTarget.id);
      loadCatalog(selected);
      loadBackups();
      fetchCatalogs().then(setCatalogs).catch(() => {});
      toast("Cat\u00E1logo restaurado correctamente", "success");
    } catch (err: any) {
      toast(err.message || "Error al restaurar", "error");
    } finally {
      setRestoring(false);
      setRestoreTarget(null);
    }
  }, [restoreTarget, selected, loadCatalog, loadBackups, toast]);

  // Keyboard shortcut: Ctrl/Cmd+S to save
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (validation?.valid && hasChanges && !saving) {
          handleSave();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [validation, hasChanges, saving, handleSave]);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <CatalogToolbar
        catalogName={selected}
        meta={meta}
        hasChanges={hasChanges}
        validation={validation}
        validating={validating}
        saving={saving}
        onValidate={handleValidate}
        onSave={handleSave}
        onImport={() => setImportOpen(true)}
        onBack={() => window.history.back()}
      />

      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Sidebar */}
        <CatalogSidebar
          catalogs={catalogs}
          selected={selected}
          onSelect={handleSelectCatalog}
          hasUnsavedChanges={hasChanges}
        />

        {/* Editor area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Validation warnings */}
          {validation && validation.warnings.length > 0 && (
            <div className="px-5 pt-3 shrink-0">
              <div className="bg-amb/[0.05] border border-amb/[0.14] rounded-lg overflow-hidden">
                <button
                  onClick={() => setWarningsExpanded(!warningsExpanded)}
                  className="w-full flex items-center gap-2 px-3.5 py-2.5 text-xs text-amb bg-transparent border-none cursor-pointer font-sans text-left hover:bg-amb/[0.03] transition"
                >
                  <svg
                    width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    className={`transition-transform ${warningsExpanded ? "rotate-90" : ""}`}
                  >
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                  <span className="font-medium">
                    {validation.warnings.length} advertencia{validation.warnings.length > 1 ? "s" : ""}
                  </span>
                  {!validation.valid && (
                    <span className="text-err text-[10px] ml-1">— corregir antes de guardar</span>
                  )}
                </button>
                {warningsExpanded && (
                  <div className="px-3.5 pb-2.5 flex flex-col gap-1">
                    {validation.warnings.map((w, i) => (
                      <div key={i} className="flex items-start gap-2 text-[11px] text-amb/85 py-0.5">
                        <span className="shrink-0 mt-0.5">
                          {w.type === "error" ? (
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#ff453a" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                          ) : (
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                          )}
                        </span>
                        <span>
                          {w.sku && (
                            <span className="font-mono text-[10px] px-1 py-px rounded bg-white/[0.05] mr-1.5">
                              {w.sku}
                            </span>
                          )}
                          {w.message}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Editor + Backups */}
          <div className="flex-1 overflow-y-auto px-5 py-3 flex flex-col gap-4">
            <div className="min-h-[400px] max-h-[60vh] border border-b1 rounded-lg overflow-auto">
              <CatalogEditor
                value={content}
                onChange={setContent}
                loading={loading}
                loadError={loadError}
                onRetry={() => loadCatalog(selected)}
              />
            </div>

            {/* Backup History */}
            {backups.length > 0 && (
              <div className="shrink-0 pb-4">
                <div className="text-[11px] font-semibold text-t3 uppercase tracking-wide mb-2">Historial de backups {"\u2014"} {selected}</div>
                <div className="flex flex-col gap-1">
                  {backups.map(b => (
                    <div key={b.id} className="flex items-center gap-3 px-3.5 py-2.5 bg-white/[0.015] border border-b1 rounded-lg">
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] font-medium text-t1">{b.created_at ? new Date(b.created_at).toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "\u2014"}</div>
                        <div className="text-[10px] text-t3 truncate mt-0.5">{b.source_file || "manual"}{b.stats?.items_before != null ? ` \u00B7 ${b.stats.items_before} items` : ""}{b.stats?.reason ? ` \u00B7 ${b.stats.reason}` : ""}</div>
                      </div>
                      <button
                        onClick={() => setRestoreTarget(b)}
                        className="px-2.5 py-1 rounded-md text-[11px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t3 hover:text-t1 hover:border-b3 transition shrink-0"
                      >
                        Restaurar
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Import Modal */}
      {importOpen && (
        <ImportModal
          onDone={handleImportDone}
          onClose={() => setImportOpen(false)}
        />
      )}

      {/* Restore Confirmation Modal */}
      {restoreTarget && (
        <div onClick={() => setRestoreTarget(null)} className="fixed inset-0 z-[999] bg-black/60 backdrop-blur-[4px] flex items-center justify-center">
          <div onClick={e => e.stopPropagation()} className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-6 md:py-7 w-[calc(100vw-32px)] max-w-[420px] shadow-[0_20px_60px_rgba(0,0,0,.5)]">
            <div className="text-[15px] font-medium text-t1 mb-2">Restaurar backup</div>
            <div className="text-[13px] text-t2 leading-relaxed mb-2">
              {"\u00BF"}Restaurar <strong className="text-t1">{selected}</strong> al estado del {restoreTarget.created_at ? new Date(restoreTarget.created_at).toLocaleString("es-AR") : "backup"}?
            </div>
            <div className="text-[11px] text-t3 mb-1">Origen: {restoreTarget.source_file || "manual"}</div>
            <div className="text-[11px] text-amb mb-5">Se crear{"\u00E1"} un backup de seguridad del estado actual antes de restaurar.</div>
            <div className="flex gap-2.5 justify-end">
              <button onClick={() => setRestoreTarget(null)} className="px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition">Cancelar</button>
              <button
                onClick={handleRestore}
                disabled={restoring}
                className={`px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans border-none text-white transition ${restoring ? "bg-amb/60 cursor-wait" : "bg-amb cursor-pointer hover:bg-amber-500"}`}
              >
                {restoring ? "Restaurando..." : "Confirmar restauraci\u00F3n"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
