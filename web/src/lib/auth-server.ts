/**
 * Server-side auth helpers · Sprint 4 ssr-auth (Opción D).
 *
 * Solo se importa desde Server Components o Route Handlers. NUNCA desde
 * client components — `cookies()` de `next/headers` solo existe en server.
 *
 * Pareja del Route Handler `/api/session`: el cliente POSTea el JWT (que
 * tiene en localStorage post-login) y este helper lo lee desde SSR para
 * inyectarlo como `Authorization: Bearer <token>` en fetches al backend.
 */
import { cookies } from "next/headers";
import { SESSION_COOKIE_NAME } from "@/lib/session-cookie";

/**
 * Lee la cookie httpOnly `vercel_session_token` (sincronizada en login via
 * `/api/session`). Devuelve `null` si no hay sesión SSR válida — el caller
 * decide cómo degradar (típicamente `ssrFallbackHeader` en `real.ts`).
 *
 * NUNCA throw — el comportamiento esperado en SSR sin cookie es "no auth"
 * (caso pre-login o cookie expirada / borrada).
 */
export function getServerToken(): string | null {
  try {
    const store = cookies();
    const cookie = store.get(SESSION_COOKIE_NAME);
    if (!cookie) return null;
    const value = cookie.value?.trim();
    return value ? value : null;
  } catch {
    // `cookies()` lanza si se llama fuera de un Server Component / Route
    // Handler. En esos casos retornamos null (no auth) en vez de propagar.
    return null;
  }
}
