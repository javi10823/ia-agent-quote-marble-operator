/**
 * Item de lista mobile (mockup 23). Cada item es un Link al detalle
 * (Sprint 2: detalle mobile no implementado · Sprint 4). En Sprint 2.5
 * navega al paso 2 contexto como el desktop.
 */
import Link from "next/link";
import type { DashboardQuote } from "@/lib/api";
import { StatusChip } from "./StatusChip";
import { SourceTag } from "./SourceTag";
import { formatAmount, formatM2, resolveQuoteSource } from "./format";

export function QuoteListItem({ quote }: { quote: DashboardQuote }) {
  return (
    <Link
      href={`/quotes/${quote.id}/contexto`}
      className="mlist-item"
      data-testid={`mobile-item-${quote.id}`}
      data-status={quote.status}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 6,
        padding: "14px 16px",
        borderBottom: "1px solid var(--line)",
        color: "inherit",
        textDecoration: "none",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <SourceTag source={resolveQuoteSource(quote)} />
        <StatusChip status={quote.status} />
      </div>
      <div style={{ fontSize: 14, color: "var(--ink)" }}>{quote.client}</div>
      <div className="font-mono" style={{ fontSize: 11, color: "var(--ink-mute)" }}>
        {quote.material} · {formatM2(quote.m2)}
      </div>
      <div className="font-mono" style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 2 }}>
        {formatAmount(quote.amount, quote.currency)}
      </div>
    </Link>
  );
}
