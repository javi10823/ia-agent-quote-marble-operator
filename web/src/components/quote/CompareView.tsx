import { useMemo } from "react";
import type { QuoteCompareResponse } from "@/lib/api";
import { fmtARS, fmtUSD, fmtQty } from "@/lib/format";
import Section from "./Section";

interface Props {
  data: QuoteCompareResponse;
}

// Use relative URLs — Next.js rewrites proxy /api/ and /files/ to the backend

export default function CompareView({ data }: Props) {
  const variants = useMemo(() => {
    return data.quotes.map((q) => {
      const bd = q.quote_breakdown || {};
      const moItems = (bd.mo_items || []) as { quantity?: number; unit_price?: number }[];
      const moTotal = moItems.reduce(
        (s, m) => s + (m.quantity || 0) * (m.unit_price || 0),
        0
      );
      const merma = bd.merma as { aplica?: boolean; motivo?: string } | undefined;
      const currency = (bd.material_currency || "USD") as "USD" | "ARS";

      return {
        id: q.id,
        material: q.material || bd.material_name || "—",
        currency,
        priceM2: bd.material_price_unit || 0,
        m2: bd.material_m2 || 0,
        totalMat: bd.material_total || 0,
        discountPct: bd.discount_pct || 0,
        moTotal,
        merma: merma?.aplica ? (merma.motivo || "Aplica") : "No aplica",
        delivery: bd.delivery_days || "—",
        totalArs: q.total_ars || bd.total_ars || 0,
        totalUsd: q.total_usd || bd.total_usd || 0,
        pdfUrl: q.pdf_url,
      };
    });
  }, [data]);

  // Find cheapest by total_usd (or total_ars if no USD)
  const bestIdx = useMemo(() => {
    let idx = 0;
    let best = Infinity;
    variants.forEach((v, i) => {
      const val = v.totalUsd || v.totalArs;
      if (val && val < best) {
        best = val;
        idx = i;
      }
    });
    return idx;
  }, [variants]);

  const n = variants.length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Header */}
      <Section title="Comparativo de materiales">
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, color: "var(--t2)" }}>
            Cliente: <strong style={{ color: "var(--t1)" }}>{data.client_name}</strong>
          </span>
          <span style={{ fontSize: 13, color: "var(--t2)" }}>
            Proyecto: <strong style={{ color: "var(--t1)" }}>{data.project}</strong>
          </span>
          <span style={{ fontSize: 13, color: "var(--t2)" }}>
            {n} variante{n > 1 ? "s" : ""}
          </span>
        </div>
      </Section>

      {/* Comparison table */}
      <Section title="Comparativa de precios">
        <div style={{ overflowX: "auto" }}>
          <table style={{
            width: "100%", borderCollapse: "collapse",
            border: "1px solid var(--b1)", borderRadius: 8, overflow: "hidden",
            minWidth: 400 + n * 150,
          }}>
            <thead>
              <tr>
                <th style={headerCell}></th>
                {variants.map((v, i) => (
                  <th key={v.id} style={{
                    ...headerCell, textAlign: "center",
                    background: i === bestIdx ? "rgba(48,209,88,0.12)" : "rgba(255,255,255,.05)",
                    borderLeft: "1px solid var(--b1)",
                  }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--t1)" }}>
                      {v.material}
                    </div>
                    {i === bestIdx && (
                      <div style={{ fontSize: 9, color: "var(--grn)", fontWeight: 600, marginTop: 2 }}>
                        MAS ECONOMICO
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <Row label="Precio / m²" values={variants.map(v =>
                v.currency === "USD" ? fmtUSD(v.priceM2) : fmtARS(v.priceM2)
              )} bestIdx={bestIdx} odd />
              <Row label="Superficie" values={variants.map(v =>
                `${fmtQty(v.m2)} m²`
              )} bestIdx={bestIdx} />
              <Row label="Total Material" values={variants.map(v =>
                v.currency === "USD" ? fmtUSD(v.totalMat) : fmtARS(v.totalMat)
              )} bestIdx={bestIdx} odd />
              <Row label="Descuento" values={variants.map(v =>
                v.discountPct ? `${v.discountPct}%` : "No aplica"
              )} bestIdx={bestIdx} />
              <Row label="Mano de Obra" values={variants.map(v =>
                fmtARS(v.moTotal)
              )} bestIdx={bestIdx} odd />
              <Row label="Merma" values={variants.map(v => v.merma)} bestIdx={bestIdx} />
              <Row label="Plazo" values={variants.map(v => v.delivery)} bestIdx={bestIdx} odd />

              {/* Total rows */}
              <tr style={{ borderTop: "2px solid var(--b2)" }}>
                <td style={{ ...cellBase, fontWeight: 700, fontSize: 14, color: "var(--t1)" }}>
                  Total ARS
                </td>
                {variants.map((v, i) => (
                  <td key={v.id} style={{
                    ...cellBase, textAlign: "center", fontWeight: 700, fontSize: 14,
                    color: "var(--t1)",
                    background: i === bestIdx ? "rgba(48,209,88,0.08)" : "transparent",
                    borderLeft: "1px solid var(--b1)",
                  }}>
                    {v.totalArs ? fmtARS(v.totalArs) : "—"}
                  </td>
                ))}
              </tr>
              <tr>
                <td style={{ ...cellBase, fontWeight: 700, fontSize: 14, color: "var(--acc)" }}>
                  Total USD
                </td>
                {variants.map((v, i) => (
                  <td key={v.id} style={{
                    ...cellBase, textAlign: "center", fontWeight: 700, fontSize: 14,
                    color: i === bestIdx ? "var(--grn)" : "var(--acc)",
                    background: i === bestIdx ? "rgba(48,209,88,0.08)" : "transparent",
                    borderLeft: "1px solid var(--b1)",
                  }}>
                    {v.totalUsd ? fmtUSD(v.totalUsd) : "—"}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </Section>

      {/* Actions */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <a
          href={`/api/quotes/${data.parent_id}/compare/pdf`}
          target="_blank"
          rel="noopener noreferrer"
          style={btnStyle}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
          </svg>
          Descargar comparativo PDF
        </a>
        {variants.map((v) => v.pdfUrl && (
          <a
            key={v.id}
            href={`${v.pdfUrl}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{ ...btnStyle, background: "transparent", border: "1px solid var(--b2)" }}
          >
            PDF {v.material}
          </a>
        ))}
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

const headerCell: React.CSSProperties = {
  padding: "12px 14px", fontSize: 11, fontWeight: 600,
  color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.05em",
  background: "rgba(255,255,255,.03)", borderBottom: "1px solid var(--b1)",
  textAlign: "left",
};

const cellBase: React.CSSProperties = {
  padding: "10px 14px", fontSize: 13, color: "var(--t2)",
  borderBottom: "1px solid rgba(255,255,255,.04)",
};

const btnStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 8,
  padding: "8px 16px", borderRadius: 8,
  background: "var(--acc)", color: "#fff",
  fontSize: 13, fontWeight: 600, textDecoration: "none",
  border: "none", cursor: "pointer",
};

function Row({ label, values, bestIdx, odd }: {
  label: string;
  values: string[];
  bestIdx: number;
  odd?: boolean;
}) {
  return (
    <tr style={{ background: odd ? "rgba(255,255,255,.03)" : "transparent" }}>
      <td style={{ ...cellBase, fontWeight: 600, color: "var(--t1)", whiteSpace: "nowrap" }}>
        {label}
      </td>
      {values.map((val, i) => (
        <td key={i} style={{
          ...cellBase, textAlign: "center",
          background: i === bestIdx && odd ? "rgba(48,209,88,0.05)" : undefined,
          borderLeft: "1px solid var(--b1)",
        }}>
          {val}
        </td>
      ))}
    </tr>
  );
}
