/**
 * ConfigForm · sub-PR 22.2.a config-ui-page + 22.2.a.III expansion.
 *
 * Fields editables agrupados en 4 secciones colapsables:
 *
 *  1. DEFAULTS DE MESADA (3 · default expanded · sub-PR 22.2.a)
 *     - default_zocalo_height, default_alzada_height, default_depth
 *
 *  2. DEFAULTS OPERATIVOS (3 · default expanded · sub-PR 22.2.a)
 *     - colocacion_particulares, delivery_zone_sku, forma_pago
 *
 *  3. DESCUENTOS (5 · default collapsed · sub-PR 22.2.a.III)
 *     - discount.imported_percentage, national_percentage, building_percentage
 *     - discount.building_min_m2_threshold, min_m2_threshold
 *
 *  4. COSTING (1 · default collapsed · sub-PR 22.2.a.III)
 *     - merma.small_piece_threshold_m2
 *
 * Flow: fetch initial blob → editable state local → "Guardar" abre diff
 * modal (solo si hay cambios) → onConfirm → PUT → badge "Guardado" 3s.
 *
 * Cero CSS nuevo en operator-shared.css. Scope responsive vive en
 * globals.css bajo `.config-v2` (~15-20 LOC media query · lección #66).
 */
"use client";

import { useEffect, useState } from "react";
import {
  applyEditableFields,
  extractEditableFields,
  type CatalogConfig,
  type ConfigEditableFields,
} from "@/lib/api/types";
import { getCatalogConfig, updateCatalogConfig } from "@/lib/api";
import { ConfigDiffModal, type DiffRow } from "./ConfigDiffModal";

type SectionId = "mesada" | "operativos" | "descuentos" | "costing";

interface FieldDef {
  key: keyof ConfigEditableFields;
  label: string;
  helper?: string;
  type: "number_m" | "number" | "percent" | "text" | "bool";
  step?: string;
  min?: number;
  max?: number;
  section: SectionId;
}

const FIELDS: FieldDef[] = [
  // ─── Sección 1 · DEFAULTS DE MESADA ────────────────────────────────
  {
    key: "default_zocalo_height",
    label: "Alto de zócalo (m)",
    helper: "Default master D'Angelo = 5cm",
    type: "number_m",
    step: "0.01",
    section: "mesada",
  },
  {
    key: "default_alzada_height",
    label: "Alto de alzada (m)",
    helper: "Default cuando brief no especifica = 60cm",
    type: "number_m",
    step: "0.01",
    section: "mesada",
  },
  {
    key: "default_depth",
    label: "Profundidad de mesada (m)",
    helper: "Default 60cm cuando brief no aclara",
    type: "number_m",
    step: "0.01",
    section: "mesada",
  },
  // ─── Sección 2 · DEFAULTS OPERATIVOS ───────────────────────────────
  {
    key: "delivery_zone_sku",
    label: "Zona de flete por defecto (SKU)",
    helper: "SKU de delivery-zones.json · default ENVIOROS (Rosario)",
    type: "text",
    section: "operativos",
  },
  {
    key: "forma_pago",
    label: "Forma de pago default",
    helper: "Texto que aparece en el PDF",
    type: "text",
    section: "operativos",
  },
  {
    key: "colocacion_particulares",
    label: "Colocación incluida para particulares",
    helper: "Edificios siempre van sin colocación (regla aparte)",
    type: "bool",
    section: "operativos",
  },
  // ─── Sección 3 · DESCUENTOS (sub-PR 22.2.a.III) ────────────────────
  {
    key: "discount_imported_percentage",
    label: "Descuento material importado %",
    helper:
      "Este % aplica tanto al descuento arquitecto como al descuento cantidad por volumen, según moneda del material.",
    type: "percent",
    step: "0.5",
    min: 0,
    max: 50,
    section: "descuentos",
  },
  {
    key: "discount_national_percentage",
    label: "Descuento material nacional %",
    helper:
      "Este % aplica tanto al descuento arquitecto como al descuento cantidad por volumen, según moneda del material.",
    type: "percent",
    step: "0.5",
    min: 0,
    max: 50,
    section: "descuentos",
  },
  {
    key: "discount_building_percentage",
    label: "Descuento edificio %",
    helper: "Aplicado cuando es_edificio=true Y m² ≥ Edificio mínimo m².",
    type: "percent",
    step: "0.5",
    min: 0,
    max: 50,
    section: "descuentos",
  },
  {
    key: "discount_building_min_m2_threshold",
    label: "Edificio mínimo m²",
    helper: "Umbral para que el descuento edificio se aplique automáticamente.",
    type: "number",
    step: "1",
    min: 0,
    max: 100,
    section: "descuentos",
  },
  {
    key: "discount_min_m2_threshold",
    label: "Cantidad mínimo m² (no-arquitecto/no-edificio)",
    helper:
      "Umbral para que el descuento por cantidad se aplique automáticamente (regla > 6m² · 4to tier · sub-PR #494).",
    type: "number",
    step: "1",
    min: 0,
    max: 100,
    section: "descuentos",
  },
  // ─── Sección 4 · COSTING (sub-PR 22.2.a.III) ───────────────────────
  {
    key: "merma_small_piece_threshold_m2",
    label: "Umbral merma (m²)",
    helper: "Piezas por debajo de este umbral se consideran retazos a efectos de merma.",
    type: "number",
    step: "0.1",
    min: 0,
    max: 10,
    section: "costing",
  },
];

