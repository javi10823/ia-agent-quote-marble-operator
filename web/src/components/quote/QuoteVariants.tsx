/**
 * Variantes del presupuesto (multi-material) · selector en Topbar.
 *
 * Si el presupuesto tiene derivados (o es derivado de otro), muestra un
 * <select> con cada variante (material + total) para saltar entre ellas.
 * Sin variantes no renderiza nada. Los errores de red se ignoran: es una
 * ayuda de navegación, no puede romper la pantalla.
 */
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listQuoteVariants, type QuoteVariant } from "@/lib/api";

export function variantLabel(v: QuoteVariant): string {
  const total = v.total_ars > 0 ? ` · $${Math.round(v.total_ars).toLocaleString("es-AR")}` : "";
  return `${v.material || "Sin material"}${total}`;
}

export function QuoteVariants({ quoteId }: { quoteId: string }) {
  const router = useRouter();
  const [variants, setVariants] = useState<QuoteVariant[]>([]);

  useEffect(() => {
    const ctrl = new AbortController();
    listQuoteVariants(quoteId, { signal: ctrl.signal })
      .then(setVariants)
      .catch(() => setVariants([]));
    return () => ctrl.abort();
  }, [quoteId]);

  if (variants.length < 2) return null;

  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
      Variantes
      <select
        data-testid="quote-variants"
        value={quoteId}
        onChange={(e) => {
          if (e.target.value !== quoteId) router.push(`/quotes/${e.target.value}/calculo`);
        }}
      >
        {variants.map((v) => (
          <option key={v.id} value={v.id}>
            {variantLabel(v)}
          </option>
        ))}
      </select>
    </label>
  );
}
