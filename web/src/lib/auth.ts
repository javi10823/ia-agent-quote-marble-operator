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
