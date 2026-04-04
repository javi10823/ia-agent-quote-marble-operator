"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

export type ToastVariant = "error" | "success" | "warning";

interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toasts: Toast[];
  toast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);
let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, variant: ToastVariant = "error") => {
    setToasts(prev => {
      if (prev.some(t => t.message === message && t.variant === variant)) return prev;
      const id = ++nextId;
      setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 5000);
      return [...prev, { id, message, variant }];
    });
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, toast: addToast }}>
      {children}
      {/* Toast container */}
      {toasts.length > 0 && (
        <div className="fixed top-4 right-4 z-[9998] flex flex-col gap-2 pointer-events-none">
          {toasts.map(t => (
            <div
              key={t.id}
              className={`
                pointer-events-auto px-4 py-3 rounded-lg text-[13px] font-medium
                shadow-[0_8px_30px_rgba(0,0,0,0.4)] border backdrop-blur-sm
                animate-[fadeUp_0.25s_ease] max-w-[360px]
                ${t.variant === "error" ? "bg-err/10 border-err/20 text-err" : ""}
                ${t.variant === "success" ? "bg-grn/10 border-grn/20 text-grn" : ""}
                ${t.variant === "warning" ? "bg-amb/10 border-amb/20 text-amb" : ""}
              `}
              onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
            >
              {t.variant === "error" && "✕ "}
              {t.variant === "success" && "✓ "}
              {t.variant === "warning" && "⚠ "}
              {t.message}
            </div>
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx.toast;
}
