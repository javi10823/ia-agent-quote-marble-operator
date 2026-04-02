"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import {
  fetchQuotes,
  createQuote as apiCreateQuote,
  deleteQuote as apiDeleteQuote,
  updateQuoteStatus as apiUpdateStatus,
  type Quote,
} from "./api";

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

  const refresh = useCallback(async () => {
    try {
      const data = await fetchQuotes();
      setQuotes(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || "Error al cargar presupuestos");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const addQuote = useCallback(async () => {
    const { id } = await apiCreateQuote();
    // Optimistic: add empty draft to list
    setQuotes(prev => [{
      id,
      client_name: "",
      project: "",
      material: null,
      total_ars: null,
      total_usd: null,
      status: "draft" as const,
      pdf_url: null,
      excel_url: null,
      drive_url: null,
      parent_quote_id: null,
      source: "operator",
      is_read: true,
      created_at: new Date().toISOString(),
    }, ...prev]);
    return id;
  }, []);

  const removeQuote = useCallback(async (id: string) => {
    await apiDeleteQuote(id);
    setQuotes(prev => prev.filter(q => q.id !== id));
  }, []);

  const setStatus = useCallback(async (id: string, status: Quote["status"]) => {
    await apiUpdateStatus(id, status);
    setQuotes(prev => prev.map(q => q.id === id ? { ...q, status } : q));
  }, []);

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
