"use client";

import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import {
  fetchQuotes,
  checkQuotes,
  createQuote as apiCreateQuote,
  deleteQuote as apiDeleteQuote,
  updateQuoteStatus as apiUpdateStatus,
  type Quote,
} from "./api";
import { useToast } from "./toast-context";

interface QuotesContextValue {
  quotes: Quote[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  addQuote: () => Promise<string>;
  removeQuote: (id: string) => Promise<void>;
  setStatus: (id: string, status: Quote["status"]) => Promise<void>;
  markRead: (id: string) => void;
}

const QuotesContext = createContext<QuotesContextValue | null>(null);

const POLL_INTERVAL = 15_000; // 15 seconds

export function QuotesProvider({ children }: { children: ReactNode }) {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  // Track last known state for smart polling change detection
  const lastCheckRef = useRef<{ count: number; lastUpdated: string | null }>({
    count: 0,
    lastUpdated: null,
  });

  const refresh = useCallback(async () => {
    try {
      const data = await fetchQuotes();
      setQuotes(data);
      setError(null);
      // Update check ref so polling doesn't re-fetch immediately
      lastCheckRef.current = {
        count: data.length,
        lastUpdated: data.length > 0
          ? data.reduce((max, q) => {
              const t = q.created_at; // created_at is always present
              return t > max ? t : max;
            }, data[0].created_at)
          : null,
      };
    } catch (err: any) {
      setError(err.message || "Error al cargar presupuestos");
      toast(err.message || "Error al cargar presupuestos");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 30_000);
    return () => clearInterval(iv);
  }, [refresh]);

  // Smart polling: check for changes every 15s, only fetch if something changed
  const silentRefresh = useCallback(async () => {
    try {
      const check = await checkQuotes();
      const changed =
        check.count !== lastCheckRef.current.count ||
        check.last_updated_at !== lastCheckRef.current.lastUpdated;
      if (changed) {
        const data = await fetchQuotes();
        setQuotes(data);
        lastCheckRef.current = {
          count: check.count,
          lastUpdated: check.last_updated_at,
        };
      }
    } catch {
      // Silent fail — don't spam toasts on transient network errors
    }
  }, []);

  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden) silentRefresh();
    }, POLL_INTERVAL);
    // Also refresh when tab becomes visible after being hidden
    const onVisible = () => {
      if (!document.hidden) silentRefresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [silentRefresh]);

  const addQuote = useCallback(async () => {
    try {
      const { id } = await apiCreateQuote();
      // Don't add empty draft to list — backend hides drafts without client_name.
      // The quote will appear in the list after the operator sets client+material via chat.
      return id;
    } catch (err: any) {
      toast(err.message || "Error al crear presupuesto");
      throw err;
    }
  }, [toast]);

  const deletingRef = useRef(false);
  const removeQuote = useCallback(async (id: string) => {
    if (deletingRef.current) return;
    deletingRef.current = true;
    const backup = quotes;
    setQuotes(prev => prev.filter(q => q.id !== id));
    try {
      await apiDeleteQuote(id);
    } catch (err: any) {
      setQuotes(backup); // rollback
      toast(err.message || "Error al eliminar presupuesto");
      throw err;
    } finally {
      deletingRef.current = false;
    }
  }, [quotes, toast]);

  const setStatus = useCallback(async (id: string, status: Quote["status"]) => {
    const backup = quotes;
    setQuotes(prev => prev.map(q => q.id === id ? { ...q, status } : q));
    try {
      await apiUpdateStatus(id, status);
    } catch (err: any) {
      setQuotes(backup); // rollback
      toast(err.message || "Error al cambiar estado");
      throw err;
    }
  }, [quotes, toast]);

  const markRead = useCallback((id: string) => {
    setQuotes(prev => prev.map(q => q.id === id ? { ...q, is_read: true } : q));
  }, []);

  return (
    <QuotesContext.Provider value={{ quotes, loading, error, refresh, addQuote, removeQuote, setStatus, markRead }}>
      {children}
    </QuotesContext.Provider>
  );
}

export function useQuotes(): QuotesContextValue {
  const ctx = useContext(QuotesContext);
  if (!ctx) throw new Error("useQuotes must be used within QuotesProvider");
  return ctx;
}
