/**
 * `/login` · Sprint 3 sub-PR auth.
 *
 * Página standalone (sin chrome shell — no hay sidebar/topbar). Form de
 * usuario + contraseña → `POST /api/auth/login`. Usa tokens del design
 * system v2 (ink/accent/surface/line). NO usa operator-shared.css.
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

  const inputCls =
    "w-full rounded-r-md border border-line bg-surface px-3 py-2 text-ink placeholder:text-ink-mute focus:border-line-strong focus:outline-none disabled:opacity-50";

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <h1 className="font-serif text-2xl italic text-ink">D&apos;Angelo</h1>
        <p className="mt-1 font-mono text-xs uppercase tracking-wide text-ink-mute">
          Acceso operador
        </p>

        {reason === "expired" && (
          <div
            className="mt-4 rounded-r-md border border-line-strong bg-surface px-3 py-2 text-sm text-warn"
            data-testid="login-expired"
          >
            Tu sesión expiró. Iniciá sesión de nuevo.
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-3">
          <input
            type="text"
            name="username"
            placeholder="Usuario"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
            disabled={loading}
            className={inputCls}
          />
          <input
            type="password"
            name="password"
            placeholder="Contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={loading}
            className={inputCls}
          />
          {error && (
            <div className="text-sm text-error" data-testid="login-error">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={loading || !username || !password}
            className="w-full rounded-r-md bg-accent px-4 py-2 text-bg disabled:opacity-50"
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
