"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  fetchEmailDraft,
  regenerateEmailDraft,
  type EmailDraft,
} from "@/lib/api";

interface Props {
  quoteId: string;
  /** Re-trigger lazy fetch when this string changes (e.g. after generating a resumen). */
  reloadKey?: string;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-AR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

async function copyToClipboard(text: string): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* fall through */
    }
  }
  // Fallback for older browsers / Safari without clipboard permission
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-1000px";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export function EmailDraftCard({ quoteId, reloadKey }: Props) {
  const [draft, setDraft] = useState<EmailDraft | null>(null);
  const [loading, setLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editedBody, setEditedBody] = useState<string>("");
  const editableRef = useRef<HTMLTextAreaElement | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const d = await fetchEmailDraft(quoteId);
        if (!cancelled && mountedRef.current) {
          setDraft(d);
          setEditedBody(d.body);
          setEditMode(false);
        }
      } catch (e: any) {
        if (!cancelled && mountedRef.current) {
          setError(e?.message || "Error al cargar el email");
        }
      } finally {
        if (!cancelled && mountedRef.current) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [quoteId, reloadKey]);

  async function handleRegenerate() {
    if (regenerating) return;
    setRegenerating(true);
    setError(null);
    try {
      const d = await regenerateEmailDraft(quoteId);
      setDraft(d);
      setEditedBody(d.body);
      setEditMode(false);
    } catch (e: any) {
      setError(e?.message || "Error al regenerar el email");
    } finally {
      setRegenerating(false);
    }
  }

  async function handleCopy() {
    if (!draft) return;
    // Copy: subject + blank line + body (edited if in edit mode)
    const body = editMode ? editedBody : draft.body;
    const text = `${draft.subject}\n\n${body}`;
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopied(true);
      setTimeout(() => {
        if (mountedRef.current) setCopied(false);
      }, 2200);
    } else {
      setError("No se pudo copiar al portapapeles");
    }
  }

  return (
    <div className="border border-b1 rounded-[10px] bg-white/[0.015]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-b1">
        <div className="flex items-center gap-2">
          <span className="text-base">✉️</span>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-semibold tracking-[0.09em] text-t3 uppercase">
                Email para cliente
              </span>
              <span className="text-[9px] font-semibold px-1.5 py-px rounded bg-acc/15 text-acc tracking-wide">
                IA
              </span>
            </div>
            {draft && (
              <div className="text-[11px] text-t4 mt-px">
                Generado {fmtDate(draft.generated_at)}
              </div>
            )}
          </div>
        </div>
        <button
          onClick={handleRegenerate}
          disabled={regenerating || loading}
          className={clsx(
            "px-3 py-1.5 rounded-md text-[11px] font-medium font-sans border border-b1 bg-transparent transition",
            regenerating || loading
              ? "text-t3 cursor-wait"
              : "text-t2 hover:text-t1 hover:border-b2 cursor-pointer"
          )}
        >
          {regenerating ? "Regenerando…" : "↻ Regenerar"}
        </button>
      </div>

      <div className="px-4 py-3">
        {loading && !draft && (
          <div className="py-8 flex items-center justify-center gap-2 text-[12px] text-t3">
            <span className="inline-block w-3 h-3 border-2 border-t3/40 border-t-acc rounded-full animate-spin" />
            Generando email…
          </div>
        )}

        {error && !loading && (
          <div className="flex items-start gap-2 bg-err/[0.08] border border-err/[0.25] rounded-lg px-3 py-2 mb-3 text-[12px] text-err">
            <span>!</span>
            <div className="flex-1">
              <div>{error}</div>
              <button
                onClick={handleRegenerate}
                className="underline text-err/90 hover:text-err mt-1 bg-transparent border-none cursor-pointer p-0 text-[11px] font-sans"
              >
                Reintentar
              </button>
            </div>
          </div>
        )}

        {draft && (
          <>
            {draft.validated === false && (
              <div className="flex items-start gap-2 bg-amb/[0.08] border border-amb/[0.25] rounded-lg px-3 py-2 mb-3 text-[12px] text-amb">
                <span>⚠</span>
                <div>
                  Revisá los montos antes de enviar — el validador detectó
                  posibles inconsistencias en la versión generada.
                </div>
              </div>
            )}

            <div className="bg-white/[0.02] border border-b1 rounded-lg px-3 py-2 mb-3">
              <div className="text-[10px] font-semibold tracking-wider text-t3 mb-0.5">
                ASUNTO
              </div>
              <div className="text-[13px] font-medium text-t1 break-words">
                {draft.subject}
              </div>
            </div>

            {editMode ? (
              <textarea
                ref={editableRef}
                value={editedBody}
                onChange={(e) => setEditedBody(e.target.value)}
                className="w-full font-mono text-[12px] leading-relaxed bg-white/[0.02] border border-b1 rounded-lg px-3 py-3 text-t1 outline-none focus:border-acc resize-y min-h-[220px] mb-3"
                spellCheck
              />
            ) : (
              <pre className="font-mono text-[12px] leading-relaxed bg-white/[0.02] border border-b1 rounded-lg px-3 py-3 text-t1 whitespace-pre-wrap max-h-[320px] overflow-y-auto mb-3">
                {draft.body}
              </pre>
            )}

            <div className="flex gap-2 flex-wrap items-center">
              <button
                onClick={handleCopy}
                className={clsx(
                  "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium font-sans border-none text-white cursor-pointer transition",
                  copied
                    ? "bg-grn hover:bg-grn"
                    : "bg-acc hover:bg-blue-500"
                )}
              >
                {copied ? "✓ Copiado" : "📋 Copiar email"}
              </button>
              <button
                onClick={() => {
                  if (editMode) {
                    // Cancel edits — restore original body
                    setEditedBody(draft.body);
                    setEditMode(false);
                  } else {
                    setEditMode(true);
                    setTimeout(() => editableRef.current?.focus(), 30);
                  }
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium font-sans border border-b1 bg-transparent text-t2 cursor-pointer hover:text-t1 hover:border-b2 transition"
              >
                {editMode ? "Descartar" : "Editar"}
              </button>
              <div className="text-[10px] text-t4 ml-auto">
                {editMode
                  ? "Los cambios sólo afectan el copiado local."
                  : "Los cambios locales no se guardan — regenerá si querés reescribirlo."}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
