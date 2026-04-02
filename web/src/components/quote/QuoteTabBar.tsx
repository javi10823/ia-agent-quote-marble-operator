import TabBtn from "@/components/ui/TabBtn";

export type QuoteTab = "detail" | "chat" | "compare";

interface Props {
  tab: QuoteTab;
  setTab: (t: QuoteTab) => void;
  canShowDetail: boolean;
  canShowCompare: boolean;
}

export default function QuoteTabBar({ tab, setTab, canShowDetail, canShowCompare }: Props) {
  return (
    <div style={{
      display: "flex", gap: 0, borderBottom: "1px solid var(--b1)",
      background: "var(--s1)", paddingLeft: 28,
    }}>
      <TabBtn active={tab === "detail"} onClick={() => setTab("detail")} disabled={!canShowDetail}>Detalle</TabBtn>
      <TabBtn active={tab === "chat"} onClick={() => setTab("chat")}>Chat</TabBtn>
      {canShowCompare && (
        <TabBtn active={tab === "compare"} onClick={() => setTab("compare")}>Comparar</TabBtn>
      )}
    </div>
  );
}
