"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchCatalogs, fetchCatalog, validateCatalog, updateCatalog } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import clsx from "clsx";

interface CatalogMeta { name: string; item_count: number; last_updated: string | null; size_kb: number; }

const GROUPS = [
  { label: "Mano de obra", items: ["labor", "delivery-zones"] },
  { label: "Materiales", items: ["materials-silestone", "materials-purastone", "materials-dekton", "materials-neolith", "materials-puraprima", "materials-laminatto", "materials-granito-nacional", "materials-granito-importado", "materials-marmol"] },
  { label: "Piletas y otros", items: ["sinks", "stock", "architects", "config"] },
];

export default function ConfigPage() {
  const router = useRouter();
  const [catalogs, setCatalogs] = useState<CatalogMeta[]>([]);
  const [selected, setSelected] = useState("labor");
  const [content, setContent] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [validation, setValidation] = useState<{ valid: boolean; warnings: any[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const toast = useToast();

  useEffect(() => {
    fetchCatalogs().then(setCatalogs).catch((err: any) => {
      toast(err.message || "Error al cargar catálogos");
    });
  }, [toast]);

  useEffect(() => {
    setLoading(true); setValidation(null); setLoadError(null);
    fetchCatalog(selected).then(d => {
      const s = JSON.stringify(d, null, 2);
      setContent(s); setOriginalContent(s);
    }).catch((err: any) => {
      setLoadError(err.message || "Error al cargar catálogo");
    }).finally(() => setLoading(false));
  }, [selected]);

  const hasChanges = content !== originalContent;
  const meta = catalogs.find(c => c.name === selected);

  async function handleValidate() {
    setValidating(true);
    try {
      const parsed = JSON.parse(content);
      const result = await validateCatalog(selected, parsed);
      setValidation(result);
    } catch {
      setValidation({ valid: false, warnings: [{ type: "error", message: "JSON inválido — revisá la sintaxis" }] });
    } finally { setValidating(false); }
  }

  async function handleSave() {
    if (!validation?.valid) return;
    setSaving(true);
    try {
      await updateCatalog(selected, JSON.parse(content));
      setOriginalContent(content);
      setValidation(null);
      const updated = await fetchCatalogs();
      setCatalogs(updated);
      toast("Catálogo guardado correctamente", "success");
    } catch (err: any) {
      toast(err.message || "Error al guardar catálogo");
    } finally { setSaving(false); }
  }

  const disableValidate = !hasChanges || validating;
  const disableSave = !validation?.valid || saving || !hasChanges;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-7 pt-5 pb-[18px] border-b border-b1 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/")}
            className="w-[30px] h-[30px] rounded-md border border-b1 bg-transparent text-t2 cursor-pointer flex items-center justify-center transition hover:border-b2 hover:text-t1"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <div>
            <div className="text-lg font-medium -tracking-[0.03em]">Catálogo</div>
            <div className="text-[11px] text-t3 mt-0.5">Validación IA antes de guardar</div>
          </div>
        </div>
        <div className="flex gap-[7px]">
          <button
            onClick={handleValidate}
            disabled={disableValidate}
            className={clsx(
              "px-3 py-[7px] rounded-md text-xs font-medium font-sans border border-b1 bg-transparent text-t2 -tracking-[0.01em] transition",
              disableValidate ? "opacity-40 cursor-not-allowed" : "cursor-pointer hover:border-b2 hover:text-t1",
            )}
          >
            {validating ? "Validando..." : "Validar con IA"}
          </button>
          <button
            onClick={handleSave}
            disabled={disableSave}
            className={clsx(
              "px-3 py-[7px] rounded-md text-xs font-medium font-sans border bg-acc-bg border-acc-hover text-acc -tracking-[0.01em] transition",
              disableSave ? "opacity-40 cursor-not-allowed" : "cursor-pointer hover:bg-acc/20",
            )}
          >
            {saving ? "Guardando..." : "Guardar cambios"}
          </button>
        </div>
      </div>

      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Catalog list */}
        <div className="md:w-[200px] shrink-0 bg-s1 border-b md:border-b-0 md:border-r border-b1 px-2 py-2 md:py-3 overflow-x-auto md:overflow-x-hidden overflow-y-auto flex md:block gap-1 md:gap-0">
          {GROUPS.map(group => (
            <div key={group.label}>
              <div className="hidden md:block text-[10px] font-medium text-t4 uppercase tracking-[0.09em] px-2 pt-2 pb-1 mt-1.5">
                {group.label}
              </div>
              {group.items.map(name => {
                const m = catalogs.find(c => c.name === name);
                const isActive = selected === name;
                return (
                  <button
                    key={name}
                    onClick={() => setSelected(name)}
                    className={clsx(
                      "flex flex-col gap-0.5 p-2 rounded-md text-xs cursor-pointer border-none w-full md:w-full shrink-0 md:shrink text-left transition-all duration-100 font-sans whitespace-nowrap md:whitespace-normal",
                      isActive ? "text-acc bg-acc-bg" : "text-t2 bg-transparent hover:bg-white/[0.04]",
                    )}
                  >
                    {name}.json
                    <span className={clsx("text-[10px]", isActive ? "text-acc/55" : "text-t3")}>
                      {m ? `${m.item_count} ítems` : "\u2014"}
                      {m?.last_updated ? ` · ${m.last_updated}` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        {/* Editor */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-[22px] py-3 border-b border-b1 bg-black/[0.12] shrink-0">
            <div className="text-[13px] font-medium text-t1 flex items-center gap-2.5">
              {selected}.json
              {meta && (
                <span className="text-[10px] px-2 py-[2px] rounded-full font-medium bg-amb-bg text-amb border border-amb/[0.16]">
                  {meta.item_count} ítems{meta.last_updated ? ` · ${meta.last_updated}` : ""}
                </span>
              )}
              {validation?.valid && !hasChanges && (
                <span className="text-[10px] px-2 py-[2px] rounded-full font-medium bg-grn-bg text-grn border border-grn/[0.18]">
                  ✓ Válido
                </span>
              )}
            </div>
            <span className="text-[11px] text-t3">
              {hasChanges && !validation && "• Cambios sin guardar"}
              {validation?.valid && hasChanges && "✓ Validado"}
              {validation && !validation.valid && "✕ Error"}
            </span>
          </div>

          <div className="flex-1 px-[22px] py-4 flex flex-col gap-2.5 overflow-hidden">
            {validation && validation.warnings.length > 0 && (
              <div className="bg-amb/[0.06] border border-amb/[0.16] rounded-[7px] px-[13px] py-2.5 text-xs text-amb/85 flex gap-2">
                <span>⚠</span>
                <div>{validation.warnings.map((w: any, i: number) => (
                  <div key={i}>{w.sku && <strong>{w.sku}: </strong>}{w.message}</div>
                ))}</div>
              </div>
            )}
            <textarea
              value={loading ? "Cargando..." : loadError ? `Error: ${loadError}` : content}
              onChange={e => setContent(e.target.value)}
              disabled={loading}
              spellCheck={false}
              className="flex-1 bg-black/[0.28] border border-b1 rounded-lg p-3.5 font-mono text-xs text-t2 resize-none outline-none leading-[1.75] transition-[border-color] duration-150 focus:border-acc"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
