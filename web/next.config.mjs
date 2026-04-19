/** @type {import('next').NextConfig} */

// Normaliza NEXT_PUBLIC_API_URL:
//  - Si viene vacío → warning + fallback localhost (dev only).
//  - Si viene con http://  y estamos en build de producción → upgradeamos
//    a https:// para evitar Mixed Content (el browser bloquea requests
//    http desde una página https, y el error que llega a la UI es un
//    "Failed to fetch" críptico). Railway siempre expone https por
//    default con su dominio *.up.railway.app, así que el upgrade es
//    siempre safe en producción.
//  - Si viene con https:// o es localhost → dejar pasar.
function normalizeApiUrl(raw) {
  if (!raw) {
    if (process.env.NODE_ENV === "production") {
      // No hard-fail en build; devolvemos placeholder que va a fallar
      // con un mensaje claro en runtime (el apiFetch wrapper).
      console.warn("[next.config] NEXT_PUBLIC_API_URL no está definido en producción");
      return "https://api-url-not-configured.invalid";
    }
    return "http://localhost:8000";
  }
  // Quitar trailing slash
  raw = raw.replace(/\/+$/, "");
  // En prod, forzar https si viene http:// (excepto localhost)
  if (
    process.env.NODE_ENV === "production" &&
    raw.startsWith("http://") &&
    !raw.startsWith("http://localhost") &&
    !raw.startsWith("http://127.0.0.1")
  ) {
    const upgraded = raw.replace(/^http:\/\//, "https://");
    console.warn(
      `[next.config] Upgrading NEXT_PUBLIC_API_URL de http:// a https:// para evitar Mixed Content en prod: ${raw} → ${upgraded}`
    );
    return upgraded;
  }
  return raw;
}

const API_URL = normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);

const nextConfig = {
  // skipTrailingSlashRedirect: sin esto, Next.js (Vercel) auto-redirige
  // `/api/catalog/` → `/api/catalog` con 308. Pero el endpoint real del
  // backend FastAPI vive en `/api/catalog/` (con slash). Al quitarlo,
  // FastAPI responde 307 devolviendo el slash → el browser sigue el
  // redirect cross-origin a Railway → cookie con SameSite=Lax no viaja
  // → 401 → handleAuthError redirige a /login.
  // Con este flag el path original se mantiene intacto hasta el rewrite
  // proxy, todo pasa same-origin, la cookie viaja.
  skipTrailingSlashRedirect: true,

  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_URL}/api/:path*`,
      },
      {
        source: "/files/:path*",
        destination: `${API_URL}/files/:path*`,
      },
    ];
  },
};

export default nextConfig;
