"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  generateResumenObra,
  type Quote,
  type ResumenObraRecord,
} from "@/lib/api";

const MAX_NOTES = 1000;

interface Props {
  open: boolean;
  quotes: Quote[]; // selected quotes, same client
  onClose: () => void;
  onSuccess: (record: ResumenObraRecord, affectedIds: string[]) => void;
}

export function ResumenObraModal({ open, quotes, onClose, onSuccess }: Props) {
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Reset whenever the modal opens with a fresh selection
  useEffect(() => {
    if (open) {
      setNotes("");
      setError(null);
      setSubmitting(false);
      // Focus textarea after render
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [open]);

  // Esc to close — only when not submitting (avoid cancelling mid-flight)
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, submitting, onClose]);

  if (!open) return null;

  const clientName = quotes[0]?.client_name || "";
  const project = quotes[0]?.project || "";
  const hasExistingResumen = quotes.some((q) => q.resumen_obra);

  async function handleSubmit() {
    if (submitting) return;
    if (notes.length > MAX_NOTES) {
      setError(`Las notas superan ${MAX_NOTES} caracteres.`);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const record = await generateResumenObra({
        quote_ids: quotes.map((q) => q.id),
        notes: notes.trim() || undefined,
      });
      onSuccess(
        record,
        quotes.map((q) => q.id)
      );
    } catch (e: any) {
      setError(e?.message || "Error al generar el resumen");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[1000] bg-black/60 backdrop-blur-[4px] flex items-center justify-center"
      onClick={() => !submitting && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label="Generar resumen de obra"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-6 md:py-7 w-[calc(100vw-24px)] max-w-[520px] shadow-[0_20px_60px_rgba(0,0,0,.5)]"
      >
        <div className="flex items-start justify-between mb-2">
          <div className="text-[15px] font-medium text-t1">
            Generar resumen de obra
          </div>
          <button
            onClick={() => !submitting && onClose()}
            className="text-t3 hover:text-t1 text-xl leading-none bg-transparent border-none cursor-pointer p-0"
            aria-label="Cerrar"
          >
            ×
          </button>
        </div>

        <div className="text-[12px] text-t3 mb-4">
          Cliente: <strong className="text-t2">{clientName || "—"}</strong>
          {project && (
            <>
              {" · "}Proyecto: <strong className="text-t2">{project}</strong>
            </>
          )}
        </div>

        <div className="bg-s3 border border-b1 rounded-lg px-3 py-2.5 mb-4">
          <div className="text-[10px] font-semibold tracking-wider text-t3 mb-2">
            SE CONSOLIDARÁN {quotes.length} PRESUPUESTO
            {quotes.length === 1 ? "" : "S"}
          </div>
          <ul className="space-y-1.5">
            {quotes.map((q) => (
              <li
                key={q.id}
                className="flex justify-between items-center text-[13px]"
              >
                <span className="text-t1 truncate mr-3">
                  {q.material || "(sin material)"}
                </span>
                <span className="font-mono text-t2 shrink-0">
                  {q.total_ars
                    ? `$${q.total_ars.toLocaleString("es-AR")}`
                    : q.total_usd
                      ? `USD ${q.total_usd.toLocaleString()}`
                      : "—"}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">
          Notas adicionales <span className="text-t4 normal-case">(opcional)</span>
        </label>
        <textarea
          ref={textareaRef}
          value={notes}
          onChange={(e) => {
            setNotes(e.target.value);
            if (error) setError(null);
          }}
          placeholder="Ej: Entrega coordinada con obra civil. Piso 3 requiere acceso por grúa. Confirmar medidas antes del corte."
          maxLength={MAX_NOTES + 100}
          rows={4}
          className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4 resize-y min-h-[80px]"
          disabled={submitting}
        />
        <div className="flex justify-between items-center mt-1 mb-3">
          <div className="text-[10px] text-t4">
            Se incluyen en el PDF y en el email del cliente.
          </div>
          <div
            className={clsx(
              "text-[10px] font-mono",
              notes.length > MAX_NOTES ? "text-err" : "text-t4"
            )}
          >
            {notes.length}/{MAX_NOTES}
          </div>
        </div>

        {hasExistingResumen && (
          <div className="flex items-start gap-2 bg-amb/[0.08] border border-amb/[0.25] rounded-lg px-3 py-2 mb-4 text-[12px] text-amb">
            <span>⚠</span>
            <div>
              Ya existe un resumen generado para alguno de estos presupuestos.
              Si confirmás, <strong>se sobreescribe</strong>.
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 bg-err/[0.08] border border-err/[0.25] rounded-lg px-3 py-2 mb-4 text-[12px] text-err">
            <span>!</span>
            <div>{error}</div>
          </div>
        )}

        <div className="flex gap-2.5 justify-end">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancelar
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || notes.length > MAX_NOTES}
            className={clsx(
              "px-[18px] py-2 rounded-lg text-[13px] font-medium font-sans border-none text-white transition inline-flex items-center gap-2",
              submitting || notes.length > MAX_NOTES
                ? "bg-acc/60 cursor-wait"
                : "bg-acc cursor-pointer hover:bg-blue-500"
            )}
          >
            {submitting ? (
              <>
                <span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                Generando…
              </>
            ) : (
              <>Generar resumen</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
