"use client";

interface CondicionesRecord {
  pdf_url: string;
  drive_url?: string | null;
  drive_file_id?: string | null;
  generated_at: string;
  plazo: string;
}

interface Props {
  record: CondicionesRecord;
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

/**
 * PR #24 — Card de Condiciones de Contratación.
 *
 * Solo se renderiza cuando el quote es edificio (is_building=true) y se
 * generó el PDF correspondiente (condiciones_pdf en el detalle).
 *
 * Mismo patrón visual que ResumenObraCard: header con icono + metadatos,
 * link a Drive (fallback a PDF local).
 */
export function CondicionesCard({ record }: Props) {
  return (
    <div className="border border-b1 rounded-[10px] bg-white/[0.015]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-b1">
        <div className="flex items-center gap-2">
          <span className="text-base">📋</span>
          <div>
            <div className="text-[11px] font-semibold tracking-[0.09em] text-t3 uppercase">
              Condiciones de contratación
            </div>
            <div className="text-[11px] text-t4 mt-px">
              Generado {fmtDate(record.generated_at)}
            </div>
          </div>
        </div>
      </div>
      <div className="px-4 py-3">
        <div className="text-[12px] text-t3 mb-3">
          <span className="font-semibold">Plazo:</span> {record.plazo}
        </div>
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
