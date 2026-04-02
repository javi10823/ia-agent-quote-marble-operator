import { fmtARS, fmtUSD } from "@/lib/format";

interface Props {
  totalArs: number | null;
  totalUsd: number | null;
}

export default function PricingSummary({ totalArs, totalUsd }: Props) {
  if (!totalArs && !totalUsd) return null;
  return (
    <div style={{
      marginTop: 20, padding: "16px 20px", borderRadius: 10,
      background: "var(--s3)", border: "1px solid var(--b2)",
      display: "flex", justifyContent: "space-between", alignItems: "center",
    }}>
      <span style={{ fontSize: 14, fontWeight: 600, color: "var(--t1)" }}>PRESUPUESTO TOTAL</span>
      <div style={{ textAlign: "right" }}>
        {totalArs && (
          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--t1)" }}>
            {fmtARS(totalArs)} <span style={{ color: "var(--t3)", fontWeight: 400, fontSize: 13 }}>mano de obra</span>
          </div>
        )}
        {totalUsd && (
          <div style={{ fontSize: 15, fontWeight: 600, color: "var(--acc)", marginTop: 2 }}>
            + {fmtUSD(totalUsd)} <span style={{ color: "var(--t3)", fontWeight: 400, fontSize: 13 }}>material</span>
          </div>
        )}
      </div>
    </div>
  );
}
