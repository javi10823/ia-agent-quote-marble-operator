import TabBtn from "@/components/ui/TabBtn";

interface Props {
  tab: "detail" | "chat";
  setTab: (t: "detail" | "chat") => void;
  canShowDetail: boolean;
}

export default function QuoteTabBar({ tab, setTab, canShowDetail }: Props) {
  return (
    <div style={{
      display: "flex", gap: 0, borderBottom: "1px solid var(--b1)",
      background: "var(--s1)", paddingLeft: 28,
    }}>
      <TabBtn active={tab === "detail"} onClick={() => setTab("detail")} disabled={!canShowDetail}>Detalle</TabBtn>
      <TabBtn active={tab === "chat"} onClick={() => setTab("chat")}>Chat</TabBtn>
    </div>
  );
}
