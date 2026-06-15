/**
 * Tabla del dashboard desktop (mockup 25).
 *
 * Cada row es clickeable → navega a `/quotes/[id]/contexto`.
 * Reusa clases legacy `.quote-table`, `.row`, `.cell` de operator-shared.css.
 */
"use client";

import Link from "next/link";
import type { DashboardQuote } from "@/lib/api";
import { StatusChip } from "./StatusChip";
import { SourceTag } from "./SourceTag";
import { formatAmount, formatM2, resolveQuoteSource } from "./format";

interface Props {
  quotes: DashboardQuote[];
  loading: boolean;
}

export function QuoteTable({ quotes, loading }: Props) {
  if (loading && quotes.length === 0) {
    return (
      <div className="ph-rows" data-testid="quote-table-loading">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="skel long" />
        ))}
      </div>
    );
  }

  if (quotes.length === 0) {
    return (
      <div className="dash-empty" data-testid="quote-table-empty">
        <p className="font-mono" style={{ fontSize: 12, color: "var(--ink-mute)" }}>
          No hay presupuestos que cumplan con los filtros.
        </p>
      </div>
    );
  }

  return (
    <table className="quote-table" data-testid="quote-table">
      <thead>
        <tr>
          <th>Cliente</th>
          <th>Material</th>
          <th className="right">m²</th>
          <th className="right">Monto</th>
          <th>Estado</th>
          <th>Última actividad</th>
        </tr>
      </thead>
      <tbody>
        {quotes.map((q) => (
          <tr
            key={q.id}
            data-testid={`quote-row-${q.id}`}
            data-status={q.status}
            style={{ cursor: "pointer" }}
          >
            <td>
              <Link
                href={`/quotes/${q.id}/contexto`}
                style={{ display: "block", color: "inherit" }}
                data-testid={`quote-link-${q.id}`}
              >
                <div>{q.client}</div>
                <div style={{ marginTop: 4 }}>
                  <SourceTag source={resolveQuoteSource(q)} />
                </div>
              </Link>
            </td>
            <td>{q.material}</td>
            <td className="right font-mono">{formatM2(q.m2)}</td>
            <td className="right font-mono">{formatAmount(q.amount, q.currency)}</td>
            <td>
              <StatusChip status={q.status} />
            </td>
            <td className="font-mono" style={{ fontSize: 11, color: "var(--ink-mute)" }}>
              hace {q.lastActivityDays}d
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
