/**
 * `/login` · Sprint 3 sub-PR auth.
 *
 * Página standalone (sin chrome shell). Estilo via el patrón real del v2:
 * clases legacy de operator-shared.css (`.btn.primary`, `.input`,
 * `.eyebrow`) + inline `style={{}}` para layout. NO usa Tailwind utility
 * classes porque el proyecto NO tiene directivas `@tailwind` → esas
 * utilities no se compilan (fix del visual check del PR #463).
 */
"use client";

import { Suspense, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/auth";

const inputStyle: React.CSSProperties = { width: "100%", marginTop: 0 };

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
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg)",
        padding: "0 16px",
      }}
    >
      <div style={{ width: "100%", maxWidth: 360 }}>
        <h1
          style={{
            fontFamily: "var(--serif)",
            fontStyle: "italic",
            fontWeight: 500,
            fontSize: 26,
            color: "var(--ink)",
            margin: 0,
            letterSpacing: "-0.3px",
          }}
        >
          D&apos;Angelo
        </h1>
        <div
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11,
            textTransform: "uppercase",
            letterSpacing: "0.6px",
            color: "var(--ink-mute)",
            marginTop: 6,
          }}
        >
          Acceso operador
        </div>

        {reason === "expired" && (
          <div
            data-testid="login-expired"
            style={{
              marginTop: 16,
              padding: "10px 12px",
              border: "1px solid var(--line-strong)",
              borderRadius: "var(--r-md)",
              background: "var(--surface)",
              color: "var(--warn)",
              fontSize: 13,
            }}
          >
            Tu sesión expiró. Iniciá sesión de nuevo.
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          style={{
            marginTop: 24,
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          <input
            type="text"
            name="username"
            placeholder="Usuario"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
            disabled={loading}
            className="input"
            style={inputStyle}
          />
          <input
            type="password"
            name="password"
            placeholder="Contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={loading}
            className="input"
            style={inputStyle}
          />
          {error && (
            <div data-testid="login-error" style={{ color: "var(--error)", fontSize: 13 }}>
              {error}
            </div>
          )}
          <button
            type="submit"
            className="btn primary"
            disabled={loading || !username || !password}
            style={{ width: "100%", justifyContent: "center" }}
          >
            {loading ? "Entrando…" : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
