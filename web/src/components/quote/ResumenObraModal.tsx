"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import {
  clientMatchCheck,
  generateResumenObra,
  mergeClient,
  type ClientMatchCheckResult,
  type Quote,
  type ResumenObraRecord,
} from "@/lib/api";
import { areFuzzySameClient } from "@/lib/clientMatch";

const MAX_NOTES = 1000;

interface Props {
  open: boolean;
  quotes: Quote[]; // selected quotes, same (fuzzy or exact) client
  onClose: () => void;
  onSuccess: (record: ResumenObraRecord, affectedIds: string[]) => void;
  /** Called when the operator unifies the client name (via merge-client). */
  onClientsMerged?: (canonicalName: string, quoteIds: string[]) => void;
}

type Step = "form" | "ambiguous";

export function ResumenObraModal({
  open,
  quotes,
  onClose,
  onSuccess,
  onClientsMerged,
}: Props) {
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<Step>("form");
  const [matchCheck, setMatchCheck] =
    useState<ClientMatchCheckResult | null>(null);
  const [canonicalName, setCanonicalName] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Derived from quotes — distinct raw client names (for UI display even
  // before the back-end check has run).
  const distinctClientNames = useMemo(() => {
    const set = new Set<string>();
    for (const q of quotes) {
      if ((q.client_name || "").trim()) set.add(q.client_name);
    }
    return Array.from(set);
  }, [quotes]);

  const looksFuzzy = useMemo(() => {
    if (distinctClientNames.length <= 1) return false;
    const anchor = distinctClientNames[0];
    return distinctClientNames.every((n) => areFuzzySameClient(n, anchor));
  }, [distinctClientNames]);

  useEffect(() => {
    if (open) {
      setNotes("");
      setError(null);
      setSubmitting(false);
      setStep("form");
      setMatchCheck(null);
      setCanonicalName(distinctClientNames[0] || "");
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [open, distinctClientNames]);

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

  async function doGenerate(forceSameClient: boolean) {
    setError(null);
    setSubmitting(true);
    try {
      const record = await generateResumenObra({
        quote_ids: quotes.map((q) => q.id),
        notes: notes.trim() || undefined,
        force_same_client: forceSameClient || undefined,
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

  async function handleSubmit() {
    if (submitting) return;
    if (notes.length > MAX_NOTES) {
      setError(`Las notas superan ${MAX_NOTES} caracteres.`);
      return;
    }
    setError(null);

    // Client-side fast path: if all distinct names are fuzzy-equivalent,
    // skip the pre-check round trip.
    if (!looksFuzzy && distinctClientNames.length > 1) {
      setSubmitting(true);
      try {
        const check = await clientMatchCheck(quotes.map((q) => q.id));
        if (!check.same) {
          setMatchCheck(check);
          setStep("ambiguous");
          setSubmitting(false);
          return;
        }
      } catch (e: any) {
        setError(e?.message || "No pudimos verificar los clientes");
        setSubmitting(false);
        return;
      }
      setSubmitting(false);
    }
    await doGenerate(false);
  }

  async function handleAmbiguousContinue() {
    await doGenerate(true);
  }

  async function handleMergeThenGenerate() {
    const name = canonicalName.trim();
    if (!name) {
      setError("El nombre canónico no puede estar vacío.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await mergeClient(
        quotes.map((q) => q.id),
        name
      );
      onClientsMerged?.(
        name,
        quotes.map((q) => q.id)
      );
      await doGenerate(false);
    } catch (e: any) {
      setError(e?.message || "Error al unificar clientes");
      setSubmitting(false);
    }
  }

  // ─────────────────────────────────────────────────────────
  // Step: ambiguous
  // ─────────────────────────────────────────────────────────
  if (step === "ambiguous" && matchCheck) {
    return (
      <div
        className="fixed inset-0 z-[1000] bg-black/60 backdrop-blur-[4px] flex items-center justify-center"
        onClick={() => !submitting && onClose()}
        role="dialog"
        aria-modal="true"
        aria-label="Verificar cliente"
      >
        <div
          onClick={(e) => e.stopPropagation()}
          className="bg-s2 border border-b2 rounded-[14px] px-6 md:px-8 py-6 md:py-7 w-[calc(100vw-24px)] max-w-[520px] shadow-[0_20px_60px_rgba(0,0,0,.5)]"
        >
          <div className="flex items-start justify-between mb-2">
            <div className="text-[15px] font-medium text-t1">
              ¿Son el mismo cliente?
            </div>
            <button
              onClick={() => !submitting && onClose()}
              className="text-t3 hover:text-t1 text-xl leading-none bg-transparent border-none cursor-pointer p-0"
            >
              ×
            </button>
          </div>
          <div className="text-[12px] text-t3 mb-3">
            Los presupuestos tienen nombres de cliente distintos. Si son el
            mismo cliente, podés continuar — opcionalmente unificando el
            nombre para que no se repita en el futuro.
          </div>
          <div className="bg-s3 border border-b1 rounded-lg px-3 py-2.5 mb-4 text-[13px]">
            <div className="text-[10px] font-semibold tracking-wider text-t3 mb-1.5">
              NOMBRES DETECTADOS
            </div>
            <ul className="space-y-0.5">
              {matchCheck.distinct_names.map((n) => (
                <li key={n} className="text-t1">
                  • {n || <span className="italic text-t3">(sin nombre)</span>}
                </li>
              ))}
            </ul>
          </div>

          <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">
            Unificar como <span className="text-t4 normal-case">(opcional)</span>
          </label>
          <input
            type="text"
            value={canonicalName}
            onChange={(e) => {
              setCanonicalName(e.target.value);
              if (error) setError(null);
            }}
            placeholder="Ej: Estudio MUNGE"
            className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4 mb-1"
            disabled={submitting}
          />
          <div className="text-[10px] text-t4 mb-4">
            Si unificás, todos estos presupuestos quedan con este nombre
            canónico y el email se regenera.
          </div>

          {error && (
            <div className="flex items-start gap-2 bg-err/[0.08] border border-err/[0.25] rounded-lg px-3 py-2 mb-4 text-[12px] text-err">
              <span>!</span>
              <div>{error}</div>
            </div>
          )}

          <div className="flex gap-2 justify-end flex-wrap">
            <button
              onClick={() => setStep("form")}
              disabled={submitting}
              className="px-[14px] py-2 rounded-lg text-[12px] font-medium font-sans cursor-pointer border border-b2 bg-transparent text-t2 hover:text-t1 hover:border-b3 transition disabled:opacity-50"
            >
              Volver
            </button>
            <button
              onClick={handleAmbiguousContinue}
              disabled={submitting}
              className={clsx(
                "px-[14px] py-2 rounded-lg text-[12px] font-medium font-sans border transition",
                submitting
                  ? "border-b2 bg-transparent text-t3 cursor-wait"
                  : "border-b2 bg-transparent text-t2 cursor-pointer hover:text-t1 hover:border-b3"
              )}
            >
              Sí, es el mismo · Continuar
            </button>
            <button
              onClick={handleMergeThenGenerate}
              disabled={submitting || !canonicalName.trim()}
              className={clsx(
                "px-[14px] py-2 rounded-lg text-[12px] font-medium font-sans border-none text-white transition inline-flex items-center gap-2",
                submitting || !canonicalName.trim()
                  ? "bg-acc/60 cursor-wait"
                  : "bg-acc cursor-pointer hover:bg-blue-500"
              )}
            >
              {submitting ? "Procesando…" : "Unificar y generar"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────
  // Step: form (default)
  // ─────────────────────────────────────────────────────────
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
                className="flex justify-between items-center text-[13px] gap-3"
              >
                <span className="text-t1 truncate flex-1 min-w-0">
                  <span className="text-t3 text-[11px] mr-1">
                    {q.client_name || "(sin cliente)"}
                  </span>
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

        {looksFuzzy && (
          <div className="flex items-start gap-2 bg-acc/[0.08] border border-acc/[0.25] rounded-lg px-3 py-2 mb-3 text-[12px] text-acc">
            <span>ℹ</span>
            <div>
              Los nombres difieren ligeramente pero parecen el mismo cliente:
              <div className="mt-0.5 text-t2">
                {distinctClientNames.join(" · ")}
              </div>
            </div>
          </div>
        )}

        <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">
          Notas adicionales{" "}
          <span className="text-t4 normal-case">(opcional)</span>
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
