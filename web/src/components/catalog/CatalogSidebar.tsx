"use client";

import clsx from "clsx";

interface CatalogMeta {
  name: string;
  item_count: number;
  last_updated: string | null;
  size_kb: number;
}

interface Props {
  catalogs: CatalogMeta[];
  selected: string;
  onSelect: (name: string) => void;
  hasUnsavedChanges: boolean;
}

const GROUPS = [
  { label: "Mano de obra", items: ["labor", "delivery-zones"] },
  {
    label: "Materiales",
    items: [
      "materials-silestone", "materials-purastone", "materials-dekton",
      "materials-neolith", "materials-puraprima", "materials-laminatto",
      "materials-granito-nacional", "materials-granito-importado", "materials-marmol",
    ],
  },
  { label: "Piletas y otros", items: ["sinks", "stock", "architects", "config"] },
];

const DISPLAY_NAME: Record<string, string> = {
  labor: "Mano de obra",
  "delivery-zones": "Zonas de envio",
  "materials-silestone": "Silestone",
  "materials-purastone": "Purastone",
  "materials-dekton": "Dekton",
  "materials-neolith": "Neolith",
  "materials-puraprima": "Puraprima",
  "materials-laminatto": "Laminatto",
  "materials-granito-nacional": "Granito Nacional",
  "materials-granito-importado": "Granito Importado",
  "materials-marmol": "Marmol",
  sinks: "Piletas",
  stock: "Stock retazos",
  architects: "Arquitectas",
  config: "Configuracion",
};

export default function CatalogSidebar({ catalogs, selected, onSelect, hasUnsavedChanges }: Props) {
  return (
    <aside className="md:w-[240px] shrink-0 bg-s1 border-b md:border-b-0 md:border-r border-b1 overflow-x-auto md:overflow-x-hidden overflow-y-auto flex md:flex-col gap-1 md:gap-0 px-2 py-2 md:py-0">
      {GROUPS.map((group, gi) => (
        <div key={group.label}>
          {/* Group header */}
          <div className={clsx(
            "hidden md:flex items-center gap-2 px-3 pt-4 pb-2",
            gi > 0 && "mt-1 border-t border-b1",
          )}>
            <span className="text-[10px] font-semibold text-t4 uppercase tracking-[0.10em]">
              {group.label}
            </span>
          </div>

          {/* Items */}
          {group.items.map(name => {
            const meta = catalogs.find(c => c.name === name);
            const isActive = selected === name;
            const displayName = DISPLAY_NAME[name] || name;

            return (
              <button
                key={name}
                onClick={() => onSelect(name)}
                className={clsx(
                  "group flex items-center gap-2.5 w-full md:w-full shrink-0 px-3 py-2 md:py-[9px] rounded-lg text-left transition-all duration-100 font-sans border-none cursor-pointer whitespace-nowrap md:whitespace-normal",
                  isActive
                    ? "bg-acc/[0.10] text-acc border-l-2 border-l-acc md:ml-0"
                    : "bg-transparent text-t2 hover:bg-white/[0.04] hover:text-t1",
                )}
              >
                {/* Name + unsaved dot */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={clsx("text-[13px] font-medium truncate", isActive ? "text-acc" : "text-t1")}>
                      {displayName}
                    </span>
                    {isActive && hasUnsavedChanges && (
                      <span className="w-1.5 h-1.5 rounded-full bg-amb shrink-0" title="Cambios sin guardar" />
                    )}
                  </div>
                  <div className={clsx("text-[10px] mt-0.5 truncate", isActive ? "text-acc/50" : "text-t3")}>
                    {meta ? `${meta.item_count} items` : "\u2014"}
                    {meta?.last_updated ? ` \u00B7 ${meta.last_updated}` : ""}
                  </div>
                </div>

                {/* Count badge */}
                {meta && (
                  <span className={clsx(
                    "text-[10px] px-[7px] py-px rounded-full font-mono shrink-0 hidden md:inline-flex",
                    isActive ? "bg-acc/[0.15] text-acc/70" : "bg-white/[0.05] text-t3",
                  )}>
                    {meta.item_count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      ))}
    </aside>
  );
}
