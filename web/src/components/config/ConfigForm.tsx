/**
 * ConfigForm · sub-PR 22.2.a config-ui-page.
 *
 * 6 defaults operativos editables:
 *   - default_depth (m · profundidad de mesada)
 *   - default_zocalo_height (m · BUG PROD FIX 0.07→0.05)
 *   - default_alzada_height (m)
 *   - colocacion_particulares (bool)
 *   - delivery_zone_sku (string · SKU de delivery-zones.json)
 *   - forma_pago (string)
 *
 * Flow: fetch initial blob → editable state local → "Guardar" abre diff
 * modal (solo si hay cambios) → onConfirm → PUT → badge "Guardado" 3s.
 *
 * Cero CSS nuevo en operator-shared.css. Scope CSS responsive vive en
 * globals.css bajo `.config-v2` (Step 6 · ~15-20 LOC media query).
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

interface FieldDef {
  key: keyof ConfigEditableFields;
  label: string;
  helper?: string;
  type: "number_m" | "text" | "bool";
  step?: string;
}

const FIELDS: FieldDef[] = [
  {
    key: "default_zocalo_height",
    label: "Alto de zócalo (m)",
    helper: "Default master D'Angelo = 5cm",
    type: "number_m",
    step: "0.01",
  },
  {
    key: "default_alzada_height",
    label: "Alto de alzada (m)",
    helper: "Default cuando brief no especifica = 60cm",
    type: "number_m",
    step: "0.01",
  },
  {
    key: "default_depth",
    label: "Profundidad de mesada (m)",
    helper: "Default 60cm cuando brief no aclara",
    type: "number_m",
    step: "0.01",
  },
  {
    key: "delivery_zone_sku",
    label: "Zona de flete por defecto (SKU)",
    helper: "SKU de delivery-zones.json · default ENVIOROS (Rosario)",
    type: "text",
  },
  {
    key: "forma_pago",
    label: "Forma de pago default",
    helper: "Texto que aparece en el PDF",
    type: "text",
  },
  {
    key: "colocacion_particulares",
    label: "Colocación incluida para particulares",
    helper: "Edificios siempre van sin colocación (regla aparte)",
    type: "bool",
  },
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

export function ConfigForm() {
  const [baseBlob, setBaseBlob] = useState<CatalogConfig | null>(null);
  const [original, setOriginal] = useState<ConfigEditableFields | null>(null);
  const [draft, setDraft] = useState<ConfigEditableFields | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [savedBadge, setSavedBadge] = useState(false);

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

  return (
    <form
      data-testid="config-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (hasChanges) setShowModal(true);
      }}
      style={{ display: "flex", flexDirection: "column", gap: 16 }}
    >
      <div className="config-fields-grid">
        {FIELDS.map((f) => {
          const val = draft[f.key];
          const id = `config-field-${f.key}`;
          return (
            <div
              key={f.key}
              data-testid={`config-row-${f.key}`}
              style={{ display: "flex", flexDirection: "column", gap: 4 }}
            >
              <label htmlFor={id} style={{ fontSize: 13, color: "var(--ink)", fontWeight: 500 }}>
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
              ) : f.type === "number_m" ? (
                <input
                  id={id}
                  data-testid={`config-input-${f.key}`}
                  className="input num"
                  type="number"
                  step={f.step}
                  min="0"
                  value={val as number}
                  onChange={(e) => handleField(f.key, Number(e.target.value) as never)}
                />
              ) : (
                <input
                  id={id}
                  data-testid={`config-input-${f.key}`}
                  className="input"
                  type="text"
                  value={val as string}
                  onChange={(e) => handleField(f.key, e.target.value as never)}
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
            </div>
          );
        })}
      </div>

      <div
        className="config-actions"
        style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}
      >
        <button
          type="submit"
          className="btn primary"
          disabled={!hasChanges}
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
