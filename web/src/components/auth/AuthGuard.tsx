/**
 * Guard de auth client-side · Sprint 3 sub-PR auth (Opción 1).
 *
 * Reemplaza la protección de rutas via middleware edge (imposible en la
 * arquitectura cross-origin — ver `web/src/middleware.ts`). Verifica
 * `getSession()` al mount y redirige a /login si no hay sesión.
 *
 * Activación: solo enforcea cuando `NEXT_PUBLIC_REQUIRE_AUTH === 'true'`.
 * Por default (CI, dev local) es no-op → los 48 E2E previos siguen verdes.
 * Se usa un flag dedicado y NO `NEXT_PUBLIC_API_URL` porque esa var ya
 * está seteada a localhost:8000 en playwright.config.ts desde Sprint 2.
 */
"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getSession } from "@/lib/auth";

const PUBLIC_PATHS = ["/login"];

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    // Auth off por default. Solo enforcea con NEXT_PUBLIC_REQUIRE_AUTH==='true'.
    // (NEXT_PUBLIC_API_URL NO sirve como gate: ya está seteada a localhost:8000
    // en playwright.config.ts desde Sprint 2 → rompería los 48 E2E previos.)
    if (process.env.NEXT_PUBLIC_REQUIRE_AUTH !== "true") {
      setChecked(true);
      return;
    }
    // Rutas públicas → sin gate.
    if (PUBLIC_PATHS.includes(pathname)) {
      setChecked(true);
      return;
    }
    // Verificar sesión local.
    if (!getSession()) {
      router.replace(`/login?redirect=${encodeURIComponent(pathname)}`);
      return;
    }
    setChecked(true);
  }, [pathname, router]);

  if (!checked) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-bg"
        data-testid="auth-checking"
      >
        <div className="font-mono text-sm text-ink-mute">Verificando sesión…</div>
      </div>
    );
  }

  return <>{children}</>;
}
