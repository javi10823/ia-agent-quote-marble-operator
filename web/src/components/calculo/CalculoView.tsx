/**
 * Container del paso 4 · Cálculo. Coordina los 4 estados visuales
 * (loading / A / B / C) + toggles + chat drawer.
 *
 * Mocks-first per decisión Javi: cifras canon del mockup 07-paso4-A-v4.
 * Toggles tipo cliente / sobrante / stock son visual-only en este PR
 * (Sprint 4 los conecta al recompute).
 *
 * Mismo patrón de grid interno que ContextView (1fr o 1fr/480px cuando
 * el chat scoped está abierto). NO modifica el chrome layout del PR #456.
 */
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useCalculo } from "@/lib/hooks/useCalculo";
import { useAuditMode } from "@/lib/hooks/useAuditMode";
import { IaAuditBanner } from "@/components/observability/IaAuditBanner";
import { CalcBanner } from "./CalcBanner";
import { CalcChatPanel } from "./CalcChatPanel";
import { CalcConfirmBar } from "./CalcConfirmBar";
import { CalcSectionFlete } from "./CalcSectionFlete";
import { CalcSectionLabor } from "./CalcSectionLabor";
import { CalcSectionMaterial } from "./CalcSectionMaterial";
import { CalcSectionMerma } from "./CalcSectionMerma";
import { CalcSectionPiletas } from "./CalcSectionPiletas";
import { CalcToolbar } from "./CalcToolbar";
import { DatosPdfDetails } from "./DatosPdfDetails";
import { GrandTotal } from "./GrandTotal";
import { PatchErrorBanner } from "./PatchErrorBanner";

interface Props {
  quoteId: string;
}

export function CalculoView({ quoteId }: Props) {
  const { data, state, error, toggles, recalculate, applyFix, setToggle } = useCalculo(quoteId);
  const [chatOpen, setChatOpen] = useState(false);
  const router = useRouter();

  // Sprint 3 observability-per-row · audit ahora es global (TopBar).
  // Antes (PR #465 paso-4): useEffect local + toggle en CalcToolbar.
  // Ahora: useAuditMode encapsula el body[data-audit] sync + persistencia.
  // `auditOn` se usa para gatear AuditChip + AuditTrail per-row.
  const { auditOn } = useAuditMode();

  if (state === "loading" && !data) {
    return (
      <div className="col" data-testid="calculo-loading">
        <div className="section-head">
          <div>
            <div className="meta">Paso 4 de 5 · Cálculo</div>
            <h2>Generando presupuesto…</h2>
          </div>
        </div>
        <div className="ph-rows">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skel long" />
          ))}
        </div>
      </div>
    );
  }

  if (!data || (state === "error" && !data?.patchError)) {
    return (
      <div className="col" data-testid="calculo-error">
        <div className="section-head">
          <h2>No pude cargar el cálculo</h2>
        </div>
        <p className="font-mono" style={{ fontSize: 12, color: "var(--error)" }}>
          {error ?? "Error desconocido"}
        </p>
      </div>
    );
  }

  const isPatchError = state === "error" && !!data.patchError;

  return (
    <div
      data-testid="calculo-view"
      data-state={isPatchError ? "B" : chatOpen ? "C" : "A"}
      data-chat-open={chatOpen}
      style={{
        // Sprint 3 paso-4 fix-up #2 · grid SIEMPRE 1fr. El chat es overlay
        // fixed (ver operator-shared.css §.chat) y NO ocupa columna en el grid.
        display: "grid",
        gridTemplateColumns: "1fr",
        gap: 24,
        minHeight: 0,
      }}
    >
      <div className="col">
        <div className="section-head">
          <div>
            <div className="meta">Paso 4 de 5 · Cálculo</div>
            <h2>
              Presupuesto calculado
              {isPatchError && (
                <span className="warn-inline" style={{ marginLeft: 8 }}>
                  ⚠ presupuesto modificado
                </span>
              )}
            </h2>
          </div>
          <CalcToolbar
            toggles={toggles}
            onChange={setToggle}
            onRecalculate={recalculate}
            busy={state === "loading"}
          />
        </div>

        <IaAuditBanner />

        {isPatchError && data.patchError ? (
          <PatchErrorBanner
            traceId={data.patchError.traceId}
            msg={data.patchError.msg}
            onFix={applyFix}
            onRecalcFromScratch={recalculate}
          />
        ) : (
          <CalcBanner summary={data.bannerSummary} adjustments={data.bannerAdjustments} />
        )}

        <CalcSectionMaterial
          rows={data.material.rows}
          subtotal={data.material.subtotal}
          auditOn={auditOn}
        />
        <CalcSectionMerma merma={data.merma} auditOn={auditOn} onFix={applyFix} />
        <CalcSectionLabor
          rows={data.labor.rows}
          subtotal={data.labor.subtotal}
          auditOn={auditOn}
          ivaVisible={toggles.ivaVisible}
        />
        <CalcSectionPiletas piletas={data.piletas} />
        <CalcSectionFlete flete={data.flete} auditOn={auditOn} />

        <GrandTotal totals={data.totals} />

        {!isPatchError && <DatosPdfDetails defaults={data.datosPdf} />}

        <CalcConfirmBar
          quoteId={quoteId}
          blocked={isPatchError}
          blockedReason={
            isPatchError ? "resolvé la merma fantasma antes de generar PDF" : undefined
          }
          onOpenChat={() => setChatOpen(true)}
          onConfirm={() => router.push(`/quotes/${quoteId}/pdf`)}
        />
      </div>

      {chatOpen && <CalcChatPanel quoteId={quoteId} onClose={() => setChatOpen(false)} />}
    </div>
  );
}
