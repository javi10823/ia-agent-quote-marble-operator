/**
 * Route Handler `/api/session` · Sprint 4 ssr-auth (Opción D).
 *
 * Sincroniza el JWT que el backend devuelve en login al frontend Vercel,
 * en una cookie httpOnly scoped a vercel.app (same-origin con la página).
 * Esta cookie SOLO se lee en SSR (server components) para inyectar el JWT
 * como `Authorization: Bearer <token>` en fetches server-side hacia Railway.
 *
 * Por qué una cookie *extra* y no usar la de Railway:
 * - La cookie httpOnly que setea Railway (`auth_token`) tiene
 *   `Domain=railway.app`. El server de Vercel NUNCA la ve (es cross-origin).
 * - El JWT viaja en el BODY de la respuesta del login (`token: body.token`)
 *   y ya queda en localStorage del cliente. Esa misma string la usamos acá
 *   para crear una cookie scopeada a vercel.app (same-origin → Next puede
 *   leerla con `cookies()` de `next/headers`).
 * - El backend FastAPI ya soporta `Authorization: Bearer <token>` como
 *   fallback nativo del cookie cross-origin (ver
 *   `api/app/core/auth.py:166` extract_token_from_request) → cero cambios
 *   en el backend.
 *
 * Razones de las decisiones:
 * - `httpOnly: true` → no expuesta al JS del browser (defense in depth aunque
 *   el token también esté en localStorage por el flow de login). Igual
 *   reduce surface en caso de XSS en otras rutas.
 * - `sameSite: "lax"` → la cookie vive en el mismo origin que la página;
 *   no necesita el caso cross-origin de `"none"`.
 * - `secure: true` en prod, `false` en dev (localhost sin TLS).
 * - `maxAge ≈ 24h` razonable. El JWT del backend tiene su propio `exp`
 *   (~60min según APP_CONFIG); si vence antes que la cookie, el primer
 *   401 dispara `handleApiError` → redirect /login (flujo ya cubierto).
 * - `path: "/"` para que se vea desde cualquier ruta SSR.
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE_NAME } from "@/lib/session-cookie";

const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24; // 24h

function isProd(): boolean {
  return process.env.NODE_ENV === "production";
}

interface PostBody {
  token?: string;
}

/** POST `/api/session` body: `{ token: "<JWT>" }` → setea cookie y devuelve 204. */
export async function POST(request: NextRequest) {
  let body: PostBody;
  try {
    body = (await request.json()) as PostBody;
  } catch {
    return NextResponse.json({ ok: false, reason: "invalid-json" }, { status: 400 });
  }
  const token = typeof body.token === "string" ? body.token.trim() : "";
  if (!token) {
    return NextResponse.json({ ok: false, reason: "missing-token" }, { status: 400 });
  }
  const res = new NextResponse(null, { status: 204 });
  res.cookies.set({
    name: SESSION_COOKIE_NAME,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    secure: isProd(),
    maxAge: COOKIE_MAX_AGE_SECONDS,
    path: "/",
  });
  return res;
}

/** DELETE `/api/session` → limpia la cookie y devuelve 204. */
export async function DELETE() {
  const res = new NextResponse(null, { status: 204 });
  res.cookies.set({
    name: SESSION_COOKIE_NAME,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: isProd(),
    maxAge: 0,
    path: "/",
  });
  return res;
}
