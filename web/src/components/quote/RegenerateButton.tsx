"use client";

import { useState, useEffect, useCallback } from "react";
import clsx from "clsx";
import { regenerateQuoteDocs } from "@/lib/api";

interface Props {
  /** Id del presupuesto a regenerar. */
  quoteId: string;
  /** Si false, no se muestra el botón (ej. no hay breakdown todavía). */
  enabled: boolean;
  /** Callback que el parent usa para refetch del quote y refrescar los links. */
  onRegenerated: () => void | Promise<void>;
}

/**
 * Botón "Regenerar archivos" con modal de confirmación.
 *
 * Llama a POST /quotes/{id}/regenerate que re-emite PDF/Excel usando los
 * datos ya guardados en DB. NO re-corre Valentina, NO recalcula, NO cambia
 * status — solo aplica el template actual sobre el breakdown existente.
 */
export default function RegenerateButton({ quoteId, enabled, onRegenerated }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Escape cierra el modal
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy]);

  // Auto-hide del toast a los 3s
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleConfirm = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await regenerateQuoteDocs(quoteId);
      await onRegenerated();
      setOpen(false);
      setToast("Archivos regenerados");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error al regenerar");
    } finally {
      setBusy(false);
    }
  }, [quoteId, onRegenerated]);

  if (!enabled) return null;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className={clsx(
          "flex items-center gap-[5px] px-3 py-1.5 rounded-md text-[11px] font-medium no-underline border bg-transparent hover:bg-white/[0.04] transition cursor-pointer",
          "border-white/10 text-t2 hover:text-t1",
        )}
        title="Regenerar PDF y Excel con el template actual"
      >
        ↻ Regenerar
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          onClick={() => !busy && setOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-b1 bg-s2 p-6 shadow-[0_20px_40px_-20px_rgba(0,0,0,0.5)]"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-[15px] font-semibold text-t1 mb-2">Regenerar archivos</h3>
            <p className="text-[13px] text-t2 leading-relaxed mb-4">
              ¿Regenerar <strong className="text-t1">PDF y Excel</strong> con el template actual?
              Los archivos anteriores serán reemplazados.
            </p>
            <div className="text-[12px] text-t3 bg-s1 border border-b1 rounded-lg px-3 py-2 mb-5 leading-relaxed">
              No se recalculan precios, m² ni MO. No se cambia el estado del
              presupuesto. Solo se refrescan los archivos.
            </div>

            {error && (
              <div className="text-[12px] text-err bg-[rgba(255,69,58,0.1)] border border-err/30 rounded-lg px-3 py-2 mb-3">
                {error}
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setOpen(false)}
                disabled={busy}
                className="px-4 py-2 rounded-lg text-[13px] font-medium border border-b2 text-t2 hover:text-t1 hover:border-b3 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancelar
              </button>
              <button
                onClick={handleConfirm}
                disabled={busy}
                className="px-4 py-2 rounded-lg text-[13px] font-semibold bg-acc hover:bg-acc-hover text-white transition disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {busy ? (
                  <>
                    <span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                    Regenerando…
                  </>
                ) : (
                  "Regenerar"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg bg-grn text-white text-[13px] font-medium shadow-[0_10px_30px_-10px_rgba(48,209,88,0.5)] animate-[fadeIn_0.2s_ease]">
          ✓ {toast}
        </div>
      )}
    </>
  );
}
