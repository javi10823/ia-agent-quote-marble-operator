"use client";

import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import Papa from "papaparse";
import CsvPreviewTable from "./CsvPreviewTable";
import clsx from "clsx";

interface Props {
  catalogName: string;
  currentContent: string;
  onApply: (jsonString: string) => void;
  onClose: () => void;
}

// Column aliases: CSV/JSON field name → canonical JSON field name
const ALIASES: Record<string, string> = {
  precio: "price_ars",
  precio_ars: "price_ars",
  precio_usd: "price_usd",
  nombre: "name",
  tarea: "task",
  ubicacion: "location",
  categoria: "category",
  tipo: "material_type",
  espesor: "thickness_mm",
  unidad: "unit",
  foto: "photo",
  descuento: "discount_percentage",
  notas: "notes",
  moneda: "currency",
  ultima_actualizacion: "last_updated",
};

// Required fields per catalog type
const REQUIRED_FIELDS: Record<string, string[]> = {
  labor: ["sku", "name", "price_ars"],
  "delivery-zones": ["sku", "location", "price_ars"],
  architects: ["name"],
  sinks: ["sku", "name", "price_ars"],
  materials: ["sku", "name", "price_usd"],
};

// SKU field used for merge matching per catalog type
const SKU_FIELD: Record<string, string> = {
  architects: "name",
};

function getRequiredFields(catalogName: string): string[] {
  if (catalogName.startsWith("materials-")) return REQUIRED_FIELDS.materials;
  return REQUIRED_FIELDS[catalogName] || ["sku", "name"];
}

function getSkuField(catalogName: string): string {
  return SKU_FIELD[catalogName] || "sku";
}

function normalizeFieldName(field: string): string {
  const lower = field.toLowerCase().trim().replace(/\s+/g, "_");
  return ALIASES[lower] || lower;
}

type Step = "upload" | "preview" | "confirm";
type ImportMode = "merge" | "replace";

interface MergeStats {
  updated: number;
  added: number;
  unchanged: number;
  total: number;
}

