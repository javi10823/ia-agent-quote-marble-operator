/**
 * Bloque `.aud-trail` per-row · SOURCE / REGLA / CALC / IVA / SUMA.
 * Solo renderea cuando `auditOn` está activo (toggle global del toolbar).
 */
import type { AuditEntry } from "@/lib/api";

interface Props {
  entries: AuditEntry[];
}

export function AuditTrail({ entries }: Props) {
  if (!entries.length) return null;
  return (
    <div className="aud-trail" data-testid="aud-trail">
      {entries.map((e, i) => (
        <span key={`${e.kind}-${i}`} className="at-row">
          <span className="at-k">{e.kind}</span>
          <span className="at-v">
            {e.kind === "CALC" || e.kind === "IVA" || e.kind === "SUMA" ? (
              <span className="calc">{e.text}</span>
            ) : (
              e.text
            )}
          </span>
        </span>
      ))}
    </div>
  );
}
