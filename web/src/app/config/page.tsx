"use client";

import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { fetchCatalogs, fetchCatalog, validateCatalog, updateCatalog } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import CatalogSidebar from "@/components/catalog/CatalogSidebar";
import CatalogToolbar from "@/components/catalog/CatalogToolbar";
import CsvImportModal from "@/components/catalog/CsvImportModal";

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
  const [csvImportOpen, setCsvImportOpen] = useState(false);
  const [warningsExpanded, setWarningsExpanded] = useState(true);
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

  // CSV import apply
  const handleCsvApply = useCallback((jsonString: string) => {
    setContent(jsonString);
    setValidation(null);
    toast("Datos importados. Valida y guarda para confirmar.", "warning");
  }, [toast]);

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
        onImport={() => setCsvImportOpen(true)}
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

          {/* Editor */}
          <div className="flex-1 overflow-hidden px-5 py-3">
            <div className="h-full border border-b1 rounded-lg overflow-auto">
              <CatalogEditor
                value={content}
                onChange={setContent}
                loading={loading}
                loadError={loadError}
                onRetry={() => loadCatalog(selected)}
              />
            </div>
          </div>
        </div>
      </div>

      {/* CSV Import Modal */}
      {csvImportOpen && (
        <CsvImportModal
          catalogName={selected}
          currentContent={content}
          onApply={handleCsvApply}
          onClose={() => setCsvImportOpen(false)}
        />
      )}
    </div>
  );
}
