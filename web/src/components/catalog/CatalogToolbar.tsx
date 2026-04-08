"use client";

import clsx from "clsx";

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

interface Props {
  catalogName: string;
  meta: CatalogMeta | undefined;
  hasChanges: boolean;
  validation: Validation | null;
  validating: boolean;
  saving: boolean;
  onValidate: () => void;
  onSave: () => void;
  onImport: () => void;
  onBack: () => void;
}

const IMPORTABLE = new Set([
  "labor", "delivery-zones", "architects", "sinks",
  "materials-silestone", "materials-purastone", "materials-dekton",
  "materials-neolith", "materials-puraprima", "materials-laminatto",
  "materials-granito-nacional", "materials-granito-importado", "materials-marmol",
]);

export default function CatalogToolbar({
  catalogName, meta, hasChanges, validation, validating, saving,
  onValidate, onSave, onImport, onBack,
}: Props) {
  const canImport = IMPORTABLE.has(catalogName);
  const disableValidate = !hasChanges || validating;
  const disableSave = !validation?.valid || saving || !hasChanges;

  return (
    <div className="flex flex-wrap md:flex-nowrap items-center justify-between px-3 md:px-5 py-2.5 md:py-3 border-b border-b1 bg-s1 shrink-0 gap-2 md:gap-3">
      {/* Left: back + title */}
      <div className="flex items-center gap-3 shrink-0">
        <button
          onClick={onBack}
          className="w-[30px] h-[30px] rounded-md border border-b1 bg-transparent text-t2 cursor-pointer flex items-center justify-center transition hover:border-b2 hover:text-t1"
          aria-label="Volver"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <div>
          <div className="text-[15px] font-medium text-t1 -tracking-[0.02em]">Catalogo</div>
          <div className="text-[10px] text-t3 mt-0.5">Validacion IA antes de guardar</div>
        </div>
      </div>

      {/* Center: filename + badges + status */}
      <div className="flex items-center gap-2.5 flex-1 justify-center min-w-0">
        <span className="text-[13px] font-medium text-t1 font-mono">{catalogName}.json</span>
        {meta && (
          <span className="text-[10px] px-2 py-[2px] rounded-full font-medium bg-white/[0.05] text-t3 border border-b1 shrink-0">
            {meta.item_count} items
          </span>
        )}
        {meta?.last_updated && (
          <span className="text-[10px] text-t4 shrink-0 hidden lg:inline">
            {meta.last_updated}
          </span>
        )}

        {/* Status indicator */}
        {hasChanges && !validation && (
          <span className="flex items-center gap-1 text-[10px] text-amb font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-amb" />
            Sin guardar
          </span>
        )}
        {validation?.valid && hasChanges && (
          <span className="flex items-center gap-1 text-[10px] text-grn font-medium">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
            Validado
          </span>
        )}
        {validation && !validation.valid && (
          <span className="flex items-center gap-1 text-[10px] text-err font-medium">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            Error
          </span>
        )}
      </div>

      {/* Right: action buttons */}
      <div className="flex items-center gap-2 shrink-0">
        {canImport && (
          <button
            onClick={onImport}
            className="flex items-center gap-1.5 px-3 py-[7px] rounded-md text-xs font-medium font-sans border border-b1 bg-transparent text-t2 -tracking-[0.01em] transition cursor-pointer hover:border-b2 hover:text-t1"
            aria-label="Importar datos"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            Importar
          </button>
        )}
        <button
          onClick={onValidate}
          disabled={disableValidate}
          className={clsx(
            "px-3 py-[7px] rounded-md text-xs font-medium font-sans border border-b1 bg-transparent text-t2 -tracking-[0.01em] transition",
            disableValidate ? "opacity-40 cursor-not-allowed" : "cursor-pointer hover:border-b2 hover:text-t1",
          )}
        >
          {validating ? "Validando..." : "Validar con IA"}
        </button>
        <button
          onClick={onSave}
          disabled={disableSave}
          className={clsx(
            "px-3 py-[7px] rounded-md text-xs font-medium font-sans border bg-acc-bg border-acc-hover text-acc -tracking-[0.01em] transition",
            disableSave ? "opacity-40 cursor-not-allowed" : "cursor-pointer hover:bg-acc/20",
          )}
        >
          {saving ? "Guardando..." : "Guardar"}
        </button>
      </div>
    </div>
  );
}
