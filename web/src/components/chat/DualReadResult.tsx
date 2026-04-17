"use client";
import React, { useState } from "react";

interface FieldValue {
  opus?: number | null;
  sonnet?: number | null;
  valor: number;
  status: string;
}

interface Zocalo {
  lado: string;
  opus_ml?: number | null;
  sonnet_ml?: number | null;
  ml: number;
  alto_m: number;
  status: string;
}

interface Tramo {
  id: string;
  descripcion: string;
  largo_m: FieldValue;
  ancho_m: FieldValue;
  m2: FieldValue;
  zocalos: Zocalo[];
  frentin: unknown[];
  regrueso: unknown[];
}

type AmbiguedadTipo = "DEFAULT" | "INFO" | "REVISION";
type Ambiguedad = string | { tipo: AmbiguedadTipo; texto: string };

interface Sector {
  id: string;
  tipo: string;
  tramos: Tramo[];
  m2_total: FieldValue;
  ambiguedades: Ambiguedad[];
}

interface DualReadData {
  sectores: Sector[];
  requires_human_review: boolean;
  conflict_fields: string[];
  source: string;
  m2_warning?: string | null;
  _retry?: boolean;
}

interface Props {
  data: DualReadData;
  quoteId: string;
  onConfirm: (verified: DualReadData) => void;
  onRetry?: (newData: DualReadData) => void;
}

type IconStyle = { cls: string; char: string };
const STATUS_STYLE: Record<string, IconStyle> = {
  CONFIRMADO:   { cls: "bg-grn-bg text-grn",                        char: "✓" },
  ALERTA:       { cls: "bg-amb-bg text-amb",                        char: "!" },
  CONFLICTO:    { cls: "bg-[rgba(255,69,58,0.15)] text-err",        char: "✕" },
  DUDOSO:       { cls: "bg-[rgba(191,85,236,0.15)] text-[#bf55ec]", char: "?" },
  SOLO_SONNET:  { cls: "bg-grn-bg text-grn",                        char: "✓" },
  SOLO_OPUS:    { cls: "bg-grn-bg text-grn",                        char: "✓" },
};

const STATUS_TITLE: Record<string, string> = {
  CONFIRMADO: "Ambos lectores coincidieron",
  ALERTA: "Diferencia menor — se tomó el promedio",
  CONFLICTO: "Conflicto entre lectores — requiere revisión",
  DUDOSO: "Valor dudoso — requiere revisión",
  SOLO_SONNET: "Solo Sonnet detectó este valor",
  SOLO_OPUS: "Solo Opus detectó este valor",
};

function StatusIcon({
  status,
  onRemove,
}: {
  status: string;
  onRemove?: () => void;
}) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.CONFIRMADO;
  const baseCls = `inline-grid place-items-center w-[18px] h-[18px] rounded-[5px] text-[10px] font-bold ${s.cls}`;
  if (onRemove) {
    // PR #56 — la X de zócalos no confirmados ahora es clickeable para
    // remover el zócalo del despiece (caso típico: Dual Read sugirió un
    // zócalo por nicho visible, pero en realidad ese lado no lleva).
    return (
      <button
        type="button"
        onClick={onRemove}
        className={`${baseCls} cursor-pointer hover:opacity-80 hover:scale-110 transition-transform`}
        title="Remover este zócalo"
        aria-label="Remover este zócalo"
      >
        {s.char}
      </button>
    );
  }
  return (
    <span
      className={baseCls}
      title={STATUS_TITLE[status] || status}
      aria-label={STATUS_TITLE[status] || status}
    >
      {s.char}
    </span>
  );
}

function EditableNumber({
  field,
  onEdit,
}: {
  field: FieldValue;
  onEdit: (v: number) => void;
}) {
  const editable = field.status === "CONFLICTO" || field.status === "DUDOSO";
  if (!editable) return <>{field.valor.toFixed(2)}</>;
  return (
    <div className="inline-flex items-center gap-1.5 justify-end flex-wrap">
      {field.opus != null && (
        <button
          className="px-1.5 py-0.5 rounded text-[10px] border border-purple-400/30 text-purple-400 hover:bg-purple-400/10"
          onClick={() => onEdit(field.opus!)}
          title="Usar valor Opus"
        >
          O:{field.opus}
        </button>
      )}
      {field.sonnet != null && (
        <button
          className="px-1.5 py-0.5 rounded text-[10px] border border-blue-400/30 text-blue-400 hover:bg-blue-400/10"
          onClick={() => onEdit(field.sonnet!)}
          title="Usar valor Sonnet"
        >
          S:{field.sonnet}
        </button>
      )}
      <input
        type="number"
        step="0.01"
        defaultValue={field.valor}
        className="w-16 px-1.5 py-0.5 bg-s1 border border-b2 rounded text-[11px] text-t1 text-right font-mono"
        onChange={(e) => onEdit(parseFloat(e.target.value) || 0)}
      />
    </div>
  );
}

