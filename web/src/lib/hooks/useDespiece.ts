/**
 * Hook que gestiona el despiece del paso 3:
 *   - load inicial via listPiecesForQuote (skeleton + timeline)
 *   - updatePiece / addPiece / deletePiece (edición humana en vivo)
 *   - regenerate (Valentina re-corre la inferencia)
 *   - dirty tracking: isDirty si ≥1 pieza fue editada o agregada a mano
 *
 * Cancela cualquier load pendiente al desmontar (AbortController). Los
 * datasources indexan SIEMPRE por quoteId (lección Sprint 2.5 fix-up #2).
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  addPieceForQuote,
  deletePieceForQuote,
  listPiecesForQuote,
  regenerateDespiece,
  updatePieceForQuote,
  type Piece,
  type PieceList,
  type TimelineStep,
} from "../api";
import type { DespieceFormState } from "../types";

export function useDespiece(quoteId: string) {
  const [data, setData] = useState<PieceList | null>(null);
  const [state, setState] = useState<DespieceFormState>("loading");
  const [error, setError] = useState<string | null>(null);
  const mutAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let aborted = false;
    const ctrl = new AbortController();
    setState("loading");
    setError(null);
    setData(null);
    listPiecesForQuote(quoteId, { signal: ctrl.signal })
      .then((list) => {
        if (aborted) return;
        setData(list);
        setState("idle");
      })
      .catch((err) => {
        if (aborted || (err instanceof DOMException && err.name === "AbortError")) return;
        setError(err instanceof Error ? err.message : "Error al cargar el despiece");
        setState("error");
      });
    return () => {
      aborted = true;
      ctrl.abort();
    };
  }, [quoteId]);

  const updatePiece = useCallback(
    async (pieceId: string, partial: Partial<Piece>) => {
      mutAbortRef.current?.abort();
      const ctrl = new AbortController();
      mutAbortRef.current = ctrl;
      setState("saving");
      setError(null);
      try {
        const updated = await updatePieceForQuote(quoteId, pieceId, partial, {
          signal: ctrl.signal,
        });
        setData((prev) =>
          prev
            ? { ...prev, pieces: prev.pieces.map((p) => (p.id === pieceId ? updated : p)) }
            : prev,
        );
        setState("idle");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Error al guardar la pieza");
        setState("error");
      }
    },
    [quoteId],
  );

  const addPiece = useCallback(
    async (piece: Omit<Piece, "id" | "origin" | "confidence" | "extracted_from">) => {
      setState("saving");
      setError(null);
      try {
        const created = await addPieceForQuote(quoteId, piece);
        setData((prev) => (prev ? { ...prev, pieces: [...prev.pieces, created] } : prev));
        setState("idle");
        return created;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al agregar la pieza");
        setState("error");
        return null;
      }
    },
    [quoteId],
  );

  const deletePiece = useCallback(
    async (pieceId: string) => {
      setState("saving");
      setError(null);
      try {
        await deletePieceForQuote(quoteId, pieceId);
        setData((prev) =>
          prev ? { ...prev, pieces: prev.pieces.filter((p) => p.id !== pieceId) } : prev,
        );
        setState("idle");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al eliminar la pieza");
        setState("error");
      }
    },
    [quoteId],
  );

  const regenerate = useCallback(
    async (mode: "all" | "keep-edits" = "all") => {
      setState("regenerating");
      setError(null);
      try {
        const fresh = await regenerateDespiece(quoteId, { mode });
        setData(fresh);
        setState("idle");
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Error al regenerar el despiece");
        setState("error");
      }
    },
    [quoteId],
  );

  const pieces: Piece[] = data?.pieces ?? [];
  const timeline: TimelineStep[] = data?.timeline ?? [];
  const status = data?.status ?? "pending";
  const warnings = data?.warnings ?? [];
  const isDirty = pieces.some(
    (p) => p.edited === true || p.origin === "EDITADO" || p.origin === "AGREGADO_MANUAL",
  );
  const editedCount = pieces.filter(
    (p) => p.edited === true || p.origin === "AGREGADO_MANUAL",
  ).length;

  // Sprint 3 error-states · flags del PieceList propagados al UI.
  const rejected = data?.rejected === true;
  const chatFlagged = data?.chatFlagged ?? null;

  return {
    pieces,
    timeline,
    status,
    warnings,
    state,
    error,
    updatePiece,
    addPiece,
    deletePiece,
    regenerate,
    isDirty,
    editedCount,
    rejected,
    chatFlagged,
  };
}
