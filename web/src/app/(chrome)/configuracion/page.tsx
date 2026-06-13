/**
 * Configuración · sub-PR 22.2.a config-ui-page.
 *
 * Reemplaza el placeholder por el ConfigForm real con 6 defaults
 * operativos editables. Fetch + persist viven en el component cliente
 * (los catálogos son cross-quote · no necesitan SSR aggressive).
 *
 * Scope CSS: `.config-v2` wrapper · ver globals.css (~15-20 LOC media
 * query) · operator-shared.css INTACTO.
 */
import { ConfigForm } from "@/components/config/ConfigForm";

export default function ConfiguracionPage() {
  return (
    <div className="config-v2">
      <div className="topbar">
        <div className="crumbs">
          <span className="now">Configuración</span>
        </div>
      </div>
      <div className="body" data-testid="configuracion-page">
        <div className="col">
          <div className="section-head">
            <h2>Defaults operativos</h2>
            <span className="meta">
              Aplican cuando el brief no especifica · editás y guardás · Marina puede sobrescribir
              manualmente en cada presupuesto desde /contexto.
            </span>
          </div>
          <ConfigForm />
        </div>
      </div>
    </div>
  );
}
