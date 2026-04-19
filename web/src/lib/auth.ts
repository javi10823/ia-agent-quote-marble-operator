// Ver lib/api.ts para explicación completa — llamamos DIRECTO a Railway.
function resolveApiBase(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/+$/, "");
  }
  return "http://localhost:8000";
}

const API_BASE = resolveApiBase();
const STORAGE_KEY = "dangelo:username";

export async function login(username: string, password: string): Promise<{ ok: boolean; username: string }> {
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
  // (Home hero "Buen día, X."). La sesión real vive en cookie.
  if (typeof window !== "undefined" && data?.username) {
    try { localStorage.setItem(STORAGE_KEY, data.username); } catch {}
  }
  return data;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (typeof window !== "undefined") {
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
  }
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
