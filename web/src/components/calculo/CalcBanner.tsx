/**
 * Banner `.calc-banner` · línea 1 resumen sistema + línea 2 ajustes Valentina.
 * Estado A/C. (Estado B usa PatchErrorBanner.)
 */
import type { ValentinaAdjustment } from "@/lib/api";

interface Props {
  summary: string;
  adjustments: ValentinaAdjustment[];
}

export function CalcBanner({ summary, adjustments }: Props) {
  return (
    <div className="calc-banner" data-testid="calc-banner">
      <div className="l1">
        <span>{summary}</span>
      </div>
      {adjustments.length > 0 && (
        <div className="l2">
          <em>Valentina</em> aplicó:
          <span className="adj-list">
            {adjustments.map((a, i) => (
              <span key={i}>
                {a.text}
                {i < adjustments.length - 1 && <span className="pt"> · </span>}
              </span>
            ))}
          </span>
        </div>
      )}
    </div>
  );
}
