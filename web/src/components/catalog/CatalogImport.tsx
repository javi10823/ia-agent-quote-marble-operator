/**
 * CatalogImport · sub-PR 22.2.b · importador Dux full-page (3 estados).
 *
 *   A. upload   → drag-drop + validación client (ext/size/MIME) → preview
 *   B. preview  → diff por catálogo (tabs · counters · tabla expandible),
 *                 selección de catálogos + include_new → apply
 *   C. success  → stats por catálogo + links al viewer · "Importar otro"
 *
 * iva_warning: banner GLOBAL (decisión 22.2.b · el backend solo emite flag
 * global · si está activo el backend RECHAZA el apply → deshabilitamos el
 * botón y explicamos). Bug encoding latin-1 se arregla en el backend.
 */
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { importApply, importPreview } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import type { CatalogDiff, ImportApplyResponse, ImportPreview } from "@/lib/api/types";

const VALID_EXT = [".xls", ".xlsx", ".csv"];
const VALID_MIME = [
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
  "text/csv",
  "", // algunos browsers no setean MIME para .csv → permitir y validar por extensión
];
const MAX_BYTES = 50 * 1024 * 1024; // 50 MB · backend NO valida tamaño (mitigación client-side)

type Phase =
  | { kind: "upload" }
  | { kind: "analyzing" }
  | { kind: "preview"; preview: ImportPreview }
  | { kind: "applying" }
  | { kind: "success"; result: ImportApplyResponse };

function validateFile(file: File): string | null {
  const lower = file.name.toLowerCase();
  if (!VALID_EXT.some((e) => lower.endsWith(e))) {
    return `Extensión no soportada. Usá ${VALID_EXT.join(", ")}.`;
  }
  if (file.size > MAX_BYTES) {
    return `El archivo supera 50 MB (${(file.size / 1024 / 1024).toFixed(1)} MB).`;
  }
  if (file.type && !VALID_MIME.includes(file.type)) {
    return `Tipo de archivo inesperado (${file.type}). Exportá como Excel o CSV desde Dux.`;
  }
  return null;
}

