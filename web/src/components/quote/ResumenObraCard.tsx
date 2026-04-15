"use client";

import clsx from "clsx";
import type { ResumenObraRecord } from "@/lib/api";

interface Props {
  record: ResumenObraRecord;
  onRegenerate?: () => void;
  regenerating?: boolean;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-AR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function ResumenObraCard({
  record,
  onRegenerate,
  regenerating,
}: Props) {
  return (
    <div className="border border-b1 rounded-[10px] bg-white/[0.015]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-b1">
        <div className="flex items-center gap-2">
          <span className="text-base">📑</span>
          <div>
            <div className="text-[11px] font-semibold tracking-[0.09em] text-t3 uppercase">
              Resumen de obra
            </div>
            <div className="text-[11px] text-t4 mt-px">
              Generado {fmtDate(record.generated_at)} · {record.quote_ids.length}{" "}
              presupuesto{record.quote_ids.length === 1 ? "" : "s"}
            </div>
          </div>
        </div>
        {onRegenerate && (
          <button
            onClick={onRegenerate}
            disabled={regenerating}
            className={clsx(
              "px-3 py-1.5 rounded-md text-[11px] font-medium font-sans border border-b1 bg-transparent transition",
              regenerating
                ? "text-t3 cursor-wait"
                : "text-t2 hover:text-t1 hover:border-b2 cursor-pointer"
            )}
          >
            {regenerating ? "Regenerando…" : "↻ Regenerar"}
          </button>
        )}
      </div>

      <div className="px-4 py-3">
        {record.notes ? (
          <div className="mb-3">
            <div className="text-[10px] font-semibold tracking-wider text-t3 mb-1">
              NOTAS DEL OPERADOR
            </div>
            <p className="text-[13px] text-t2 italic leading-relaxed whitespace-pre-wrap">
              “{record.notes}”
            </p>
          </div>
        ) : (
          <div className="text-[12px] text-t4 mb-3 italic">Sin notas adicionales.</div>
        )}

        {/*
          PR #23 — solo ofrecer Drive. El operador pidió esconder el botón
          'Descargar PDF' del card del resumen porque el flujo real es
          mandar el link de Drive al cliente, no descargar local. Si Drive
          falló (drive_url null) caemos al PDF local como fallback.
        */}
        <div className="flex gap-2 flex-wrap">
          {record.drive_url ? (
            <a
              href={record.drive_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium font-sans no-underline border border-b1 bg-transparent text-t2 hover:border-b2 hover:text-t1 transition"
            >
              ☁ Ver en Drive
            </a>
          ) : (
            <a
              href={record.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium font-sans no-underline border border-b1 bg-transparent text-t2 hover:border-b2 hover:text-t1 transition"
              title="Drive no disponible — abriendo PDF local"
            >
              📄 Descargar PDF
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
