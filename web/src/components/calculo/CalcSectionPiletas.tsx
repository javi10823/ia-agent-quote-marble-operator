/**
 * Sección 04 · Piletas · formato `.piletas-inline` compacto.
 */
import type { PiletaSection } from "@/lib/api";

export function CalcSectionPiletas({ piletas }: { piletas: PiletaSection }) {
  return (
    <section className="calc-section piletas-inline" data-testid="calc-section-piletas">
      <div className="sh">
        <span className="num">04</span>
        <span className="ttl">Piletas</span>
        {piletas.variant === "na" ? (
          <span className="chip-na">{piletas.chipLabel}</span>
        ) : (
          <span className="chip-info">{piletas.chipLabel}</span>
        )}
        {piletas.sub && <span className="sub">{piletas.sub}</span>}
      </div>
    </section>
  );
}
