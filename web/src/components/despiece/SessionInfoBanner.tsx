/**
 * Banner `.ia-banner.system` arriba de la tabla del despiece cuando hay
 * chat scoped abierto (mockup 17).
 *
 * Copy literal: "CHAT ABIERTO SOBRE R5 · ZÓCALO PERIMETRAL · HACE 8 MIN"
 * + sub explicando persistencia intra-quote.
 *
 * Sprint 3 error-states decisión Javi E: feature de session persistente
 * 24h es OUT scope (es feature backend), solo mostramos el copy del banner.
 */
"use client";

interface Props {
  context: string;
}

export function SessionInfoBanner({ context }: Props) {
  return (
    <div className="ia-banner system" data-testid="session-info-banner">
      <div className="text">
        {context}
        <div className="sub">
          Sesión persistente intra-quote · se borra cuando cierres el quote o pasen 24h sin tocarlo
        </div>
      </div>
    </div>
  );
}