export default function CsvImportModal({ catalogName, currentContent, onApply, onClose }: Props) {
  const [step, setStep] = useState<Step>("upload");
  const [mode, setMode] = useState<ImportMode>("merge");
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [mappedFields, setMappedFields] = useState<Set<string>>(new Set());
  const [missingRequired, setMissingRequired] = useState<string[]>([]);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [fileName, setFileName] = useState("");
  const [fileType, setFileType] = useState<"csv" | "json">("csv");
  const fileRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  // Parse current catalog items for merge
  const currentItems = useMemo(() => {
    try {
      const parsed = JSON.parse(currentContent);
      if (Array.isArray(parsed)) return parsed;
      if (parsed?.items && Array.isArray(parsed.items)) return parsed.items;
      if (parsed?.stock && Array.isArray(parsed.stock)) return parsed.stock;
      return [];
    } catch {
      return [];
    }
  }, [currentContent]);

  // Compute merge stats
  const mergeStats = useMemo((): MergeStats => {
    if (mode !== "merge" || rows.length === 0) {
      return { updated: 0, added: 0, unchanged: 0, total: rows.length };
    }
    const skuField = getSkuField(catalogName);
    const existingMap = new Map<string, Record<string, unknown>>();
    for (const item of currentItems) {
      const key = String(item[skuField] || "").toUpperCase();
      if (key) existingMap.set(key, item);
    }

    let updated = 0;
    let added = 0;
    for (const row of rows) {
      const key = String(row[skuField] || "").toUpperCase();
      if (!key) { added++; continue; }
      const existing = existingMap.get(key);
      if (!existing) {
        added++;
      } else {
        // Check if any imported field actually changes
        let changed = false;
        for (const [field, value] of Object.entries(row)) {
          if (field === skuField) continue;
          if (value != null && value !== "" && existing[field] !== value) {
            changed = true;
            break;
          }
        }
        if (changed) updated++;
      }
    }
    const matchedKeys = new Set(rows.map(r => String(r[skuField] || "").toUpperCase()).filter(Boolean));
    const unchanged = currentItems.filter((item: Record<string, unknown>) => {
      const key = String(item[skuField] || "").toUpperCase();
      return key && !matchedKeys.has(key);
    }).length + (rows.length - updated - added);

    return {
      updated,
      added,
      unchanged: currentItems.length - updated + added > 0 ? currentItems.length - updated : 0,
      total: currentItems.length - updated + rows.length,
    };
  }, [mode, rows, currentItems, catalogName]);

  // Escape to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Normalize rows: apply field aliases to all keys
  const normalizeRows = useCallback((rawRows: Record<string, unknown>[], rawHeaders: string[]): {
    normalizedHeaders: string[];
    normalizedRows: Record<string, unknown>[];
    mapped: Set<string>;
  } => {
    const normalizedHeaders = rawHeaders.map(normalizeFieldName);
    const mapped = new Set(normalizedHeaders);

    const normalizedRows = rawRows.map(row => {
      const out: Record<string, unknown> = {};
      rawHeaders.forEach((origH, i) => {
        out[normalizedHeaders[i]] = row[origH];
      });
      return out;
    });

    return { normalizedHeaders, normalizedRows, mapped };
  }, []);

  // Parse CSV file
  const parseCsvFile = useCallback((file: File) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      dynamicTyping: true,
      complete(results) {
        if (!results.data || results.data.length === 0) {
          setError("El archivo CSV esta vacio o no se pudo leer.");
          return;
        }

        const csvHeaders = results.meta.fields || [];
        const csvRows = results.data as Record<string, unknown>[];
        const { normalizedHeaders, normalizedRows, mapped } = normalizeRows(csvRows, csvHeaders);

        const required = getRequiredFields(catalogName);
        const missing = required.filter(f => !mapped.has(f));

        const errs: string[] = [];
        if (results.errors.length > 0) {
          for (const e of results.errors.slice(0, 5)) {
            errs.push(`Fila ${e.row ?? "?"}: ${e.message}`);
          }
          if (results.errors.length > 5) {
            errs.push(`...y ${results.errors.length - 5} errores mas`);
          }
        }

        setHeaders(normalizedHeaders);
        setRows(normalizedRows);
        setMappedFields(mapped);
        setMissingRequired(missing);
        setParseErrors(errs);
        setStep("preview");
      },
      error(err) {
        setError(`Error al leer CSV: ${err.message}`);
      },
    });
  }, [catalogName, normalizeRows]);

  // Parse JSON file
  const parseJsonFile = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = reader.result as string;
        let parsed = JSON.parse(text);

        // Handle different JSON structures
        let items: Record<string, unknown>[];
        if (Array.isArray(parsed)) {
          items = parsed;
        } else if (parsed?.items && Array.isArray(parsed.items)) {
          items = parsed.items;
        } else if (parsed?.stock && Array.isArray(parsed.stock)) {
          items = parsed.stock;
        } else if (typeof parsed === "object" && parsed !== null) {
          // Single object → wrap in array
          items = [parsed];
        } else {
          setError("Formato JSON no reconocido. Se esperaba un array o un objeto con items.");
          return;
        }

        if (items.length === 0) {
          setError("El archivo JSON no contiene items.");
          return;
        }

        // Extract headers from all keys across all items
        const allKeys = new Set<string>();
        for (const item of items) {
          for (const key of Object.keys(item)) allKeys.add(key);
        }
        const rawHeaders = Array.from(allKeys);

        // Normalize field names (apply aliases)
        const normalizedHeaders = rawHeaders.map(normalizeFieldName);
        const mapped = new Set(normalizedHeaders);

        const normalizedRows = items.map(item => {
          const out: Record<string, unknown> = {};
          rawHeaders.forEach((origH, i) => {
            out[normalizedHeaders[i]] = item[origH];
          });
          return out;
        });

        const required = getRequiredFields(catalogName);
        const missing = required.filter(f => !mapped.has(f));

        setHeaders(normalizedHeaders);
        setRows(normalizedRows);
        setMappedFields(mapped);
        setMissingRequired(missing);
        setParseErrors([]);
        setStep("preview");
      } catch (e: any) {
        setError(`JSON invalido: ${e.message}`);
      }
    };
    reader.onerror = () => setError("Error al leer el archivo.");
    reader.readAsText(file);
  }, [catalogName]);

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    const name = file.name.toLowerCase();
    setFileName(file.name);
    setError(null);
    setParseErrors([]);

    if (name.endsWith(".csv")) {
      setFileType("csv");
      parseCsvFile(file);
    } else if (name.endsWith(".json")) {
      setFileType("json");
      parseJsonFile(file);
    } else {
      setError("Solo se aceptan archivos .csv o .json");
    }
  }, [parseCsvFile, parseJsonFile]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current = 0;
    setDragActive(false);
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  // Apply: merge or replace
  const handleApply = useCallback(() => {
    try {
      let resultItems: Record<string, unknown>[];

      if (mode === "merge") {
        // Build map of existing items by SKU
        const skuField = getSkuField(catalogName);
        const existingMap = new Map<string, Record<string, unknown>>();
        for (const item of currentItems) {
          const key = String(item[skuField] || "").toUpperCase();
          if (key) existingMap.set(key, { ...item });
        }

        // Merge: update existing, add new
        const touchedKeys = new Set<string>();
        for (const row of rows) {
          const key = String(row[skuField] || "").toUpperCase();
          if (key && existingMap.has(key)) {
            // Merge: only overwrite fields that have non-null/non-empty values
            const merged = existingMap.get(key)!;
            for (const [field, value] of Object.entries(row)) {
              if (value != null && value !== "") {
                merged[field] = value;
              }
            }
            existingMap.set(key, merged);
            touchedKeys.add(key);
          } else {
            // New item: add with all fields
            if (key) {
              existingMap.set(key, { ...row });
              touchedKeys.add(key);
            } else {
              // No SKU: just append
              existingMap.set(`__new_${Math.random()}`, { ...row });
            }
          }
        }

        // Reconstruct: existing order preserved, new items at end
        resultItems = [];
        const addedKeys = new Set<string>();
        // First: existing items in original order (updated or not)
        for (const item of currentItems) {
          const key = String(item[skuField] || "").toUpperCase();
          if (key && existingMap.has(key)) {
            resultItems.push(existingMap.get(key)!);
            addedKeys.add(key);
          } else {
            resultItems.push(item);
          }
        }
        // Then: new items not in original
        existingMap.forEach((item, key) => {
          if (!addedKeys.has(key)) {
            resultItems.push(item);
          }
        });
      } else {
        // Full replacement
        resultItems = rows;
      }

      // Handle catalogs with _metadata wrappers
      const parsed = (() => { try { return JSON.parse(currentContent); } catch { return null; } })();
      if (parsed && !Array.isArray(parsed) && parsed?._metadata) {
        if (parsed.items) {
          parsed.items = resultItems;
        } else if (parsed.stock) {
          parsed.stock = resultItems;
        }
        onApply(JSON.stringify(parsed, null, 2));
      } else {
        onApply(JSON.stringify(resultItems, null, 2));
      }
    } catch {
      setError("Error al generar JSON. Verifica el contenido.");
    }
  }, [mode, catalogName, currentContent, currentItems, rows, onApply]);

  const resetUpload = useCallback(() => {
    setStep("upload");
    setRows([]);
    setHeaders([]);
    setError(null);
    setParseErrors([]);
  }, []);

  return (
    <div
      className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="Importar datos"
    >
      <div
        className="bg-s2 border border-b1 rounded-xl w-full max-w-[740px] max-h-[85vh] overflow-hidden shadow-[0_24px_80px_rgba(0,0,0,0.5)] flex flex-col animate-[fadeUp_0.2s_ease-out]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-b1 shrink-0">
          <div>
            <div className="text-[15px] font-medium text-t1">Importar datos</div>
            <div className="text-[11px] text-t3 mt-0.5">
              {step === "upload" && `Arrastra un CSV o JSON para ${catalogName}.json`}
              {step === "preview" && `Vista previa de ${fileName} — ${rows.length} filas`}
              {step === "confirm" && `Confirmar importacion a ${catalogName}.json`}
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-md flex items-center justify-center text-t3 bg-transparent border-none cursor-pointer hover:text-t1 hover:bg-white/[0.05] transition"
            aria-label="Cerrar"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">

          {/* ── Step 1: Upload ────────────────────────────────── */}
          {step === "upload" && (
            <div>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,.json"
                className="hidden"
                onChange={e => handleFiles(e.target.files)}
              />
              <div
                onDragEnter={e => { e.preventDefault(); dragCounter.current++; setDragActive(true); }}
                onDragLeave={e => { e.preventDefault(); dragCounter.current--; if (dragCounter.current <= 0) { dragCounter.current = 0; setDragActive(false); } }}
                onDragOver={e => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileRef.current?.click()}
                className={clsx(
                  "flex flex-col items-center justify-center gap-3 py-16 px-8 rounded-xl cursor-pointer transition-all duration-200",
                  dragActive
                    ? "border-2 border-acc bg-acc/[0.06] shadow-[0_0_30px_rgba(79,143,255,0.10)]"
                    : "border-2 border-dashed border-b2 bg-white/[0.01] hover:border-b3 hover:bg-white/[0.02]",
                )}
              >
                <div className={clsx(
                  "w-12 h-12 rounded-xl flex items-center justify-center transition-colors",
                  dragActive ? "bg-acc/[0.15] text-acc" : "bg-white/[0.04] text-t3",
                )}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                </div>
                <div className="text-center">
                  <div className={clsx("text-sm font-medium", dragActive ? "text-acc" : "text-t1")}>
                    {dragActive ? "Solta el archivo aca" : "Arrastra un archivo o hace click para seleccionar"}
                  </div>
                  <div className="text-[11px] text-t3 mt-1">
                    CSV con encabezados o JSON. Se detectan las columnas y se mapean automaticamente.
                  </div>
                </div>
              </div>

              {error && (
                <div className="mt-4 px-3.5 py-2.5 rounded-lg bg-err/[0.08] border border-err/[0.20] text-xs text-err flex items-start gap-2">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 mt-0.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                  {error}
                </div>
              )}
            </div>
          )}

          {/* ── Step 2: Preview ───────────────────────────────── */}
          {step === "preview" && (
            <div className="flex flex-col gap-4">

              {/* Import mode selector */}
              <div className="flex items-center gap-2 p-1 bg-white/[0.03] rounded-lg border border-b1 self-start">
                <button
                  onClick={() => setMode("merge")}
                  className={clsx(
                    "px-3 py-[6px] rounded-md text-xs font-medium font-sans border-none cursor-pointer transition-all",
                    mode === "merge"
                      ? "bg-acc/[0.15] text-acc shadow-sm"
                      : "bg-transparent text-t3 hover:text-t2",
                  )}
                >
                  Actualizar por SKU
                </button>
                <button
                  onClick={() => setMode("replace")}
                  className={clsx(
                    "px-3 py-[6px] rounded-md text-xs font-medium font-sans border-none cursor-pointer transition-all",
                    mode === "replace"
                      ? "bg-amb/[0.15] text-amb shadow-sm"
                      : "bg-transparent text-t3 hover:text-t2",
                  )}
                >
                  Reemplazo completo
                </button>
              </div>

              {/* Mode explanation */}
              <div className={clsx(
                "px-3.5 py-2.5 rounded-lg text-xs flex items-start gap-2",
                mode === "merge"
                  ? "bg-acc/[0.04] border border-acc/[0.12] text-acc/80"
                  : "bg-amb/[0.04] border border-amb/[0.12] text-amb/80",
              )}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 mt-0.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                {mode === "merge" ? (
                  <span>
                    <strong>Merge inteligente:</strong> Matchea por <code className="text-[10px] font-mono px-1 py-px rounded bg-white/[0.06]">{getSkuField(catalogName)}</code>.
                    Actualiza solo los campos que trae el archivo. Los items que no estan en el archivo se mantienen sin cambios. Items nuevos se agregan al final.
                  </span>
                ) : (
                  <span>
                    <strong>Reemplazo completo:</strong> Se elimina todo el contenido actual y se reemplaza por los datos del archivo.
                    Los items que no esten en el archivo se pierden.
                  </span>
                )}
              </div>

              {/* Merge stats */}
              {mode === "merge" && rows.length > 0 && (
                <div className="flex gap-3">
                  <StatBadge label="Actualizados" count={mergeStats.updated} color="acc" />
                  <StatBadge label="Nuevos" count={mergeStats.added} color="grn" />
                  <StatBadge label="Sin cambios" count={mergeStats.unchanged} color="t3" />
                </div>
              )}

              {/* Column mapping badges */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] text-t3">Columnas detectadas:</span>
                {headers.map(h => (
                  <span
                    key={h}
                    className={clsx(
                      "text-[10px] px-2 py-0.5 rounded-full font-mono",
                      mappedFields.has(h)
                        ? "bg-grn/[0.08] text-grn border border-grn/[0.15]"
                        : "bg-amb/[0.08] text-amb border border-amb/[0.15]",
                    )}
                  >
                    {h}
                  </span>
                ))}
              </div>

              {/* Missing required warning */}
              {missingRequired.length > 0 && (
                <div className="px-3.5 py-2.5 rounded-lg bg-amb/[0.06] border border-amb/[0.16] text-xs text-amb flex items-start gap-2">
                  <span className="shrink-0">&#9888;</span>
                  <div>
                    <strong>Campos requeridos faltantes:</strong>{" "}
                    {missingRequired.join(", ")}
                    <div className="text-amb/70 mt-0.5">
                      {mode === "merge"
                        ? "En modo merge los campos faltantes se mantienen del catalogo actual."
                        : "Podes continuar, pero el catalogo podria quedar incompleto."
                      }
                    </div>
                  </div>
                </div>
              )}

              {/* Parse errors */}
              {parseErrors.length > 0 && (
                <div className="px-3.5 py-2.5 rounded-lg bg-err/[0.06] border border-err/[0.16] text-xs text-err">
                  <strong>Errores de parseo:</strong>
                  {parseErrors.map((e, i) => <div key={i} className="mt-0.5">{e}</div>)}
                </div>
              )}

              {/* Preview table */}
              <CsvPreviewTable headers={headers} rows={rows} mappedFields={mappedFields} />

              {/* Actions */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={resetUpload}
                  className="px-3 py-[7px] rounded-md text-xs font-medium font-sans border border-b1 bg-transparent text-t2 cursor-pointer hover:border-b2 hover:text-t1 transition"
                >
                  Elegir otro archivo
                </button>
                <button
                  onClick={() => setStep("confirm")}
                  className="px-4 py-[7px] rounded-md text-xs font-medium font-sans border bg-acc-bg border-acc-hover text-acc cursor-pointer hover:bg-acc/20 transition"
                >
                  Continuar
                </button>
              </div>
            </div>
          )}

          {/* ── Step 3: Confirm ───────────────────────────────── */}
          {step === "confirm" && (
            <div className="flex flex-col items-center gap-5 py-6">
              <div className={clsx(
                "w-14 h-14 rounded-2xl flex items-center justify-center",
                mode === "merge" ? "bg-acc/[0.10]" : "bg-amb/[0.10]",
              )}>
                {mode === "merge" ? (
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#4f8fff" strokeWidth="1.5">
                    <path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 014-4h14"/>
                    <path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 01-4 4H3"/>
                  </svg>
                ) : (
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f5a623" strokeWidth="1.5">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="12" y1="18" x2="12" y2="12"/>
                    <line x1="9" y1="15" x2="15" y2="15"/>
                  </svg>
                )}
              </div>

              <div className="text-center">
                {mode === "merge" ? (
                  <>
                    <div className="text-[15px] font-medium text-t1">
                      Actualizar {catalogName}.json
                    </div>
                    <div className="text-xs text-t3 mt-2 max-w-[400px]">
                      Se actualizan <strong className="text-t1">{mergeStats.updated}</strong> items existentes
                      {mergeStats.added > 0 && <> y se agregan <strong className="text-t1">{mergeStats.added}</strong> nuevos</>}.
                      {mergeStats.unchanged > 0 && <> Los restantes <strong className="text-t1">{mergeStats.unchanged}</strong> items quedan sin cambios.</>}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-[15px] font-medium text-t1">
                      Reemplazar {catalogName}.json
                    </div>
                    <div className="text-xs text-t3 mt-2 max-w-[400px]">
                      Se reemplaza todo el contenido con <strong className="text-t1">{rows.length}</strong> items del archivo.
                      {currentItems.length > 0 && (
                        <> Los <strong className="text-t1">{currentItems.length}</strong> items actuales se eliminan.</>
                      )}
                    </div>
                  </>
                )}
                <div className="text-[11px] text-amb mt-3">
                  Los cambios se cargan en el editor. Debes validar y guardar para que sean definitivos.
                </div>
              </div>

              <div className="flex gap-3 mt-2">
                <button
                  onClick={() => setStep("preview")}
                  className="px-4 py-2 rounded-md text-xs font-medium font-sans border border-b1 bg-transparent text-t2 cursor-pointer hover:border-b2 hover:text-t1 transition"
                >
                  Volver
                </button>
                <button
                  onClick={() => { handleApply(); onClose(); }}
                  className={clsx(
                    "px-5 py-2 rounded-md text-xs font-medium font-sans border-none cursor-pointer transition",
                    mode === "merge"
                      ? "bg-acc text-white hover:bg-acc/90 shadow-[0_2px_12px_rgba(79,143,255,0.25)]"
                      : "bg-amb text-white hover:bg-amb/90 shadow-[0_2px_12px_rgba(245,166,35,0.25)]",
                  )}
                >
                  {mode === "merge" ? "Aplicar actualizacion" : "Aplicar reemplazo"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Stat badge sub-component ────────────────────────────────────────────────

function StatBadge({ label, count, color }: { label: string; count: number; color: string }) {
  const colorMap: Record<string, string> = {
    acc: "bg-acc/[0.08] text-acc border-acc/[0.15]",
    grn: "bg-grn/[0.08] text-grn border-grn/[0.15]",
    t3: "bg-white/[0.03] text-t3 border-b1",
  };
  return (
    <div className={clsx("flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium", colorMap[color] || colorMap.t3)}>
      <span className="text-[17px] font-semibold font-mono">{count}</span>
      <span className="text-[11px] opacity-80">{label}</span>
    </div>
  );
}
