import { fmtARS, fmtUSD } from "@/lib/format";

interface Props {
  totalArs: number | null;
  totalUsd: number | null;
}

export default function PricingSummary({ totalArs, totalUsd }: Props) {
  if (!totalArs && !totalUsd) return null;
  return (
    <div style={{
      marginTop: 24, padding: "22px 28px", borderRadius: 12,
      background: "var(--s2)", border: "1px solid var(--b1)",
      display: "flex", justifyContent: "space-between", alignItems: "flex-end",
    }}>
      <div>
        <div style={{
          fontSize: 10, fontFamily: "var(--font-mono)", fontWeight: 500,
          color: "var(--t4)", letterSpacing: "0.14em", textTransform: "uppercase",
          marginBottom: 8,
        }}>Presupuesto total</div>
        <div style={{
          fontFamily: "var(--font-serif), Georgia, serif", fontStyle: "italic",
          fontSize: 15, color: "var(--t3)", fontWeight: 400,
          letterSpacing: "-0.01em",
        }}>Contado · 30 días demora</div>
      </div>
      <div style={{ textAlign: "right" }}>
        {totalArs && (
          <div style={{
            fontFamily: "var(--font-serif), Georgia, serif",
            fontSize: 28, fontWeight: 500, color: "var(--t1)",
            letterSpacing: "-0.02em", lineHeight: 1, marginBottom: 2,
          }}>
            {fmtARS(totalArs)}
          </div>
        )}
        {totalUsd && (
          <div style={{
            fontSize: 13, fontWeight: 500, color: "var(--acc)",
            marginTop: 6, fontFamily: "var(--font-mono)",
            letterSpacing: "-0.01em",
          }}>
            {fmtUSD(totalUsd)}
          </div>
        )}
      </div>
    </div>
  );
}
