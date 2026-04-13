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
      padding: isMobile ? "10px 14px" : "14px 28px",
      borderBottom: "1px solid var(--b1)",
      flexShrink: 0, background: "var(--s1)",
      gap: isMobile ? 10 : 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <button onClick={onBack} style={backBtnStyle}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>
        </button>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 16, fontWeight: 600, color: "var(--t1)" }}>{quote?.client_name || "Nuevo presupuesto"}</span>
            <span style={{ ...badgeStyle, background: st.bg, color: st.color }}>● {st.label}</span>
            {quote?.source === "web" && <span style={{ ...badgeStyle, background: "rgba(138,43,226,.15)", color: "#a855f7" }}>WEB</span>}
          </div>
          <div style={{ fontSize: 12, color: "var(--t3)", marginTop: 2 }}>
            {quote?.project}{quote?.material ? ` ${DOT} ${quote.material}` : ""}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {quote?.pdf_url && <FileLink href={quote.pdf_url} label="PDF" color="#ff6b63" />}
        {quote?.drive_pdf_url && <FileLink href={quote.drive_pdf_url} label="PDF Drive" color="var(--acc)" />}
        {quote?.drive_excel_url && <FileLink href={quote.drive_excel_url} label="Excel Drive" color="#34d399" />}
      </div>
    </div>
  );
}
