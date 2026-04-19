import FileLink from "@/components/ui/FileLink";
import { DOT } from "@/lib/chars";
import { STATUS, backBtnStyle, badgeStyle } from "@/lib/constants";
import { useBreakpoints } from "@/lib/useMediaQuery";
import type { QuoteDetail } from "@/lib/api";

interface Props {
  quote: QuoteDetail | null;
  onBack: () => void;
}

export default function QuoteHeader({ quote, onBack }: Props) {
  const { isMobile } = useBreakpoints();
  const st = STATUS[quote?.status || "draft"];
  return (
    <div style={{
      display: "flex", alignItems: isMobile ? "flex-start" : "center",
      flexDirection: isMobile ? "column" : "row",
      justifyContent: "space-between",
      padding: isMobile ? "12px 18px" : "18px 36px",
      borderBottom: "1px solid var(--b1)",
      flexShrink: 0, background: "var(--bg)",
      gap: isMobile ? 10 : 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <button onClick={onBack} style={backBtnStyle} aria-label="Volver al listado">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
        </button>
        <div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <span style={{
              fontFamily: "var(--font-serif), Georgia, serif",
              fontStyle: "italic",
              fontSize: isMobile ? 18 : 22,
              fontWeight: 500,
              color: "var(--t1)",
              letterSpacing: "-0.01em",
              lineHeight: 1.15,
            }}>{quote?.client_name || "Nuevo presupuesto"}</span>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              fontSize: 12, color: st.color, fontFamily: "var(--font-sans)",
            }}>
              <span style={{ width: 7, height: 7, borderRadius: 999, background: st.color }} />
              {st.label}
            </span>
            {quote?.source === "web" && (
              <span style={{
                fontSize: 9, fontFamily: "var(--font-mono)",
                fontWeight: 600, letterSpacing: "0.08em",
                padding: "2px 6px", borderRadius: 4,
                border: "1px solid rgba(180,143,224,0.3)",
                color: "#b48fe0",
              }}>WEB</span>
            )}
          </div>
          <div style={{
            fontSize: 12, color: "var(--t3)", marginTop: 3,
            fontFamily: "var(--font-sans)",
          }}>
            {quote?.project}{quote?.material ? ` ${DOT} ${quote.material}` : ""}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {quote?.drive_pdf_url && <FileLink href={quote.drive_pdf_url} label="PDF Drive" color="var(--acc)" />}
        {quote?.drive_excel_url && <FileLink href={quote.drive_excel_url} label="Excel Drive" color="#5cb38f" />}
        {!quote?.drive_pdf_url && quote?.pdf_url && <FileLink href={quote.pdf_url} label="PDF" color="#d46b60" />}
      </div>
    </div>
  );
}
