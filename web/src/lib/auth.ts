// Ver lib/api.ts para explicación completa — llamamos DIRECTO a Railway.
function resolveApiBase(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/+$/, "");
  }
  return "http://localhost:8000";
}

const API_BASE = resolveApiBase();
const STORAGE_KEY = "dangelo:username";
// JWT en localStorage. Fallback para clientes donde la cookie cross-origin
// no viaja (iOS Safari con ITP bloqueando third-party cookies). El backend
// acepta el token vía cookie O header `Authorization: Bearer` — si ambos
// están presentes, cookie gana (ver api/app/core/auth.py). En desktop el
// header queda como redundancia inofensiva; en mobile es el único canal.
const TOKEN_KEY = "dangelo:token";

export async function login(username: string, password: string): Promise<{ ok: boolean; username: string; token: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    credentials: "include",
  });
  if (res.status === 401) {
    const err = await res.json();
    throw new Error(err.detail || "Usuario o contraseña incorrectos");
  }
  if (!res.ok) throw new Error("Error de conexión");
  const data = await res.json();
  // Cacheamos el username del lado del cliente para saludos personalizados
  // (Home hero "Buen día, X."). La sesión real vive en cookie + token.
  if (typeof window !== "undefined") {
    try {
      if (data?.username) localStorage.setItem(STORAGE_KEY, data.username);
      if (data?.token) localStorage.setItem(TOKEN_KEY, data.token);
    } catch {}
  }
  return data;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (typeof window !== "undefined") {
    try {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(TOKEN_KEY);
    } catch {}
  }
}

/** JWT guardado tras el último login exitoso (o null si nunca se logueó o
 * corrió logout). Lo consume `apiFetch` para inyectar el header
 * `Authorization: Bearer <token>` como fallback cuando la cookie no viaja.
 *
 * NOTA seguridad: sí, localStorage es accesible desde JS y por lo tanto
 * vulnerable a XSS. Asumimos riesgo aceptable porque (a) la app es interna
 * de un único operador, (b) la alternativa — no poder usar mobile — es
 * peor, (c) el token expira a las 72hs. Si a futuro habilitamos acceso
 * multi-usuario o exponemos la app a terceros, mover a IndexedDB con
 * encriptación o a httpOnly cookie estricta (lo que requeriría rewrite
 * de arquitectura). */
export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

/** Username del operador logueado, si está disponible. null si no hay sesión
 * guardada en localStorage (no consulta al backend). */
export function getCurrentUsername(): string | null {
  if (typeof window === "undefined") return null;
  try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
}

/** Capitaliza y limpia el username para mostrar en saludos.
 * "javier" → "Javier", "javier.hernandez" → "Javier". */
export function prettyFirstName(u: string | null): string {
  if (!u) return "";
  const first = u.split(/[.\s_-]/)[0] || u;
  return first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
}
