/**
 * Cliente de auth · Sprint 3 sub-PR auth.
 *
 * Opción 1 (client-side gate · recomendada por PR #322): la sesión se
 * trackea en localStorage. El `auth_token` real es una cookie httpOnly
 * scoped a railway.app — NO accesible ni por el JS ni por el middleware
 * edge de Vercel (por eso `middleware.ts` queda no-op).
 *
 * El enforcement de seguridad lo hace el backend: cualquier `/api/*` sin
 * cookie válida devuelve 401. El gate client-side es solo UX (evitar
 * mostrar el shell a alguien sin sesión).
 */

const SESSION_KEY = "op_session_v1"; // versionado por si cambia el shape

const API_URL = process.env.NEXT_PUBLIC_API_URL;

export interface Session {
  username: string;
  /** JWT que el backend devuelve en el BODY del login (no la cookie httpOnly). */
  token: string;
  loginAt: number;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export async function login(credentials: LoginCredentials): Promise<Session> {
  if (!API_URL) {
    throw new Error("NEXT_PUBLIC_API_URL no configurada — el modo mock no soporta login real");
  }

  const response = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // CRÍTICO: el browser maneja la cookie httpOnly de railway.app cross-origin.
    credentials: "include",
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    if (response.status === 401) throw new Error("Credenciales inválidas");
    throw new Error(`Error ${response.status}`);
  }

  const body = (await response.json()) as { ok: boolean; username: string; token: string };

  // Sprint 4 ssr-auth (Opción D): sincronizar el JWT a una cookie httpOnly
  // de vercel.app via `/api/session` para que `[id]/layout.tsx` (Server
  // Component) la lea en SSR e inyecte como Bearer header al backend
  // Railway. Esperamos esta sync ANTES de retornar — sin esto, un navigate
  // inmediato post-login todavía vería el SSR fallback (em-dashes).
  // Best-effort: si la sync falla (network blip), seguimos · client-side
  // sigue funcionando con la cookie cross-origin de Railway, solo el SSR
  // queda degradado al fallback (mismo comportamiento previo a este PR).
  try {
    await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: body.token }),
    });
  } catch (err) {
    // Fix-up #1 PR #469 · NICE-TO-HAVE audit · loguear best-effort fails.
    // No bloqueamos el login si la sync falla (sigue funcionando · solo SSR
    // queda degradado al fallback), pero dejamos rastro diagnosticable en
    // producción para que un futuro 503 / network blip se note rápido.
    console.warn("[auth] Sync con /api/session falló (login)", err);
  }

  const session: Session = {
    username: body.username,
    token: body.token,
    loginAt: Date.now(),
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export async function logout(): Promise<void> {
  if (API_URL) {
    try {
      await fetch(`${API_URL}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Best-effort — el logout client-side no depende del backend.
    }
  }
  // Sprint 4 ssr-auth (Opción D): limpiar cookie httpOnly vercel session.
  // Best-effort · si falla, el SSR queda con token stale hasta 24h pero el
  // backend la rechazará y `handleApiError` reanudará el redirect a /login.
  try {
    await fetch("/api/session", { method: "DELETE" });
  } catch (err) {
    // Fix-up #1 PR #469 · NICE-TO-HAVE audit · loguear best-effort fails.
    console.warn("[auth] Sync con /api/session falló (logout)", err);
  }
  clearSession();
}

export function getSession(): Session | null {
  if (typeof window === "undefined") return null; // SSR-safe
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(SESSION_KEY);
}

/**
 * Helper para `lib/api/real.ts` (sub-PR api-integration): ante un 401
 * del backend (sesión expirada), limpia la sesión local y manda a /login.
 */
export function handleApiError(response: Response): void {
  if (response.status === 401) {
    clearSession();
    if (typeof window !== "undefined") {
      window.location.href = "/login?reason=expired";
    }
  }
}
