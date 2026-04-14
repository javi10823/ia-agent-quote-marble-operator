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

interface Sector {
  id: string;
  tipo: string;
  tramos: Tramo[];
  m2_total: FieldValue;
  ambiguedades: string[];
}

interface DualReadData {
  sectores: Sector[];
  requires_human_review: boolean;
  conflict_fields: string[];
  source: string;
  m2_warning?: string | null;
}

interface Props {
  data: DualReadData;
  onConfirm: (verified: DualReadData) => void;
}

const STATUS_ICONS: Record<string, string> = {
  CONFIRMADO: "\u2705",
  ALERTA: "\u26A0\uFE0F",
  CONFLICTO: "\u274C",
  DUDOSO: "\uD83D\uDFE0",
  SOLO_SONNET: "\uD83D\uDD35",
  SOLO_OPUS: "\uD83D\uDFE3",
};

const STATUS_COLORS: Record<string, string> = {
  CONFIRMADO: "text-green-400",
  ALERTA: "text-yellow-400",
  CONFLICTO: "text-red-400",
  DUDOSO: "text-orange-400",
  SOLO_SONNET: "text-blue-400",
  SOLO_OPUS: "text-purple-400",
};

function FieldRow({ label, field, onEdit }: {
  label: string;
  field: FieldValue;
  onEdit?: (val: number) => void;
}) {
  const icon = STATUS_ICONS[field.status] || "";
  const color = STATUS_COLORS[field.status] || "text-t2";
  const editable = field.status === "CONFLICTO" || field.status === "DUDOSO";

  return (
    <div className="flex items-center gap-2 py-1 px-2 text-[13px]">
      <span className="w-5 text-center">{icon}</span>
      <span className="text-t3 w-24 shrink-0">{label}</span>
      {editable ? (
        <div className="flex gap-2 items-center">
          {field.opus != null && (
            <button
              className="px-2 py-0.5 rounded text-xs border border-purple-400/30 text-purple-400 hover:bg-purple-400/10"
              onClick={() => onEdit?.(field.opus!)}
            >
              Opus: {field.opus}
            </button>
          )}
          {field.sonnet != null && (
            <button
              className="px-2 py-0.5 rounded text-xs border border-blue-400/30 text-blue-400 hover:bg-blue-400/10"
              onClick={() => onEdit?.(field.sonnet!)}
            >
              Sonnet: {field.sonnet}
            </button>
          )}
          <input
            type="number"
            step="0.01"
            defaultValue={field.valor}
            className="w-20 px-1.5 py-0.5 bg-s1 border border-b2 rounded text-xs text-t1"
            onChange={(e) => onEdit?.(parseFloat(e.target.value) || 0)}
          />
        </div>
      ) : (
        <span className={`${color} font-medium`}>
          {field.valor}m
          {field.status === "ALERTA" && " (promedio)"}
        </span>
      )}
    </div>
  );
}

export default function DualReadResult({ data, onConfirm }: Props) {
  const [editedData, setEditedData] = useState<DualReadData>(data);

  const updateField = (sectorIdx: number, tramoIdx: number, field: string, val: number) => {
    setEditedData(prev => {
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

  return (
    <div className="rounded-[10px] border border-b1 bg-s2 p-3 my-2 max-w-lg">
      <div className="text-[13px] font-semibold text-t1 mb-2">
        {data.source === "DUAL" ? "Doble lectura del plano" : `Lectura ${data.source.replace("SOLO_", "")}`}
      </div>

      {data.m2_warning && (
        <div className="text-[12px] text-yellow-400 bg-yellow-400/10 rounded px-2 py-1 mb-2">
          {data.m2_warning}
        </div>
      )}

      {editedData.sectores.map((sector, si) => (
        <div key={sector.id} className="mb-3">
          <div className="text-[12px] text-t3 uppercase tracking-wide mb-1">
            {sector.id} — {sector.tipo}
          </div>
          {sector.tramos.map((tramo, ti) => (
            <div key={tramo.id} className="ml-2 border-l border-b1 pl-2 mb-2">
              <div className="text-[12px] text-t2 font-medium mb-1">{tramo.descripcion || tramo.id}</div>
              <FieldRow label="Largo" field={tramo.largo_m} onEdit={(v) => updateField(si, ti, "largo_m", v)} />
              <FieldRow label="Ancho" field={tramo.ancho_m} onEdit={(v) => updateField(si, ti, "ancho_m", v)} />
              <FieldRow label="m²" field={tramo.m2} onEdit={(v) => updateField(si, ti, "m2", v)} />
              {tramo.zocalos.map((z, zi) => (
                <div key={zi} className="flex items-center gap-2 py-1 px-2 text-[13px]">
                  <span className="w-5 text-center">{STATUS_ICONS[z.status] || ""}</span>
                  <span className="text-t3 w-24 shrink-0">Zóc. {z.lado}</span>
                  {z.status === "CONFLICTO" || z.status === "DUDOSO" ? (
                    <input
                      type="number"
                      step="0.01"
                      defaultValue={z.ml}
                      className="w-20 px-1.5 py-0.5 bg-s1 border border-b2 rounded text-xs text-t1"
                      onChange={(e) => updateField(si, ti, `zocalo_${zi}`, parseFloat(e.target.value) || 0)}
                    />
                  ) : (
                    <span className={STATUS_COLORS[z.status] || "text-t2"}>
                      {z.ml}ml \u00D7 {z.alto_m}m
                    </span>
                  )}
                </div>
              ))}
            </div>
          ))}
          {sector.ambiguedades.length > 0 && (
            <div className="text-[11px] text-orange-400 mt-1 ml-2">
              {sector.ambiguedades.map((a, i) => <div key={i}>\u26A0\uFE0F {a}</div>)}
            </div>
          )}
        </div>
      ))}

      <button
        className="w-full mt-2 py-2 rounded-lg text-[13px] font-medium bg-green-600 hover:bg-green-500 text-white transition"
        onClick={() => onConfirm(editedData)}
      >
        Confirmar medidas
      </button>
    </div>
  );
}
