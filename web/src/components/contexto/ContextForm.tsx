/**
 * ContextForm — grid de los 11 campos del paso 2 (mockup 01-A / 02-B).
 *
 * Estructura:
 *   - section-head + botón "Abrir chat"
 *   - banner ia-banner (estado A) o muted (estado B con N editados)
 *   - 3 grupos (Cliente · Proyecto · Material) con .ctx-group-head
 *   - .etable.cols-220-1fr-140-60 con 1 .row por campo
 *   - confirm-bar inferior con CTA "Confirmar y continuar a despiece"
 */
"use client";

import { useRouter } from "next/navigation";
import type { ContextData, ContextResponse } from "@/lib/api";
import { ContextField } from "./ContextField";

export interface FieldDef {
  name: keyof ContextData;
  label: string;
  hint: string;
  type?: "text" | "boolean";
}

export interface Group {
  title: string;
  fields: FieldDef[];
}

// Exportado (Sprint 4 audit-copy-3-layer-state): fuente única de la
// estructura secciones/labels · el snapshot de [UI RENDER] del audit copy
// la reusa para garantizar que matchee el render real.
export const GROUPS: Group[] = [
  {
    title: "Cliente",
    fields: [
      { name: "cliente", label: "Cliente", hint: "arquitecta / razón social" },
      { name: "contacto", label: "Contacto", hint: "teléfono / email" },
      { name: "localidad", label: "Localidad", hint: "obra · ciudad" },
      { name: "plazo", label: "Plazo de entrega", hint: "desde confirmación de medidas" },
    ],
  },
  {
    title: "Proyecto",
    fields: [
      { name: "tipologia", label: "Tipología", hint: "cocina, baño, mesa, etc." },
      { name: "tipo_obra", label: "Tipo de obra", hint: "define colocación + flete" },
      { name: "material", label: "Material", hint: "piedra o engineered" },
    ],
  },
  {
    title: "Detalles",
    fields: [
      { name: "pileta", label: "Pileta", hint: "tipo + origen" },
      { name: "zocalo", label: "Zócalo", hint: "contra pared · si/no + alto" },
      { name: "regrueso", label: "Frentín / Regrueso", hint: "borde frontal grueso" },
      { name: "anafe", label: "Anafe", hint: "define MO ANAFE en paso 3", type: "boolean" },
    ],
  },
];

interface Props {
  quoteId: string;
  context: ContextResponse;
  briefSummary: string | null;
  isDirty: boolean;
  editedCount: number;
  saving: boolean;
  onUpdateField: <K extends keyof ContextData>(key: K, value: ContextData[K]) => void;
  onOpenChat: () => void;
  chatOpen: boolean;
}

export function ContextForm({
  quoteId,
  context,
  briefSummary,
  isDirty,
  editedCount,
  saving,
  onUpdateField,
  onOpenChat,
  chatOpen,
}: Props) {
  const router = useRouter();

  return (
    <div className="col" data-testid="context-form" data-state={isDirty ? "B" : "A"}>
      <div className="section-head">
        <div>
          <div className="meta">Paso 2 de 5 · Contexto</div>
          <h2>Contexto del presupuesto</h2>
        </div>
        <div className="right">
          {!chatOpen && (
            <button
              type="button"
              className="btn ghost"
              onClick={onOpenChat}
              data-testid="open-chat"
            >
              Abrir chat con Valentina
            </button>
          )}
        </div>
      </div>

      {/* Banner: cambia copy según pristine/dirty */}
      <div className={`ia-banner${isDirty ? " muted" : ""}`} data-testid="context-banner">
        <div className="vbubble" />
        <div className="text">
          {isDirty ? (
            <>
              <em>Marina</em> editó {editedCount} campo{editedCount === 1 ? "" : "s"}. Los cambios
              se aplican al cálculo del paso 3.
              <div className="sub">
                Click en cualquier campo para seguir editando · ✏ marca los editados
              </div>
            </>
          ) : (
            <>
              <em>Valentina</em> extrajo del brief:{" "}
              {briefSummary ?? "extraje los datos del brief — revisalos y editá lo que haga falta"}.
              Revisalo y editá lo que haga falta.
              <div className="sub">
                Click en cualquier campo para editar · Tab/Enter confirma · Esc cancela
              </div>
            </>
          )}
        </div>
      </div>

      {GROUPS.map((group) => (
        <div key={group.title}>
          <div className="ctx-group-head">
            <span>{group.title}</span>
            <span className="ctx-count">{group.fields.length} campos</span>
          </div>
          <div className="etable cols-220-1fr-140-60 mb-16">
            <div className="colh">
              <div>Campo</div>
              <div>Valor</div>
              <div>Origen</div>
              <div />
            </div>
            {group.fields.map((f) => (
              <ContextField
                key={f.name}
                name={f.name}
                label={f.label}
                hint={f.hint}
                type={f.type}
                field={context[f.name]}
                onCommit={(value) => onUpdateField(f.name, value as ContextData[typeof f.name])}
              />
            ))}
          </div>
        </div>
      ))}

      <div className="confirm-bar">
        <div className="summary">
          {saving ? (
            <span className="font-mono" style={{ fontSize: 12 }}>
              guardando…
            </span>
          ) : isDirty ? (
            <>
              <strong>{editedCount}</strong> campo{editedCount === 1 ? "" : "s"} editado
              {editedCount === 1 ? "" : "s"} · listo para despiece
            </>
          ) : (
            <>Contexto extraído por Valentina · listo para despiece</>
          )}
        </div>
        <button
          type="button"
          className="btn primary"
          data-testid="confirm-context"
          onClick={() => router.push(`/quotes/${quoteId}/despiece`)}
        >
          Confirmar y continuar a despiece →
        </button>
      </div>
    </div>
  );
}
