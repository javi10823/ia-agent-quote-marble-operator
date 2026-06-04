/**
 * Audit mode global · Sprint 3 observability-per-row.
 *
 * Hook global con localStorage persist + sync `body[data-audit]`.
 * Reemplaza el toggle local del paso-4 (CalcToolbar) por un flag único
 * controlado desde TopBar. Visible para cualquier ruta del quote layout.
 *
 * Mock-only (decisión Javi H): role-gate dev/QA diferido — toggle
 * discreto es proxy razonable mientras no exista role system.
 */
"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";

const STORAGE_KEY = "marble.audit-mode";

type AuditMode = "on" | "off";

// External store · simple pub/sub para que múltiples componentes
// se sincronicen sin React Context ni state global.
const listeners = new Set<() => void>();

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function getSnapshot(): AuditMode {
  if (typeof window === "undefined") return "off";
  return (window.localStorage.getItem(STORAGE_KEY) as AuditMode) || "off";
}

function getServerSnapshot(): AuditMode {
  return "off";
}

function applyBody(value: AuditMode) {
  if (typeof document === "undefined") return;
  // Fix-up #1 H3: spec original dice attribute AUSENTE en OFF.
  // Functionally equivalente para `body[data-audit="on"]` CSS selectors,
  // pero coherente con la expectativa (DevTools muestra atributo solo cuando on).
  if (value === "on") {
    document.body.dataset.audit = "on";
  } else {
    delete document.body.dataset.audit;
  }
}

function setMode(value: AuditMode) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, value);
  applyBody(value);
  listeners.forEach((cb) => cb());
}

export function useAuditMode() {
  const mode = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const auditOn = mode === "on";

  // Sync body[data-audit] al mount + cada vez que cambia.
  useEffect(() => {
    applyBody(mode);
    // No limpiamos al desmontar · el flag es global por sesión.
  }, [mode]);

  const toggle = useCallback(() => {
    setMode(getSnapshot() === "on" ? "off" : "on");
  }, []);

  const setOn = useCallback((on: boolean) => {
    setMode(on ? "on" : "off");
  }, []);

  return { auditOn, toggle, setOn };
}