const SECTIONS: { id: SectionId; title: string; defaultOpen: boolean }[] = [
  { id: "mesada", title: "Defaults de mesada", defaultOpen: true },
  { id: "operativos", title: "Defaults operativos", defaultOpen: true },
  { id: "descuentos", title: "Descuentos", defaultOpen: false },
  { id: "costing", title: "Costing", defaultOpen: false },
];

function formatValue(key: keyof ConfigEditableFields, value: unknown): string {
  if (typeof value === "boolean") return value ? "sí" : "no";
  if (
    key === "default_depth" ||
    key === "default_zocalo_height" ||
    key === "default_alzada_height"
  ) {
    return `${(value as number).toFixed(2)} m`;
  }
  const def = FIELDS.find((f) => f.key === key);
  if (def?.type === "percent") return `${value}%`;
  if (def?.type === "number") return String(value);
  return String(value);
}

function diffRows(prev: ConfigEditableFields, next: ConfigEditableFields): DiffRow[] {
  const rows: DiffRow[] = [];
  for (const f of FIELDS) {
    if (prev[f.key] !== next[f.key]) {
      rows.push({
        label: f.label,
        before: formatValue(f.key, prev[f.key]),
        after: formatValue(f.key, next[f.key]),
      });
    }
  }
  return rows;
}

function isOutOfRange(field: FieldDef, value: number): boolean {
  if (field.min !== undefined && value < field.min) return true;
  if (field.max !== undefined && value > field.max) return true;
  return false;
}

