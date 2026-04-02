import { useMemo } from "react";
import type { QuoteDetail } from "@/lib/api";
import { fmtARS, fmtUSD, fmtQty } from "@/lib/format";
import { tableStyle, thStyle, tdStyle } from "@/lib/constants";
import { useBreakpoints } from "@/lib/useMediaQuery";
import Section from "./Section";
import MetaItem from "./MetaItem";
import ReqField from "./ReqField";
import InfoBar from "./InfoBar";
import PricingSummary from "./PricingSummary";
import SourceFilesSection from "./SourceFilesSection";

interface Props {
  quote: QuoteDetail | null;
  breakdown: Record<string, any> | null;
  onSwitchToChat: () => void;
}

export default function DetailView({ quote, breakdown, onSwitchToChat }: Props) {
  const { isMobile, isTablet } = useBreakpoints();

  const pieces = useMemo(
    () => breakdown?.sectors?.flatMap((s: any) => s.pieces || []) || [],
    [breakdown]
  );
  const moItems = useMemo(
    () => (breakdown?.mo_items || []).map((m: any) => ({
      ...m,
      total: m.total ?? (m.quantity ?? 0) * (m.unit_price ?? 0),
    })),
    [breakdown]
  );
  const totalMO = useMemo(
    () => moItems.reduce((s: number, m: any) => s + (m.total || 0), 0),
    [moItems]
  );
  const merma = breakdown?.merma;
  const totalM2 = breakdown?.material_m2 || 0;
  const discountPct = breakdown?.discount_pct || 0;

  if (!quote) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* A. RESUMEN */}
      <Section title="Resumen">
        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : isTablet ? "1fr 1fr" : "1fr 1fr 1fr 1fr", gap: isMobile ? 12 : 16 }}>
          <MetaItem label="Cliente" value={quote.client_name || "—"} />
          <MetaItem label="Proyecto" value={quote.project || "—"} />
          <MetaItem label="Material" value={quote.material || "—"} />
          <MetaItem label="Fecha" value={new Date(quote.created_at).toLocaleDateString("es-AR")} />
          <MetaItem label="Demora" value={breakdown?.delivery_days || "—"} />
          <MetaItem label="Origen" value={quote.source === "web" ? "Web (chatbot)" : "Operador"} />
          <MetaItem label="Total ARS" value={quote.total_ars ? fmtARS(quote.total_ars) : "—"} highlight />
          <MetaItem label="Total USD" value={quote.total_usd ? fmtUSD(quote.total_usd) : "—"} highlight />
        </div>
      </Section>

      {/* A2. SOURCE FILES */}
      {quote.source_files && quote.source_files.length > 0 && (
        <SourceFilesSection files={quote.source_files} />
      )}

      {/* B. SOLICITUD */}
      {breakdown && (
        <Section title="Solicitud">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <ReqField label="Material" value={breakdown.material_name || "—"} />
            <ReqField label="Superficie" value={totalM2 ? `${fmtQty(totalM2)} m²` : "—"} />
            <ReqField label="Moneda" value={breakdown.material_currency || "—"} />
            <ReqField label="Precio/m²" value={breakdown.material_price_unit ? (breakdown.material_currency === "USD" ? fmtUSD(breakdown.material_price_unit) : fmtARS(breakdown.material_price_unit)) : "—"} />
            <ReqField label="Plazo" value={breakdown.delivery_days || "—"} />
            <ReqField label="Proyecto" value={breakdown.project || "—"} />
          </div>
        </Section>
      )}

      {/* C. DESGLOSE */}
      {breakdown && (pieces.length > 0 || moItems.length > 0) ? (
        <Section title="Desglose del Presupuesto">
          {/* Pieces */}
          {pieces.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--t1)", marginBottom: 8 }}>
                Material — {fmtQty(totalM2)} m²
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={thStyle}>Pieza</th>
                      <th style={{ ...thStyle, textAlign: "right" }}>Detalle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pieces.map((p: string, i: number) => (
                      <tr key={i} style={{ background: i % 2 === 1 ? "rgba(255,255,255,.03)" : "transparent" }}>
                        <td style={tdStyle}>{p}</td>
                        <td style={{ ...tdStyle, textAlign: "right", color: "var(--t3)" }}></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Merma */}
          {merma && (
            <InfoBar
              icon="📐"
              label="Merma"
              status={merma.aplica ? "APLICA" : "NO APLICA"}
              detail={merma.motivo || ""}
            />
          )}

          {/* MO */}
          {moItems.length > 0 && (
            <div style={{ marginTop: 16, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--t1)", marginBottom: 8 }}>Mano de Obra</div>
              <div style={{ overflowX: "auto" }}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={thStyle}>Ítem</th>
                      <th style={{ ...thStyle, textAlign: "right" }}>Cant</th>
                      <th style={{ ...thStyle, textAlign: "right" }}>Precio</th>
                      <th style={{ ...thStyle, textAlign: "right" }}>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {moItems.map((m: any, i: number) => (
                      <tr key={i} style={{ background: i % 2 === 1 ? "rgba(255,255,255,.03)" : "transparent" }}>
                        <td style={tdStyle}>{m.description}</td>
                        <td style={{ ...tdStyle, textAlign: "right" }}>{fmtQty(m.quantity)}</td>
                        <td style={{ ...tdStyle, textAlign: "right" }}>{fmtARS(m.unit_price)}</td>
                        <td style={{ ...tdStyle, textAlign: "right" }}>{fmtARS(m.total)}</td>
                      </tr>
                    ))}
                    <tr style={{ background: "rgba(255,255,255,.05)" }}>
                      <td style={{ ...tdStyle, fontWeight: 600 }}>TOTAL MO</td>
                      <td style={tdStyle}></td>
                      <td style={tdStyle}></td>
                      <td style={{ ...tdStyle, textAlign: "right", fontWeight: 600 }}>{fmtARS(totalMO)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Discount */}
          <InfoBar
            icon="🏷️"
            label="Descuentos"
            status={discountPct > 0 ? `APLICA ${discountPct}%` : "NO APLICA"}
            detail={discountPct > 0 ? `${discountPct}% sobre material` : "Particular sin umbral de m²"}
          />

          {/* Grand total */}
          <PricingSummary totalArs={quote.total_ars} totalUsd={quote.total_usd} />
        </Section>
      ) : (
        <Section title="Desglose">
          <div style={{ fontSize: 13, color: "var(--t3)" }}>
            Este presupuesto no tiene datos de desglose estructurados. Consultá el historial de chat para ver los detalles.
          </div>
          <button onClick={onSwitchToChat} style={{
            marginTop: 10, background: "none", border: "none", color: "var(--acc)",
            fontSize: 12, cursor: "pointer", fontFamily: "inherit", padding: 0,
          }}>
            Ver chat →
          </button>
        </Section>
      )}
    </div>
  );
}
