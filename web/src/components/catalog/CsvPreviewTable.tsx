"use client";

import clsx from "clsx";

interface Props {
  headers: string[];
  rows: Record<string, unknown>[];
  mappedFields: Set<string>;
  maxRows?: number;
}

export default function CsvPreviewTable({ headers, rows, mappedFields, maxRows = 20 }: Props) {
  const displayRows = rows.slice(0, maxRows);
  const remaining = rows.length - displayRows.length;

  return (
    <div className="border border-b1 rounded-lg overflow-hidden">
      <div className="overflow-x-auto max-h-[320px] overflow-y-auto">
        <table className="w-full border-collapse min-w-max">
          <thead className="sticky top-0 z-10">
            <tr className="bg-s3">
              {headers.map(h => (
                <th
                  key={h}
                  className={clsx(
                    "px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-[0.06em] border-b border-b1 whitespace-nowrap",
                    mappedFields.has(h) ? "text-t2" : "text-t4",
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    {h}
                    {mappedFields.has(h) ? (
                      <span className="w-1 h-1 rounded-full bg-grn shrink-0" title="Campo mapeado" />
                    ) : (
                      <span className="w-1 h-1 rounded-full bg-amb shrink-0" title="Sin mapear" />
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, i) => (
              <tr key={i} className={clsx(i % 2 === 1 && "bg-white/[0.02]")}>
                {headers.map(h => (
                  <td
                    key={h}
                    className={clsx(
                      "px-3 py-[7px] text-xs font-mono border-b border-white/[0.03] whitespace-nowrap max-w-[200px] truncate",
                      mappedFields.has(h) ? "text-t2" : "text-t4",
                    )}
                  >
                    {row[h] != null ? String(row[h]) : ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {remaining > 0 && (
        <div className="px-3 py-2 text-[11px] text-t3 bg-s2 border-t border-b1 text-center">
          ...y {remaining} fila{remaining > 1 ? "s" : ""} mas
        </div>
      )}
    </div>
  );
}
