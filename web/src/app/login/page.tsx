"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/auth";

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

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: "100vh", background: "var(--bg)", position: "relative",
    }}>
      {/* Subtle glow */}
      <div style={{
        position: "fixed", width: 600, height: 600,
        background: "radial-gradient(circle, rgba(79,143,255,0.06) 0%, transparent 70%)",
        top: "50%", left: "50%", transform: "translate(-50%, -50%)",
        pointerEvents: "none",
      }} />

      <div style={{
        position: "relative", zIndex: 1,
        width: 400, background: "var(--s1)",
        border: "1px solid var(--b1)", borderRadius: 16,
        padding: "40px 36px 36px",
        boxShadow: "0 24px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.03) inset",
      }}>
        {/* Branding */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{
            width: 44, height: 44,
            background: "var(--acc2)", border: "1px solid rgba(79,143,255,0.18)",
            borderRadius: 12, display: "inline-flex", alignItems: "center", justifyContent: "center",
            fontSize: 20, fontWeight: 700, color: "var(--acc)", marginBottom: 16,
            letterSpacing: "-0.02em",
          }}>D</div>
          <div style={{ fontSize: 18, fontWeight: 600, color: "var(--t1)", letterSpacing: "-0.03em" }}>
            D&apos;Angelo Marmoleria
          </div>
          <div style={{ fontSize: 12, color: "var(--t3)", marginTop: 4, letterSpacing: "0.02em" }}>
            Sistema de presupuestos
          </div>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "10px 14px", background: "rgba(255,69,58,0.08)",
            border: "1px solid rgba(255,69,58,0.18)", borderRadius: 8,
            fontSize: 13, color: "var(--red)", marginBottom: 18,
            animation: "fadeUp 0.2s ease",
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 18 }}>
            <label htmlFor="username" style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--t2)", marginBottom: 6 }}>
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
              style={{
                width: "100%", padding: "11px 14px",
                background: "var(--s3)", border: `1px solid ${error ? "var(--red)" : "var(--b1)"}`,
                borderRadius: 10, color: "var(--t1)", fontSize: 14,
                fontFamily: "inherit", outline: "none",
                transition: "border-color 0.15s, box-shadow 0.15s",
              }}
              onFocus={e => { e.currentTarget.style.borderColor = "var(--acc)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(79,143,255,0.12)"; }}
              onBlur={e => { e.currentTarget.style.borderColor = error ? "var(--red)" : "var(--b1)"; e.currentTarget.style.boxShadow = "none"; }}
            />
          </div>

          <div style={{ marginBottom: 18 }}>
            <label htmlFor="password" style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--t2)", marginBottom: 6 }}>
              Contraseña
            </label>
            <div style={{ position: "relative" }}>
              <input
                id="password"
                type={showPw ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                required
                style={{
                  width: "100%", padding: "11px 42px 11px 14px",
                  background: "var(--s3)", border: `1px solid ${error ? "var(--red)" : "var(--b1)"}`,
                  borderRadius: 10, color: "var(--t1)", fontSize: 14,
                  fontFamily: "inherit", outline: "none",
                  transition: "border-color 0.15s, box-shadow 0.15s",
                }}
                onFocus={e => { e.currentTarget.style.borderColor = "var(--acc)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(79,143,255,0.12)"; }}
                onBlur={e => { e.currentTarget.style.borderColor = error ? "var(--red)" : "var(--b1)"; e.currentTarget.style.boxShadow = "none"; }}
              />
              <button
                type="button"
                onClick={() => setShowPw(!showPw)}
                aria-label={showPw ? "Ocultar contraseña" : "Mostrar contraseña"}
                style={{
                  position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
                  background: "none", border: "none", color: "var(--t3)", cursor: "pointer",
                  padding: 4, display: "flex", alignItems: "center",
                }}
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
            style={{
              width: "100%", padding: 12,
              background: loading ? "rgba(79,143,255,0.4)" : "var(--acc)",
              color: "#fff", border: "none", borderRadius: 10,
              fontSize: 14, fontWeight: 600, fontFamily: "inherit",
              cursor: loading ? "wait" : "pointer",
              transition: "background 0.15s, transform 0.1s",
              marginTop: 6, letterSpacing: "-0.01em",
            }}
          >
            {loading ? "Verificando..." : "Iniciar sesión"}
          </button>
        </form>

        <div style={{ textAlign: "center", marginTop: 24, fontSize: 11, color: "var(--t4)", letterSpacing: "0.02em" }}>
          Acceso exclusivo para operadores
        </div>
      </div>
    </div>
  );
}
