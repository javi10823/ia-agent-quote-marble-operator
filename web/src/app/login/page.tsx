"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/auth";
import clsx from "clsx";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Error al iniciar sesión");
    } finally {
      setLoading(false);
    }
  }

  const inputClass = clsx(
    "w-full px-3.5 py-2.5 bg-s3 border rounded-[10px] text-t1 text-sm font-sans outline-none",
    "transition-[border-color,box-shadow] duration-150",
    "focus:border-acc focus:ring-[3px] focus:ring-acc/12",
    "placeholder:text-t4",
    error ? "border-err" : "border-b1",
  );

  return (
    <div className="flex items-center justify-center h-screen bg-bg relative">
      {/* Subtle glow */}
      <div className="hidden md:block fixed w-[600px] h-[600px] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none bg-[radial-gradient(circle,rgba(95,125,160,0.06)_0%,transparent_70%)]" />

      <div className="relative z-[1] w-full max-w-[400px] mx-4 bg-s1 border border-b1 rounded-2xl px-5 md:px-9 pt-8 md:pt-10 pb-7 md:pb-9 shadow-[0_24px_80px_rgba(0,0,0,0.5),0_0_0_1px_rgba(255,255,255,0.03)_inset]">
        {/* Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-11 h-11 bg-acc-bg border border-acc/20 rounded-xl text-xl font-bold text-acc mb-4 -tracking-[0.02em]">
            D
          </div>
          <div className="text-lg font-semibold text-t1 -tracking-[0.03em]">
            D&apos;Angelo Marmoleria
          </div>
          <div className="text-xs text-t3 mt-1 tracking-wide">
            Sistema de presupuestos
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 px-3.5 py-2.5 bg-err/[0.08] border border-err/[0.18] rounded-lg text-[13px] text-err mb-4 animate-[fadeUp_0.2s_ease]">
            <svg className="shrink-0" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label htmlFor="username" className="block text-xs font-medium text-t2 mb-1.5">
              Usuario
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="marmoleria"
              autoComplete="username"
              required
              className={inputClass}
            />
          </div>

          <div className="mb-4">
            <label htmlFor="password" className="block text-xs font-medium text-t2 mb-1.5">
              Contraseña
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPw ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                required
                className={clsx(inputClass, "pr-10")}
              />
              <button
                type="button"
                onClick={() => setShowPw(!showPw)}
                aria-label={showPw ? "Ocultar contraseña" : "Mostrar contraseña"}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-t3 hover:text-t2 transition-colors"
              >
                {showPw ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className={clsx(
              "w-full py-3 rounded-[10px] text-sm font-semibold text-white mt-1.5 -tracking-[0.01em]",
              "transition-[background,transform] duration-150",
              loading
                ? "bg-acc/40 cursor-wait"
                : "bg-acc hover:bg-acc-hover active:scale-[0.99] cursor-pointer",
            )}
          >
            {loading ? "Verificando..." : "Iniciar sesión"}
          </button>
        </form>

        <div className="text-center mt-6 text-[11px] text-t4 tracking-wide">
          Acceso exclusivo para operadores
        </div>
      </div>
    </div>
  );
}