export function CatalogImport() {
  const [phase, setPhase] = useState<Phase>({ kind: "upload" });
  const [file, setFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [slow, setSlow] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [includeNew, setIncludeNew] = useState(true);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Banner "siendo procesado" si analyzing tarda >10s.
  useEffect(() => {
    if (phase.kind !== "analyzing" && phase.kind !== "applying") {
      setSlow(false);
      return;
    }
    const t = setTimeout(() => setSlow(true), 10_000);
    return () => clearTimeout(t);
  }, [phase.kind]);

  const acceptFile = (f: File) => {
    setApiError(null);
    const err = validateFile(f);
    if (err) {
      setValidationError(err);
      setFile(null);
      return;
    }
    setValidationError(null);
    setFile(f);
  };

  const runPreview = async () => {
    if (!file) return;
    setApiError(null);
    setPhase({ kind: "analyzing" });
    try {
      const preview = await importPreview(file);
      const catNames = Object.keys(preview.catalogs);
      // Preselección: todos los catálogos afectados (el operador deselecciona).
      setSelected(new Set(catNames));
      setActiveTab(catNames[0] ?? null);
      setPhase({ kind: "preview", preview });
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : "No se pudo analizar el archivo.");
      setPhase({ kind: "upload" });
    }
  };

  const runApply = async (preview: ImportPreview) => {
    if (!file) return;
    setConfirmApply(false);
    setApiError(null);
    setPhase({ kind: "applying" });
    try {
      const result = await importApply({
        file,
        catalogs: Array.from(selected),
        includeNew,
        sourceFile: file.name,
      });
      setPhase({ kind: "success", result });
    } catch (err) {
      setApiError(err instanceof ApiError ? err.message : "No se pudo aplicar la importación.");
      setPhase({ kind: "preview", preview });
    }
  };

  const reset = () => {
    setPhase({ kind: "upload" });
    setFile(null);
    setValidationError(null);
    setApiError(null);
    setSelected(new Set());
    setIncludeNew(true);
    setActiveTab(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="catalog-import" data-testid="catalog-import">
      {apiError && (
        <div className="banner err" role="alert" data-testid="import-api-error">
          {apiError}
        </div>
      )}

      {(phase.kind === "upload" || phase.kind === "analyzing") && (
        <UploadState
          phase={phase.kind}
          file={file}
          dragOver={dragOver}
          slow={slow}
          validationError={validationError}
          fileInputRef={fileInputRef}
          onDragOver={setDragOver}
          onPick={acceptFile}
          onSubmit={runPreview}
        />
      )}

      {phase.kind === "preview" && (
        <PreviewState
          preview={phase.preview}
          selected={selected}
          includeNew={includeNew}
          activeTab={activeTab}
          onToggleCatalog={(name) =>
            setSelected((prev) => {
              const next = new Set(prev);
              if (next.has(name)) next.delete(name);
              else next.add(name);
              return next;
            })
          }
          onIncludeNew={setIncludeNew}
          onTab={setActiveTab}
          onApply={() => setConfirmApply(true)}
        />
      )}

      {phase.kind === "applying" && (
        <div className="import-spinner" data-testid="import-applying">
          <p>Aplicando importación…</p>
          {slow && <p className="meta">Se generan backups automáticos · puede tardar unos segundos.</p>}
        </div>
      )}

      {phase.kind === "success" && <SuccessState result={phase.result} onAnother={reset} />}

      {confirmApply && phase.kind === "preview" && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" data-testid="apply-confirm">
          <div className="modal-card">
            <h3>Confirmar importación</h3>
            <p>
              Vas a actualizar <strong>{selected.size}</strong>{" "}
              {selected.size === 1 ? "catálogo" : "catálogos"}. Se genera un backup automático de cada
              uno antes de aplicar.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn ghost"
                onClick={() => setConfirmApply(false)}
                data-testid="apply-cancel"
              >
                Cancelar
              </button>
              <button
                type="button"
                className="btn primary"
                onClick={() => runApply(phase.preview)}
                data-testid="apply-confirm-yes"
              >
                Aplicar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Estado A · upload ────────────────────────────────────────────── */

function UploadState({
  phase,
  file,
  dragOver,
  slow,
  validationError,
  fileInputRef,
  onDragOver,
  onPick,
  onSubmit,
}: {
  phase: "upload" | "analyzing";
  file: File | null;
  dragOver: boolean;
  slow: boolean;
  validationError: string | null;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onDragOver: (v: boolean) => void;
  onPick: (f: File) => void;
  onSubmit: () => void;
}) {
  if (phase === "analyzing") {
    return (
      <div className="import-spinner" data-testid="import-analyzing">
        <p>Analizando archivo…</p>
        {slow && (
          <p className="meta" data-testid="import-slow-banner">
            El archivo está siendo procesado · puede tardar unos segundos.
          </p>
        )}
      </div>
    );
  }
  return (
    <div className="col">
      <div className="section-head">
        <h2>Importar desde Dux</h2>
        <span className="meta">
          Subí el export de Dux (.xls, .xlsx o .csv). Vas a poder revisar los cambios antes de
          aplicarlos. Los ítems con precio $0 se omiten y los faltantes nunca se borran.
        </span>
      </div>

      <div
        className={`import-dropzone${dragOver ? " over" : ""}`}
        data-testid="import-dropzone"
        onDragOver={(e) => {
          e.preventDefault();
          onDragOver(true);
        }}
        onDragLeave={() => onDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          onDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) onPick(f);
        }}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".xls,.xlsx,.csv"
          data-testid="import-file-input"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onPick(f);
          }}
        />
        {file ? (
          <p data-testid="import-file-name">
            <strong className="mono">{file.name}</strong> · {(file.size / 1024).toFixed(0)} KB
          </p>
        ) : (
          <p>Arrastrá el archivo acá o hacé click para elegirlo.</p>
        )}
      </div>

      {validationError && (
        <div className="banner err" role="alert" data-testid="import-validation-error">
          {validationError}
        </div>
      )}

      <div className="config-actions" style={{ marginTop: 8 }}>
        <button
          type="button"
          className="btn primary"
          disabled={!file}
          onClick={onSubmit}
          data-testid="import-analyze-btn"
        >
          Analizar archivo
        </button>
      </div>
    </div>
  );
}