export function ConfigForm() {
  const [baseBlob, setBaseBlob] = useState<CatalogConfig | null>(null);
  const [original, setOriginal] = useState<ConfigEditableFields | null>(null);
  const [draft, setDraft] = useState<ConfigEditableFields | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [savedBadge, setSavedBadge] = useState(false);
  const [openSections, setOpenSections] = useState<Record<SectionId, boolean>>(() =>
    SECTIONS.reduce(
      (acc, s) => ({ ...acc, [s.id]: s.defaultOpen }),
      {} as Record<SectionId, boolean>,
    ),
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const blob = await getCatalogConfig();
        if (cancelled) return;
        const edits = extractEditableFields(blob);
        setBaseBlob(blob);
        setOriginal(edits);
        setDraft(edits);
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Error desconocido");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!savedBadge) return;
    const t = setTimeout(() => setSavedBadge(false), 3000);
    return () => clearTimeout(t);
  }, [savedBadge]);

  if (loadError) {
    return (
      <div data-testid="config-load-error" role="alert" style={{ color: "var(--error)" }}>
        No pude cargar la configuración: {loadError}
      </div>
    );
  }

  if (!draft || !original || !baseBlob) {
    return (
      <div data-testid="config-loading" style={{ color: "var(--ink-mute)" }}>
        Cargando configuración…
      </div>
    );
  }

  const rowsToDiff = diffRows(original, draft);
  const hasChanges = rowsToDiff.length > 0;

  // Validación: bloquear guardar si algún número quedó fuera de rango.
  const hasInvalid = FIELDS.some((f) => {
    if (f.type !== "number" && f.type !== "percent" && f.type !== "number_m") return false;
    const v = draft[f.key];
    if (typeof v !== "number" || !Number.isFinite(v)) return true;
    return isOutOfRange(f, v);
  });

  const handleField = <K extends keyof ConfigEditableFields>(
    key: K,
    value: ConfigEditableFields[K],
  ) => {
    setDraft((d) => (d ? { ...d, [key]: value } : d));
  };

  const handleReset = () => {
    setDraft(original);
  };

  const handleSubmit = async () => {
    if (!baseBlob || !draft) return;
    const nextBlob = applyEditableFields(baseBlob, draft);
    await updateCatalogConfig(nextBlob);
    setBaseBlob(nextBlob);
    setOriginal(draft);
    setShowModal(false);
    setSavedBadge(true);
  };

  const toggleSection = (id: SectionId) => {
    setOpenSections((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <form
      data-testid="config-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (hasChanges && !hasInvalid) setShowModal(true);
      }}
      style={{ display: "flex", flexDirection: "column", gap: 16 }}
    >
      {SECTIONS.map((section) => {
        const fields = FIELDS.filter((f) => f.section === section.id);
        const isOpen = openSections[section.id];
        return (
          <section
            key={section.id}
            className="config-section"
            data-testid={`config-section-${section.id}`}
            data-open={isOpen ? "true" : "false"}
          >
            <button
              type="button"
              className="config-section-header"
              data-testid={`config-section-toggle-${section.id}`}
              aria-expanded={isOpen}
              onClick={() => toggleSection(section.id)}
            >
              <span className="config-section-chevron" aria-hidden="true">
                {isOpen ? "▼" : "▶"}
              </span>
              <span className="config-section-title">{section.title}</span>
              <span className="config-section-count">{fields.length}</span>
            </button>
            {isOpen && (
              <div className="config-fields-grid">
                {fields.map((f) => {
                  const val = draft[f.key];
                  const id = `config-field-${f.key}`;
                  const isNum =
                    f.type === "number" || f.type === "percent" || f.type === "number_m";
                  const numVal = val as number;
                  const outOfRange =
                    isNum && (typeof numVal !== "number" || isOutOfRange(f, numVal));
                  return (
                    <div
                      key={f.key}
                      data-testid={`config-row-${f.key}`}
                      style={{ display: "flex", flexDirection: "column", gap: 4 }}
                    >
                      <label
                        htmlFor={id}
                        style={{ fontSize: 13, color: "var(--ink)", fontWeight: 500 }}
                      >
                        {f.label}
                      </label>
                      {f.type === "bool" ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <input
                            id={id}
                            data-testid={`config-input-${f.key}`}
                            type="checkbox"
                            checked={val as boolean}
                            onChange={(e) => handleField(f.key, e.target.checked as never)}
                          />
                          <span style={{ fontSize: 13, color: "var(--ink-mute)" }}>
                            {(val as boolean) ? "Activada" : "Desactivada"}
                          </span>
                        </div>
                      ) : f.type === "text" ? (
                        <input
                          id={id}
                          data-testid={`config-input-${f.key}`}
                          className="input"
                          type="text"
                          value={val as string}
                          onChange={(e) => handleField(f.key, e.target.value as never)}
                        />
                      ) : (
                        <input
                          id={id}
                          data-testid={`config-input-${f.key}`}
                          className="input num"
                          type="number"
                          step={f.step ?? "1"}
                          min={f.min ?? 0}
                          max={f.max}
                          value={val as number}
                          onChange={(e) => handleField(f.key, Number(e.target.value) as never)}
                          aria-invalid={outOfRange ? "true" : "false"}
                        />
                      )}
                      {f.helper && (
                        <span
                          data-testid={`config-helper-${f.key}`}
                          style={{ fontSize: 11, color: "var(--ink-mute)" }}
                        >
                          {f.helper}
                        </span>
                      )}
                      {outOfRange && (
                        <span
                          data-testid={`config-error-${f.key}`}
                          role="alert"
                          style={{ fontSize: 11, color: "var(--error)" }}
                        >
                          Valor fuera de rango ({f.min ?? 0}–{f.max ?? "∞"})
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        );
      })}

      <div
        className="config-actions"
        style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}
      >
        <button
          type="submit"
          className="btn primary"
          disabled={!hasChanges || hasInvalid}
          data-testid="config-save"
        >
          Guardar
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={!hasChanges}
          onClick={handleReset}
          data-testid="config-reset"
        >
          Descartar
        </button>
        {savedBadge && (
          <span
            data-testid="config-saved-badge"
            role="status"
            style={{ fontSize: 12, color: "var(--ok, #4ade80)" }}
          >
            ✓ Guardado · aplicará a próximos presupuestos (puede tardar unos segundos en producción)
          </span>
        )}
      </div>

      {showModal && (
        <ConfigDiffModal
          rows={rowsToDiff}
          onCancel={() => setShowModal(false)}
          onConfirm={handleSubmit}
        />
      )}
    </form>
  );
}
