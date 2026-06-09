/**
 * Página /quotes/{id}/audit · Sprint 4 audit-trail-copy.
 *
 * Vista pretty del audit log del quote (no clipboard plain text · esa la
 * cubre el botón del topbar). Renderiza:
 *   - Header con meta (quote_id, status, totales) + summary chips
 *   - Timeline vertical de eventos con coloring de latencia
 *   - Tabla de calls agregados (tools + tokens + duración chat)
 *   - JSON breakdown colapsable
 *   - 3 botones copy: "Copiar todo", "Copiar timeline", "Copiar JSON"
 *
 * Server Component · usa Bearer token SSR (PR #469) + `getAuditLog`
 * (real o mock según USE_REAL_API). Hereda chrome del `[id]/layout.tsx`.
 *
 * NO tiene mockup oficial (feature v1.0 nueva · excepción justificada
 * del Mockup Fidelity Gate).
 */
import { getAuditLog } from "@/lib/api";
import { getServerToken } from "@/lib/auth-server";
import { AuditView } from "@/components/audit/AuditView";

export default async function AuditPage({ params }: { params: { id: string } }) {
  const bearerToken = getServerToken();
  let audit;
  let loadError: string | null = null;
  try {
    audit = await getAuditLog(params.id, { bearerToken, full: true });
  } catch (err) {
    loadError = err instanceof Error ? err.message : "Error desconocido al cargar audit";
  }

  if (!audit || loadError) {
    return (
      <div className="col" data-testid="audit-error">
        <div className="section-head">
          <h2>No pude cargar el audit log</h2>
        </div>
        <p className="font-mono" style={{ fontSize: 12, color: "var(--error)" }}>
          {loadError ?? "Quote no encontrado"}
        </p>
      </div>
    );
  }

  return <AuditView audit={audit} />;
}
