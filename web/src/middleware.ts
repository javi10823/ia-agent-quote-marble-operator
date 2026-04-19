import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Auth middleware DESHABILITADO.
 *
 * Contexto: cuando el frontend (vercel.app) llamaba al backend a través
 * del rewrite proxy de Next.js, el `Set-Cookie` de login quedaba atado
 * al dominio vercel.app. El middleware podía leer esa cookie y usarla
 * como gate de rutas.
 *
 * Después del fix cross-origin (PR #322), el frontend llama DIRECTO a
 * railway.app. El `Set-Cookie` se asocia a railway.app (distinto
 * dominio). Este middleware, que corre en el edge de Vercel, sólo ve
 * cookies de vercel.app → no encuentra `auth_token` → redirige a
 * `/login` aunque el usuario esté perfectamente logueado contra
 * Railway → loop infinito al intentar entrar al dashboard.
 *
 * La auth real vive en el backend FastAPI. Si una request no está
 * autenticada, el backend devuelve 401 directamente. No necesitamos
 * una segunda capa en el edge de Vercel — es incluso contraproducente
 * porque no puede ver el cookie correcto.
 *
 * Nota: cualquier usuario que navegue a `/` sin estar logueado va a
 * ver el dashboard shell con errores de API (401s). Si después de uso
 * real queremos auto-redirigir al login en ese caso, lo hacemos
 * client-side chequeando localStorage (ya seteamos el username del
 * user logueado en `lib/auth.ts`).
 */
export function middleware(_request: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
