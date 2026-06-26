/**
 * Sprint 4 derive-material-ui-wire · botón + modal en Topbar.
 *
 * Acción "Recotizar con otro material" · clona la quote actual con un
 * material distinto. Backend POST /api/quotes/{id}/derive-material
 * (router.py:1363 · ya cableado) recalcula con `calculate_quote` completo
 * (latencia ~3-5s) · devuelve `quote_id` de la nueva quote DRAFT.
 *
 * Guard de habilitación: deshabilitado mientras la quote no tenga material
 * asignado (proxy de "tiene contenido cotizable"). Backend valida fuerte
 * (400 si no hay pieces) · este guard es UX-only para evitar disparos
 * innecesarios.
 *
 * Modal: `<dialog>` nativo HTML + estilos inline (mismo pattern que
 * AuditToggle · cero CSS file separado · cero componente Modal genérico
 * disponible en este momento).
 *
 * Dropdown: 1-step flat con `<optgroup>` por marca. Los 9 catálogos de
 * materiales se cargan lazy en paralelo al abrir el modal (no al montar
 * el botón).
 */
"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  deriveMaterialForQuote,
  getMaterialsList,
  type MaterialOption,
} from "@/lib/api";

interface Props {
  quoteId: string;
  /** Display string del material actual · si vacío o "—" el botón se
   * deshabilita (la quote no tiene contenido para recotizar). */
  currentMaterial?: string | null;
}

function _isDerivableMaterial(m: string | null | undefined): boolean {
  if (!m) return false;
  const t = m.trim();
  if (!t || t === "—") return false;
  return true;
}

function _groupByBrand(materials: MaterialOption[]): Map<string, MaterialOption[]> {
  const groups = new Map<string, MaterialOption[]>();
  for (const m of materials) {
    const existing = groups.get(m.brand) ?? [];
    existing.push(m);
    groups.set(m.brand, existing);
  }
  return groups;
}

export function DeriveMaterialButton({ quoteId, currentMaterial }: Props) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [materials, setMaterials] = useState<MaterialOption[] | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [selected, setSelected] = useState<string>("");
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEnabled = _isDerivableMaterial(currentMaterial);
  const groups = useMemo(() => _groupByBrand(materials ?? []), [materials]);

  async function handleOpen() {
    setError(null);
    setSelected("");
    dialogRef.current?.showModal();
    if (!materials) {
      setLoadingList(true);
      try {
        const list = await getMaterialsList();
        setMaterials(list);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar materiales");
      } finally {
        setLoadingList(false);
      }
    }
  }

  function handleClose() {
    if (confirming) return;
    dialogRef.current?.close();
    setError(null);
  }

  async function handleConfirm() {
    if (!selected) return;
    setConfirming(true);
    setError(null);
    try {
      const result = await deriveMaterialForQuote(quoteId, selected);
      dialogRef.current?.close();
      router.push(`/quotes/${result.quote_id}/contexto`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al recotizar");
      setConfirming(false);
    }
  }

  const buttonTitle = isEnabled
    ? "Recotizar con otro material"
    : "Disponible cuando la quote tenga material cotizado";

  return (
    <>
      <button
        type="button"
        className="audit-toggle"
        onClick={handleOpen}
        disabled={!isEnabled}
        data-testid="derive-material-trigger"
        title={buttonTitle}
        style={{
          padding: "5px 10px",
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--r-sm)",
          background: "transparent",
          color: isEnabled ? "var(--ink)" : "var(--ink-mute)",
          fontFamily: "var(--mono)",
          fontSize: 11,
          cursor: isEnabled ? "pointer" : "not-allowed",
          opacity: isEnabled ? 1 : 0.5,
        }}
      >
        Recotizar con otro material
      </button>

      <dialog
        ref={dialogRef}
        data-testid="derive-material-dialog"
        style={{
          padding: 0,
          border: "1px solid var(--line-strong)",
          borderRadius: "var(--r-md)",
          background: "var(--surface)",
          color: "var(--ink)",
          maxWidth: 480,
          width: "90%",
        }}
        onCancel={handleClose}
      >
        <div style={{ padding: "20px 24px" }}>
          <h3 style={{ margin: "0 0 6px 0", fontSize: 16 }}>Recotizar con otro material</h3>
          <p style={{ margin: "0 0 16px 0", fontSize: 13, color: "var(--ink-mute)" }}>
            Crea una nueva quote DRAFT con las mismas piezas y cliente, recalculada con el material elegido.
          </p>

          <label
            htmlFor="derive-material-select"
            style={{ display: "block", fontSize: 12, color: "var(--ink-mute)", marginBottom: 6 }}
          >
            Material para la nueva cotización
          </label>
          <select
            id="derive-material-select"
            data-testid="derive-material-select"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={loadingList || confirming || !materials}
            style={{
              width: "100%",
              padding: "8px 10px",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--r-sm)",
              background: "var(--surface-2)",
              color: "var(--ink)",
              fontSize: 13,
            }}
          >
            <option value="">
              {loadingList ? "Cargando materiales…" : "— Elegir material —"}
            </option>
            {Array.from(groups.entries()).map(([brand, items]) => (
              <optgroup key={brand} label={brand.toUpperCase()}>
                {items.map((item) => (
                  <option key={`${item.brand}-${item.sku || item.name}`} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>

          {error && (
            <div
              data-testid="derive-material-error"
              style={{
                marginTop: 12,
                padding: "8px 10px",
                background: "var(--surface-2)",
                border: "1px solid var(--color-error, #c33)",
                borderRadius: "var(--r-sm)",
                color: "var(--color-error, #c33)",
                fontSize: 12,
              }}
            >
              {error}
            </div>
          )}

          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 8,
              marginTop: 20,
            }}
          >
            <button
              type="button"
              onClick={handleClose}
              disabled={confirming}
              data-testid="derive-material-cancel"
              style={{
                padding: "6px 12px",
                border: "1px solid var(--line-strong)",
                borderRadius: "var(--r-sm)",
                background: "transparent",
                color: "var(--ink)",
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={!selected || confirming || loadingList}
              data-testid="derive-material-confirm"
              style={{
                padding: "6px 12px",
                border: "1px solid var(--line-strong)",
                borderRadius: "var(--r-sm)",
                background: "var(--ink)",
                color: "var(--surface)",
                fontSize: 13,
                cursor: !selected || confirming || loadingList ? "not-allowed" : "pointer",
                opacity: !selected || confirming || loadingList ? 0.5 : 1,
              }}
            >
              {confirming ? "Recotizando…" : "Recotizar"}
            </button>
          </div>
        </div>
      </dialog>
    </>
  );
}
