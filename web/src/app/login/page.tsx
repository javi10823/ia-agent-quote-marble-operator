/**
 * `/login` · Sprint 3 sub-PR auth · re-diseño visual editorial.
 *
 * Aesthetic: refined minimalism · dark editorial. "Un cuarto de marmolería
 * oscuro con una sola pieza iluminada" — card al centro sobre un glow radial
 * tenue, con una hairline de acento arriba (motivo veta de mármol).
 *
 * Styling sin Tailwind utilities (no compilan — ver docs/known-issues.md):
 * inline `style={{}}` + CSS vars + un `<style>` scoped con clases `.login-*`
 * para lo que inline no puede (focus, hover, ::placeholder, @keyframes
 * stagger). NO toca operator-shared.css ni globals.css.
 *
 * Lógica del flow (submit, error, redirect, expired, loading) sin cambios.
 */
"use client";

import { Suspense, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") || "/";
  const reason = searchParams.get("reason");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ username, password });
      router.replace(redirect);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
      setLoading(false);
    }
  }

  return (
    <main className="login-root">
      <style>{LOGIN_CSS}</style>

      {/* Glow radial tenue detrás de la card · "pieza iluminada" */}
      <div className="login-glow" aria-hidden="true" />

      <section className="login-card" aria-labelledby="login-brand">
        {/* Hairline de acento · motivo veta */}
        <div className="login-vein" aria-hidden="true" />

        <header className="login-reveal login-d0">
          <h1
            id="login-brand"
            style={{
              fontFamily: "var(--serif)",
              fontStyle: "italic",
              fontWeight: 500,
              fontSize: 38,
              lineHeight: 1.05,
              letterSpacing: "-0.5px",
              color: "var(--ink)",
              margin: 0,
            }}
          >
            D&apos;Angelo
          </h1>
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              textTransform: "uppercase",
              letterSpacing: "2.5px",
              color: "var(--ink-mute)",
              marginTop: 10,
            }}
          >
            Acceso operador
          </div>
        </header>

        {reason === "expired" && (
          <div className="login-reveal login-d1 login-banner" role="status" data-testid="login-expired">
            Tu sesión expiró. Iniciá sesión de nuevo.
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ marginTop: 32 }}>
          <div className="login-reveal login-d1" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <label className="login-field">
              <span className="login-label">Usuario</span>
              <input
                type="text"
                name="username"
                placeholder="tu usuario"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
                disabled={loading}
                className="login-input"
                autoComplete="username"
              />
            </label>
            <label className="login-field">
              <span className="login-label">Contraseña</span>
              <input
                type="password"
                name="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loading}
                className="login-input"
                autoComplete="current-password"
              />
            </label>
          </div>

          {error && (
            <div className="login-error" role="alert" data-testid="login-error">
              {error}
            </div>
          )}

          <div className="login-reveal login-d2">
            <button
              type="submit"
              className="login-submit"
              disabled={loading || !username || !password}
            >
              {loading ? "Entrando…" : "Entrar"}
            </button>
          </div>
        </form>
      </section>

      <footer className="login-reveal login-d3 login-foot">
        D&apos;Angelo Operator · sistema interno
      </footer>
    </main>
  );
}

const LOGIN_CSS = `
.login-root {
  /* fixed + inset:0 fija el overlay al viewport real e ignora el
     body { min-width: 1440px } global de operator-shared.css — si no,
     en viewports < 1440 la card se descentra a la derecha. */
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: var(--bg);
  overflow-y: auto;
}
.login-glow {
  position: absolute;
  top: 38%;
  left: 50%;
  width: 620px;
  height: 620px;
  max-width: 140vw;
  transform: translate(-50%, -50%);
  background: radial-gradient(circle, rgba(169,193,214,0.10) 0%, rgba(169,193,214,0.03) 38%, transparent 68%);
  pointer-events: none;
  z-index: 0;
}
.login-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 400px;
  padding: 46px 40px 40px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow:
    inset 0 1px 0 rgba(232,237,229,0.05),
    0 1px 2px rgba(0,0,0,0.3),
    0 28px 56px -20px rgba(0,0,0,0.55);
  overflow: hidden;
}
.login-vein {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, var(--accent) 50%, transparent 100%);
  opacity: 0.5;
}
.login-banner {
  margin-top: 22px;
  padding: 10px 13px;
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--warn);
  background: rgba(232,237,229,0.04);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-md);
}
.login-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.login-label {
  font-family: var(--mono);
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--ink-mute);
}
.login-input {
  width: 100%;
  padding: 12px 14px;
  font-family: var(--sans);
  font-size: 14px;
  color: var(--ink);
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  outline: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}
.login-input::placeholder { color: var(--ink-mute); opacity: 0.6; }
.login-input:hover:not(:disabled) { border-color: var(--line-strong); }
.login-input:focus {
  border-color: var(--accent);
  background: var(--surface);
  box-shadow: 0 0 0 3px rgba(169,193,214,0.12);
}
.login-input:disabled { opacity: 0.55; cursor: not-allowed; }
.login-error {
  margin-top: 14px;
  font-size: 12.5px;
  color: var(--error);
  animation: loginFade 0.22s ease both;
}
.login-submit {
  width: 100%;
  margin-top: 24px;
  padding: 12px 24px;
  font-family: var(--sans);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.2px;
  color: var(--bg);
  background: var(--accent);
  border: none;
  border-radius: var(--r-md);
  cursor: pointer;
  transition: filter 0.18s ease, transform 0.05s ease, opacity 0.18s ease;
}
.login-submit:hover:not(:disabled) { filter: brightness(1.08); }
.login-submit:active:not(:disabled) { transform: translateY(1px); }
.login-submit:disabled { opacity: 0.45; cursor: not-allowed; }
.login-foot {
  position: relative;
  z-index: 1;
  margin-top: 22px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.5px;
  color: var(--ink-mute);
  opacity: 0.55;
}
.login-reveal {
  opacity: 0;
  animation: loginReveal 0.5s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}
.login-d0 { animation-delay: 0.05s; }
.login-d1 { animation-delay: 0.14s; }
.login-d2 { animation-delay: 0.23s; }
.login-d3 { animation-delay: 0.32s; }
@keyframes loginReveal {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes loginFade {
  from { opacity: 0; }
  to { opacity: 1; }
}
@media (max-width: 420px) {
  .login-card { padding: 34px 24px 30px; }
  #login-brand { font-size: 30px !important; }
}
@media (prefers-reduced-motion: reduce) {
  .login-reveal, .login-error { animation: none; opacity: 1; }
}
`;

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