/* ── Estado B · preview ───────────────────────────────────────────── */

function counts(diff: CatalogDiff) {
  return {
    updated: diff.updated.length,
    normalized: diff.normalized.length,
    new: diff.new.length,
    missing: diff.missing.length,
    zero_price: diff.zero_price.length,
    unchanged: diff.unchanged,
  };
}

function PreviewState({
  preview,
  selected,
  includeNew,
  activeTab,
  onToggleCatalog,
  onIncludeNew,
  onTab,
  onApply,
}: {
  preview: ImportPreview;
  selected: Set<string>;
  includeNew: boolean;
  activeTab: string | null;
  onToggleCatalog: (name: string) => void;
  onIncludeNew: (v: boolean) => void;
  onTab: (name: string) => void;
  onApply: () => void;
}) {
  const catNames = Object.keys(preview.catalogs);
  const active = activeTab && preview.catalogs[activeTab] ? preview.catalogs[activeTab] : null;
  const applyBlocked = preview.iva_warning || selected.size === 0;

  return (
    <div className="col" data-testid="import-preview">
      <div className="section-head">
        <h2>Revisar cambios</h2>
        <span className="meta">
          {preview.total_items} ítems leídos · formato {preview.format} · {catNames.length}{" "}
          {catNames.length === 1 ? "catálogo afectado" : "catálogos afectados"}
        </span>
      </div>

      {preview.iva_warning && (
        <div className="banner err" role="alert" data-testid="import-iva-warning">
          El archivo solo trae columna de precio <strong>CON IVA</strong>. No se puede importar sin
          confirmar la conversión a precio sin IVA. Re-exportá desde Dux incluyendo la columna de
          precio sin IVA.
        </div>
      )}
      {preview.currency_mismatch && (
        <div className="banner warn" role="alert" data-testid="import-currency-warning">
          La moneda del archivo difiere de la del catálogo en al menos un catálogo. Se usa la moneda
          del catálogo para comparar.
        </div>
      )}
      {preview.warnings.length > 0 && (
        <ul className="import-warnings" data-testid="import-warnings">
          {preview.warnings.map((w, i) => (
            <li key={i} className="meta">
              {w}
            </li>
          ))}
        </ul>
      )}

      <div className="import-tabs" data-testid="import-tabs" role="tablist">
        {catNames.map((name) => {
          const c = counts(preview.catalogs[name]);
          return (
            <div key={name} className={`import-tab${activeTab === name ? " active" : ""}`}>
              <input
                type="checkbox"
                checked={selected.has(name)}
                onChange={() => onToggleCatalog(name)}
                data-testid={`catalog-select-${name}`}
                aria-label={`Incluir ${name}`}
              />
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === name}
                onClick={() => onTab(name)}
                data-testid={`catalog-tab-${name}`}
              >
                <span className="mono">{name}</span>
                <span className="meta">
                  {c.updated} act · {c.new} nuevos · {c.zero_price} en $0
                </span>
              </button>
            </div>
          );
        })}
      </div>

      {active && <DiffTable diff={active} />}

      <label className="include-new" style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          type="checkbox"
          checked={includeNew}
          onChange={(e) => onIncludeNew(e.target.checked)}
          data-testid="include-new"
        />
        <span>Agregar ítems nuevos (no presentes hoy en el catálogo)</span>
      </label>

      <div className="config-actions" style={{ marginTop: 8 }}>
        <button
          type="button"
          className="btn primary"
          disabled={applyBlocked}
          onClick={onApply}
          data-testid="import-apply-btn"
        >
          Aplicar a {selected.size} {selected.size === 1 ? "catálogo" : "catálogos"}
        </button>
        {preview.iva_warning && (
          <span className="meta" style={{ color: "var(--error)" }}>
            Importación bloqueada por la columna CON IVA.
          </span>
        )}
      </div>
    </div>
  );
}

