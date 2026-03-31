"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchCatalogs, fetchCatalog, validateCatalog, updateCatalog } from "@/lib/api";

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

  useEffect(() => { fetchCatalogs().then(setCatalogs).catch(console.error); }, []);

  useEffect(() => {
    setLoading(true); setValidation(null);
    fetchCatalog(selected).then(d => {
      const s = JSON.stringify(d, null, 2);
      setContent(s); setOriginalContent(s);
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
    } finally { setSaving(false); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "20px 28px 18px", borderBottom: "1px solid var(--b1)", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <button onClick={() => router.push("/")} style={backStyle}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <div>
            <div style={{ fontSize: 18, fontWeight: 500, letterSpacing: "-0.03em" }}>Catálogo</div>
            <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 2 }}>Validación IA antes de guardar</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 7 }}>
          <button onClick={handleValidate} disabled={!hasChanges || validating} style={btnStyle(!hasChanges || validating)}>
            {validating ? "Validando..." : "Validar con IA"}
          </button>
          <button onClick={handleSave} disabled={!validation?.valid || saving || !hasChanges} style={{
            ...btnStyle(!validation?.valid || saving || !hasChanges),
            background: "var(--acc2)", borderColor: "var(--acc3)", color: "var(--acc)",
          }}>
            {saving ? "Guardando..." : "Guardar cambios"}
          </button>
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Catalog list */}
        <div style={{
          width: 200, flexShrink: 0,
          background: "var(--s1)", borderRight: "1px solid var(--b1)",
          padding: "12px 8px", overflowY: "auto",
        }}>
          {GROUPS.map(group => (
            <div key={group.label}>
              <div style={{ fontSize: 10, fontWeight: 500, color: "var(--t4)", textTransform: "uppercase", letterSpacing: "0.09em", padding: "8px 8px 4px", marginTop: 6 }}>
                {group.label}
              </div>
              {group.items.map(name => {
                const m = catalogs.find(c => c.name === name);
                return (
                  <button key={name} onClick={() => setSelected(name)} style={{
                    display: "flex", flexDirection: "column", gap: 2,
                    padding: 8, borderRadius: 6, fontSize: 12,
                    color: selected === name ? "var(--acc)" : "var(--t2)",
                    cursor: "pointer", border: "none", width: "100%", textAlign: "left",
                    background: selected === name ? "var(--acc2)" : "transparent",
                    transition: "all .1s", fontFamily: "inherit",
                  }}>
                    {name}.json
                    <span style={{ fontSize: 10, color: selected === name ? "rgba(79,143,255,.55)" : "var(--t3)" }}>
                      {m ? `${m.item_count} ítems` : "—"}
                      {m?.last_updated ? ` · ${m.last_updated}` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        {/* Editor */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "12px 22px", borderBottom: "1px solid var(--b1)",
            background: "rgba(0,0,0,.12)", flexShrink: 0,
          }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--t1)", display: "flex", alignItems: "center", gap: 9 }}>
              {selected}.json
              {meta && (
                <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999, fontWeight: 500, background: "var(--amb2)", color: "var(--amb)", border: "1px solid rgba(245,166,35,.16)" }}>
                  {meta.item_count} ítems{meta.last_updated ? ` · ${meta.last_updated}` : ""}
                </span>
              )}
              {validation?.valid && !hasChanges && (
                <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999, fontWeight: 500, background: "var(--grn2)", color: "var(--grn)", border: "1px solid rgba(48,209,88,.18)" }}>✓ Válido</span>
              )}
            </div>
            <span style={{ fontSize: 11, color: "var(--t3)" }}>
              {hasChanges && !validation && "• Cambios sin guardar"}
              {validation?.valid && hasChanges && "✓ Validado"}
              {validation && !validation.valid && "✕ Error"}
            </span>
          </div>

          <div style={{ flex: 1, padding: "16px 22px", display: "flex", flexDirection: "column", gap: 10, overflow: "hidden" }}>
            {validation && validation.warnings.length > 0 && (
              <div style={{
                background: "rgba(245,166,35,.06)", border: "1px solid rgba(245,166,35,.16)",
                borderRadius: 7, padding: "10px 13px",
                fontSize: 12, color: "rgba(245,166,35,.85)", display: "flex", gap: 8,
              }}>
                <span>⚠</span>
                <div>{validation.warnings.map((w, i) => (
                  <div key={i}>{w.sku && <strong>{w.sku}: </strong>}{w.message}</div>
                ))}</div>
              </div>
            )}
            <textarea
              value={loading ? "Cargando..." : content}
              onChange={e => setContent(e.target.value)}
              disabled={loading}
              spellCheck={false}
              style={{
                flex: 1, background: "rgba(0,0,0,.28)", border: "1px solid var(--b1)",
                borderRadius: 8, padding: 14,
                fontFamily: "'Geist Mono', monospace", fontSize: 12,
                color: "var(--t2)", resize: "none", outline: "none", lineHeight: 1.75,
                transition: "border-color .15s",
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

const backStyle: React.CSSProperties = {
  width: 30, height: 30, borderRadius: 6,
  border: "1px solid var(--b1)", background: "transparent",
  color: "var(--t2)", cursor: "pointer",
  display: "flex", alignItems: "center", justifyContent: "center",
  transition: "all .1s",
};

const btnStyle = (disabled: boolean): React.CSSProperties => ({
  padding: "7px 13px", borderRadius: 6,
  fontSize: 12, fontWeight: 500, fontFamily: "inherit",
  cursor: disabled ? "not-allowed" : "pointer",
  border: "1px solid var(--b1)", background: "transparent",
  color: "var(--t2)", letterSpacing: "-0.01em",
  opacity: disabled ? 0.4 : 1, transition: "all .1s",
});
