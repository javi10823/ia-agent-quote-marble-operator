"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import {
  fetchQuotes,
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

export function QuotesProvider({ children }: { children: ReactNode }) {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const refresh = useCallback(async () => {
    try {
      const data = await fetchQuotes();
      setQuotes(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || "Error al cargar presupuestos");
      toast(err.message || "Error al cargar presupuestos");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { refresh(); }, [refresh]);

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

  const removeQuote = useCallback(async (id: string) => {
    const backup = quotes;
    setQuotes(prev => prev.filter(q => q.id !== id));
    try {
      await apiDeleteQuote(id);
    } catch (err: any) {
      setQuotes(backup); // rollback
      toast(err.message || "Error al eliminar presupuesto");
      throw err;
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
