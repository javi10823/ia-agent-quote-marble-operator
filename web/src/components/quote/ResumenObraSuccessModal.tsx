"use client";

import { useEffect } from "react";
import type { ResumenObraRecord } from "@/lib/api";

interface Props {
  open: boolean;
  record: ResumenObraRecord | null;
  affectedCount: number;
  onClose: () => void;
}

export function ResumenObraSuccessModal({
  open,
  record,
  affectedCount,
  onClose,
}: Props) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !record) return null;

  const filename = record.pdf_url.split("/").pop() || "resumen.pdf";

  return (
    <div
      className="fixed inset-0 z-[1000] bg-black/60 backdrop-blur-[4px] flex items-center justify-center"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Resumen generado"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-6 md:py-7 w-[calc(100vw-24px)] max-w-[420px] shadow-[0_20px_60px_rgba(0,0,0,.5)] text-center"
      >
        <div className="w-14 h-14 rounded-full mx-auto mb-4 flex items-center justify-center bg-grn-bg text-grn text-[28px] leading-none">
          ✓
        </div>
        <div className="text-[15px] font-medium text-t1 mb-1">
          Resumen generado
        </div>
        <div className="text-[13px] text-t2 mb-5">
          Se adjuntó a {affectedCount} presupuesto
          {affectedCount === 1 ? "" : "s"}.
        </div>

        <div className="bg-s3 border border-b1 rounded-lg px-3 py-2.5 mb-5 text-left text-[12px] space-y-1.5">
          <div className="flex justify-between gap-3">
            <span className="text-t3 shrink-0">Archivo</span>
            <span className="text-t1 truncate">{filename}</span>
          </div>
          {record.drive_url && (
            <div className="flex justify-between gap-3">
              <span className="text-t3 shrink-0">Drive</span>
              <a
                href={record.drive_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-acc truncate hover:underline"
              >
                Abrir en Drive
              </a>
            </div>
          )}
          <div className="flex justify-between gap-3">
            <span className="text-t3 shrink-0">Cliente</span>
            <span className="text-t1 truncate">{record.client_name || "—"}</span>
          </div>
        </div>

        <div className="flex gap-2 justify-end">
          <a
            href={record.pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-2 rounded-lg text-[12px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition no-underline inline-flex items-center gap-1.5"
          >
            📄 Ver PDF
          </a>
          {record.drive_url && (
            <a
              href={record.drive_url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-2 rounded-lg text-[12px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition no-underline inline-flex items-center gap-1.5"
            >
              ☁ Drive
            </a>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-[13px] font-medium font-sans border-none text-white bg-acc cursor-pointer hover:bg-blue-500 transition"
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
}