function DiffTable({ diff }: { diff: CatalogDiff }) {
  const c = counts(diff);
  return (
    <div className="diff-table" data-testid={`diff-table-${diff.catalog}`}>
      <div className="diff-counters">
        <span className="diff-badge updated">{c.updated} actualizados</span>
        <span className="diff-badge normalized">{c.normalized} normalizados</span>
        <span className="diff-badge new">{c.new} nuevos</span>
        <span className="diff-badge zero">{c.zero_price} en $0 (omitidos)</span>
        <span className="diff-badge missing">{c.missing} faltantes (no se borran)</span>
        <span className="diff-badge unchanged">{c.unchanged} sin cambios</span>
      </div>

      {diff.updated.length > 0 && (
        <details open>
          <summary>Actualizados ({diff.updated.length})</summary>
          <table>
            <thead>
              <tr>
                <th>SKU</th>
                <th>Nombre</th>
                <th>Antes</th>
                <th>Después</th>
                <th>Δ%</th>
              </tr>
            </thead>
            <tbody>
              {diff.updated.map((u) => (
                <tr key={u.sku} className={Math.abs(u.change_pct) > 30 ? "row-warn" : ""}>
                  <td className="mono">{u.sku}</td>
                  <td>{u.name}</td>
                  <td>{u.old_price}</td>
                  <td>{u.new_price}</td>
                  <td>{u.change_pct > 0 ? `+${u.change_pct}` : u.change_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {diff.new.length > 0 && (
        <details>
          <summary>Nuevos ({diff.new.length})</summary>
          <table>
            <thead>
              <tr>
                <th>SKU</th>
                <th>Nombre</th>
                <th>Precio</th>
              </tr>
            </thead>
            <tbody>
              {diff.new.map((n) => (
                <tr key={n.sku}>
                  <td className="mono">{n.sku}</td>
                  <td>{n.name}</td>
                  <td>{n.price}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {diff.zero_price.length > 0 && (
        <details>
          <summary>Precio $0 — omitidos ({diff.zero_price.length})</summary>
          <ul>
            {diff.zero_price.map((z) => (
              <li key={z.sku} className="mono">
                {z.sku} · {z.name}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/* ── Estado C · success ───────────────────────────────────────────── */

function SuccessState({
  result,
  onAnother,
}: {
  result: ImportApplyResponse;
  onAnother: () => void;
}) {
  const entries = Object.entries(result.results);
  return (
    <div className="col" data-testid="import-success">
      <div className="section-head">
        <h2>Importación aplicada</h2>
        <span className="meta">
          Archivo {result.source_file} · se generó un backup por catálogo antes de aplicar.
        </span>
      </div>

      <ul className="import-results">
        {entries.map(([name, r]) => (
          <li key={name} className="import-result-row" data-testid={`import-result-${name}`}>
            <Link href={`/catalogo/${encodeURIComponent(name)}`} className="mono">
              {name}
            </Link>
            {r.ok ? (
              <span className="meta">
                {r.updated ?? 0} actualizados · {r.normalized ?? 0} normalizados · {r.added ?? 0}{" "}
                nuevos · {r.skipped_zero ?? 0} en $0 omitidos
              </span>
            ) : (
              <span className="meta" style={{ color: "var(--error)" }}>
                {r.error}
              </span>
            )}
          </li>
        ))}
      </ul>

      <div className="config-actions" style={{ marginTop: 8 }}>
        <button type="button" className="btn ghost" onClick={onAnother} data-testid="import-another">
          Importar otro
        </button>
      </div>
    </div>
  );
}
