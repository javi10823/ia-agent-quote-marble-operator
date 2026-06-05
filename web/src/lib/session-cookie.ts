/**
 * Constante compartida del nombre de la cookie httpOnly que sincroniza
 * el JWT del backend Railway a vercel.app · Sprint 4 ssr-auth.
 *
 * Vive en su propio módulo porque Next 14 prohíbe exports custom desde
 * archivos `route.ts` (solo HTTP method handlers).
 */
export const SESSION_COOKIE_NAME = "vercel_session_token";