function EditableZocalo({
  z,
  onEdit,
}: {
  z: Zocalo;
  onEdit: (v: number) => void;
}) {
  const editable = z.status === "CONFLICTO" || z.status === "DUDOSO";
  if (!editable) return <>{z.ml.toFixed(2)}</>;
  return (
    <input
      type="number"
      step="0.01"
      defaultValue={z.ml}
      className="w-16 px-1.5 py-0.5 bg-s1 border border-b2 rounded text-[11px] text-t1 text-right font-mono"
      onChange={(e) => onEdit(parseFloat(e.target.value) || 0)}
    />
  );
}

export default function DualReadResult({ data, quoteId, onConfirm, onRetry }: Props) {
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [editedData, setEditedData] = useState<DualReadData>(data);

  const handleRetry = async () => {
    setRetrying(true);
    setRetryError(null);
    try {
      const res = await fetch(`/api/quotes/${quoteId}/dual-read-retry`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const newData = await res.json();
      if (onRetry) onRetry(newData);
    } catch (e: unknown) {
      setRetryError(e instanceof Error ? e.message : "Error");
    } finally {
      setRetrying(false);
    }
  };

  const updateField = (sectorIdx: number, tramoIdx: number, field: string, val: number) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const tramo = next.sectores[sectorIdx].tramos[tramoIdx];
      if (field.startsWith("zocalo_")) {
        const zIdx = parseInt(field.split("_")[1]);
        tramo.zocalos[zIdx].ml = val;
      } else {
        tramo[field].valor = val;
      }
      return next;
    });
  };

  // PR #56 — remover un zócalo del despiece (click en la X del StatusIcon).
  // Útil cuando Dual Read sugiere 3 zócalos por nicho visible pero en realidad
  // uno de los lados no lleva (ej: lateral abierto).
  const removeZocalo = (sectorIdx: number, tramoIdx: number, zIdx: number) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.sectores[sectorIdx].tramos[tramoIdx].zocalos.splice(zIdx, 1);
      return next;
    });
  };

  // PR #68 — remover una mesada (tramo) completa del despiece. Útil cuando
  // el Dual Read duplicó tramos (Opus y Sonnet disagree) o detectó
  // elementos ajenos (heladera, bajo mesada) como piezas.
  const removeTramo = (sectorIdx: number, tramoIdx: number) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.sectores[sectorIdx].tramos.splice(tramoIdx, 1);
      // Si el sector queda vacío, removerlo también.
      if (next.sectores[sectorIdx].tramos.length === 0) {
        next.sectores.splice(sectorIdx, 1);
      }
      return next;
    });
  };

  // Totals
  let mesadasM2 = 0;
  let zocalosM2 = 0;
  let piecesCount = 0;
  let zocalosCount = 0;
  editedData.sectores.forEach((s) =>
    s.tramos.forEach((t) => {
      mesadasM2 += t.m2.valor || 0;
      piecesCount += 1;
      t.zocalos.forEach((z) => {
        if ((z.ml || 0) > 0) {
          zocalosM2 += z.ml * (z.alto_m || 0);
          zocalosCount += 1;
        }
      });
    })
  );
  const totalM2 = mesadasM2 + zocalosM2;

  const allAmbiguedades = editedData.sectores.flatMap((s) => s.ambiguedades);
  const title =
    data.source === "DUAL" ? "Doble lectura del plano" : `Lectura ${data.source.replace("SOLO_", "")}`;
  const prettify = (s: string) =>
    s
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  const firstSectorHead = editedData.sectores[0]
    ? `${prettify(editedData.sectores[0].id)} — ${prettify(editedData.sectores[0].tipo)}`
    : "";

  return (
    <div className="my-2 w-full rounded-2xl border border-b1 bg-s1 overflow-hidden shadow-[0_20px_40px_-20px_rgba(0,0,0,0.5)]">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-4 bg-gradient-to-b from-s3 to-s2 border-b border-b1">
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-acc bg-acc-bg border border-acc/30 px-2 py-1 rounded-md">
          {data.source === "DUAL" ? "Doble lectura" : data.source.replace("SOLO_", "Solo ")}
        </span>
        <h3 className="text-[15px] font-semibold text-t1 tracking-tight">{firstSectorHead || title}</h3>
        <span className="ml-auto text-[12px] text-t3 font-mono">
          {piecesCount} {piecesCount === 1 ? "mesada" : "mesadas"} · {zocalosCount}{" "}
          {zocalosCount === 1 ? "zócalo" : "zócalos"}
        </span>
      </div>

      {data.m2_warning && (
        <div className="mx-5 mt-4 text-[12px] text-amb bg-amb-bg rounded-lg px-3 py-2 border border-amb/25">
          {data.m2_warning}
        </div>
      )}

      {/* Body: pieces + totals */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px]">
        {/* Pieces */}
        <div className="py-2 overflow-x-auto">
          {/* Column headers */}
          <div className="grid grid-cols-[22px_1fr_80px_80px_80px] gap-3 px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-t3 bg-s2 border-b border-b1">
            <span></span>
            <span>Pieza</span>
            <span className="text-right">Largo</span>
            <span className="text-right">Ancho</span>
            <span className="text-right">m²</span>
          </div>

          {editedData.sectores.map((sector, si) => (
            <div key={sector.id}>
              {editedData.sectores.length > 1 && (
                <div className="px-5 pt-3.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-t3">
                  {sector.id} — {sector.tipo}
                </div>
              )}

              {sector.tramos.map((tramo, ti) => (
                <React.Fragment key={tramo.id}>
                  {/* Mesada row */}
                  <div className="grid grid-cols-[22px_1fr_80px_80px_80px] items-center gap-3 px-5 py-2.5 text-[13px] font-mono tabular-nums border-t border-b1">
                    <StatusIcon status={tramo.largo_m.status} />
                    <div className="font-sans">
                      <div className="text-t1">{tramo.descripcion || tramo.id}</div>
                      <div className="text-[11px] text-t3 mt-0.5">mesada rectangular</div>
                    </div>
                    <div className="text-t2 text-right">
                      <EditableNumber field={tramo.largo_m} onEdit={(v) => updateField(si, ti, "largo_m", v)} />
                      <span className="text-t4 ml-0.5">m</span>
                    </div>
                    <div className="text-t2 text-right">
                      <EditableNumber field={tramo.ancho_m} onEdit={(v) => updateField(si, ti, "ancho_m", v)} />
                      <span className="text-t4 ml-0.5">m</span>
                    </div>
                    <div className="text-t1 font-medium text-right flex items-center justify-end gap-2">
                      <EditableNumber field={tramo.m2} onEdit={(v) => updateField(si, ti, "m2", v)} />
                      {/* PR #68 — botón × también en mesadas para remover duplicados
                          / piezas ajenas (heladera, bajo mesada) que el dual_read
                          detecta mal. */}
                      <button
                        type="button"
                        onClick={() => removeTramo(si, ti)}
                        title="Remover esta mesada"
                        aria-label="Remover esta mesada"
                        className="w-5 h-5 rounded-md grid place-items-center text-[11px] leading-none text-t4 hover:text-err hover:bg-[rgba(255,69,58,0.12)] border border-transparent hover:border-err/30 transition-colors cursor-pointer"
                      >
                        ×
                      </button>
                    </div>
                  </div>

                  {/* Zócalos rows — ocultar ml=0 salvo que requieran revisión */}
                  {tramo.zocalos.map((z, zi) => {
                    const hasMl = (z.ml ?? 0) > 0;
                    const needsReview = z.status === "CONFLICTO" || z.status === "DUDOSO";
                    if (!hasMl && !needsReview) return null;
                    return (
                      <div
                        key={zi}
                        className="group grid grid-cols-[22px_1fr_80px_80px_80px] items-center gap-3 px-5 py-2 text-[13px] font-mono tabular-nums border-t border-b1 relative"
                      >
                        <StatusIcon status={z.status} />
                        <div className="font-sans text-t2 pl-4 relative">
                          <span className="absolute left-0 top-1/2 w-2.5 h-px bg-b2" />
                          Zóc. {z.lado}
                        </div>
                        <div className="text-t2 text-right">
                          <EditableZocalo z={z} onEdit={(v) => updateField(si, ti, `zocalo_${zi}`, v)} />
                          <span className="text-t4 ml-0.5">ml</span>
                        </div>
                        <div className="text-t2 text-right">
                          {z.alto_m.toFixed(2)}
                          <span className="text-t4 ml-0.5">m</span>
                        </div>
                        <div className="text-t1 font-medium text-right flex items-center justify-end gap-2">
                          <span>{(z.ml * z.alto_m).toFixed(2)}</span>
                          {/* PR #61 — botón remover siempre disponible, independiente
                              del status (el operador confirma con el cliente si lleva
                              zócalos o no; Dual Read solo sugiere). Hover aumenta
                              contraste para descubribilidad. */}
                          <button
                            type="button"
                            onClick={() => removeZocalo(si, ti, zi)}
                            title="Remover este zócalo"
                            aria-label="Remover este zócalo"
                            className="w-5 h-5 rounded-md grid place-items-center text-[11px] leading-none text-t4 hover:text-err hover:bg-[rgba(255,69,58,0.12)] border border-transparent hover:border-err/30 transition-colors cursor-pointer"
                          >
                            ×
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </React.Fragment>
              ))}
            </div>
          ))}
        </div>

        {/* Totals */}
        <div className="border-t lg:border-t-0 lg:border-l border-b1 bg-gradient-to-b from-s2 to-s1 p-5">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-t3">Total a cortar</div>
          <div className="mt-1.5 text-[44px] leading-none font-semibold tracking-[-1px] font-mono tabular-nums text-t1">
            {totalM2.toFixed(2)}
            <span className="text-[16px] text-t2 font-medium ml-1 tracking-tight font-sans">m²</span>
          </div>
          <div className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-[12px] font-mono tabular-nums">
            <span className="text-t3 font-sans">
              Mesadas <span className="text-t4">({piecesCount})</span>
            </span>
            <span className="text-t1 text-right">{mesadasM2.toFixed(2)} m²</span>
            <span className="text-t3 font-sans">
              Zócalos <span className="text-t4">({zocalosCount})</span>
            </span>
            <span className="text-t1 text-right">{zocalosM2.toFixed(2)} m²</span>
          </div>
        </div>
      </div>

      {/* Alerts categorizadas */}
      {allAmbiguedades.length > 0 && (() => {
        const norm = allAmbiguedades.map((a) =>
          typeof a === "string" ? { tipo: "REVISION" as AmbiguedadTipo, texto: a } : a
        );
        const groups: Record<AmbiguedadTipo, string[]> = { REVISION: [], INFO: [], DEFAULT: [] };
        norm.forEach((a) => {
          const t = (a.tipo || "REVISION") as AmbiguedadTipo;
          (groups[t] || groups.REVISION).push(a.texto);
        });
        const META: Record<AmbiguedadTipo, { label: string; color: string; bg: string; border: string; dot: string }> = {
          REVISION: { label: "Revisar en plano",   color: "text-amb", bg: "bg-amb-bg",                      border: "border-amb/25",                      dot: "bg-amb" },
          INFO:     { label: "Falta dato",         color: "text-acc", bg: "bg-acc-bg",                      border: "border-acc/25",                      dot: "bg-acc" },
          DEFAULT:  { label: "Valores por default", color: "text-t2", bg: "bg-[rgba(255,255,255,0.03)]",    border: "border-b1",                          dot: "bg-t3" },
        };
        const order: AmbiguedadTipo[] = ["REVISION", "INFO", "DEFAULT"];
        return (
          <div className="mx-5 mb-4 flex flex-col gap-2">
            {order.map((t) =>
              groups[t].length === 0 ? null : (
                <div key={t} className={`p-3.5 ${META[t].bg} border ${META[t].border} rounded-xl`}>
                  <h4 className={`text-[11px] font-semibold uppercase tracking-[0.06em] ${META[t].color} mb-2`}>
                    {META[t].label}
                  </h4>
                  <ul className="flex flex-col gap-1.5">
                    {groups[t].map((text, i) => (
                      <li key={i} className="text-t2 text-[12px] leading-[1.5] pl-3.5 relative">
                        <span className={`absolute left-0 top-[9px] w-1 h-1 rounded-full ${META[t].dot}`} />
                        {text}
                      </li>
                    ))}
                  </ul>
                </div>
              )
            )}
          </div>
        );
      })()}

      {/* Retry if needed */}
      {data.source !== "DUAL" && !data._retry && (
        <div className="px-5 pb-3">
          <button
            className="w-full py-2.5 rounded-lg text-[12px] font-medium bg-orange-600/20 hover:bg-orange-600/30 border border-orange-600/40 text-orange-200 transition disabled:opacity-50"
            onClick={handleRetry}
            disabled={retrying}
          >
            {retrying ? "Consultando a Opus..." : "⚠️ Las medidas no coinciden — verificar con Opus"}
          </button>
          {retryError && <div className="text-[11px] text-err mt-1">{retryError}</div>}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 px-5 py-4 border-t border-b1 bg-s2">
        <button
          className="flex-1 py-2.5 px-4 rounded-xl text-[13px] font-semibold bg-acc hover:bg-acc-hover text-white transition"
          onClick={() => onConfirm(editedData)}
        >
          Confirmar medidas · {totalM2.toFixed(2)} m²
        </button>
      </div>
    </div>
  );
}
