"use client";
import React, { useState } from "react";
import CopyButton from "./CopyButton";
import SuggestedCandidates, {
  SuggestedCandidate,
  TramoWithSuggestions,
} from "./SuggestedCandidates";
import { dualReadRetry as apiDualReadRetry } from "@/lib/api";

// Helpers:
// - `safeNum`: para ARITMÉTICA (totales, m² derivado). Convierte null a 0
//   porque un tramo sin medir contribuye 0 al total — esa es la semántica
//   correcta del "no sé".
// - `displayNum`: para DISPLAY. Devuelve "—" si el valor es null/undefined/
//   NaN. NO sustituye por "0.00" porque "0.00" es MENTIRA para el operador:
//   el backend dijo "no pude medir esto" (DUDOSO/UNANCHORED) y la UI tiene
//   que mostrarlo como "falta medida", no como "mide cero". Un 0.00 false
//   positivo podría hacer que el operador confirme un despiece roto sin
//   darse cuenta — eso ya pasó una vez, no queremos repetirlo.
const MISSING = "—";
const safeNum = (n: unknown): number =>
  typeof n === "number" && Number.isFinite(n) ? n : 0;
const displayNum = (n: unknown): string =>
  typeof n === "number" && Number.isFinite(n) ? n.toFixed(2) : MISSING;

// Normaliza el shape del payload dual_read: garantiza que sectores/tramos/
// zocalos sean arrays y que FieldValue no sea null/undefined. Preserva los
// valores null internos (valor, ml, alto_m) — son señal de "no medí esto"
// que el display muestra como MISSING.
const normalizeField = (f: unknown): FieldValue => {
  const obj = (f && typeof f === "object" ? (f as Record<string, unknown>) : {}) as Partial<FieldValue>;
  const raw = (obj as { valor?: unknown }).valor;
  return {
    valor: typeof raw === "number" && Number.isFinite(raw) ? raw : null,
    status: typeof obj.status === "string"
      ? obj.status
      : ((typeof raw === "number" && Number.isFinite(raw)) ? "CONFIRMADO" : "UNANCHORED"),
    opus: typeof obj.opus === "number" ? obj.opus : null,
    sonnet: typeof obj.sonnet === "number" ? obj.sonnet : null,
  };
};

const normalizeDualReadData = (raw: DualReadData): DualReadData => {
  const sectores = Array.isArray(raw?.sectores) ? raw.sectores : [];
  return {
    ...raw,
    sectores: sectores.map((s) => ({
      ...s,
      tramos: (Array.isArray(s?.tramos) ? s.tramos : []).map((t) => ({
        ...t,
        largo_m: normalizeField(t?.largo_m),
        ancho_m: normalizeField(t?.ancho_m),
        m2: normalizeField(t?.m2),
        zocalos: (Array.isArray(t?.zocalos) ? t.zocalos : []).map((z) => {
          const ml = typeof z?.ml === "number" && Number.isFinite(z.ml) ? z.ml : null;
          const alto = typeof z?.alto_m === "number" && Number.isFinite(z.alto_m) ? z.alto_m : null;
          return {
            ...z,
            ml,
            alto_m: alto,
            status: typeof z?.status === "string" ? z.status : "CONFIRMADO",
            lado: typeof z?.lado === "string" ? z.lado : "trasero",
          } as Zocalo;
        }),
        frentin: Array.isArray(t?.frentin) ? t.frentin : [],
        regrueso: Array.isArray(t?.regrueso) ? t.regrueso : [],
        // PR #355 — normalizar suggested_candidates a lista (shape estable).
        // Filtramos objetos sin el mínimo shape esperado por el componente.
        suggested_candidates: Array.isArray(t?.suggested_candidates)
          ? t.suggested_candidates
              .filter(
                (c: unknown): c is SuggestedCandidate =>
                  typeof c === "object" &&
                  c !== null &&
                  typeof (c as SuggestedCandidate).valor === "number" &&
                  Number.isFinite((c as SuggestedCandidate).valor) &&
                  ((c as SuggestedCandidate).label === "mas_probable" ||
                    (c as SuggestedCandidate).label === "baja_confianza"),
              )
          : [],
      })),
      ambiguedades: Array.isArray(s?.ambiguedades) ? s.ambiguedades : [],
    })),
  };
};

interface FieldValue {
  opus?: number | null;
  sonnet?: number | null;
  // `valor: null` = el backend no pudo medir (DUDOSO/UNANCHORED). El display
  // tiene que mostrar "—" para señalar falta de dato; NO coaccionar a 0.
  valor: number | null;
  status: string;
}

interface Zocalo {
  lado: string;
  opus_ml?: number | null;
  sonnet_ml?: number | null;
  ml: number | null;
  alto_m: number | null;
  status: string;
  _manual?: boolean;
}

interface Tramo {
  id: string;
  descripcion: string;
  largo_m: FieldValue;
  ancho_m: FieldValue;
  m2: FieldValue;
  zocalos: Zocalo[];
  frentin: unknown[];
  regrueso: unknown[];
  // PR #355 — operator-assist. Se popula solo cuando el backend rescató
  // candidatas del pool pero el LLM las rechazó visualmente (`largo_m=null`).
  // Array estable — siempre list, nunca null.
  suggested_candidates?: SuggestedCandidate[];
  _manual?: boolean;
}

type AmbiguedadTipo = "DEFAULT" | "INFO" | "REVISION";
type Ambiguedad = string | { tipo: AmbiguedadTipo; texto: string };

interface Sector {
  id: string;
  tipo: string;
  tramos: Tramo[];
  m2_total?: FieldValue;
  ambiguedades: Ambiguedad[];
  _manual?: boolean;
}

interface PendingQuestionOption {
  value: string;
  label: string;
  apply?: Record<string, unknown>;
}

interface PendingQuestion {
  id: string;
  label: string;
  question: string;
  type: "radio_with_detail" | "text" | "select";
  options?: PendingQuestionOption[];
  detail_placeholder?: string;
}

interface PendingAnswer {
  id: string;
  value: string;
  detail?: string;
  alto_m?: number;
}

interface DualReadData {
  sectores: Sector[];
  requires_human_review: boolean;
  conflict_fields: string[];
  source: string;
  m2_warning?: string | null;
  view_type?: string;
  view_type_reason?: string;
  _retry?: boolean;
  /** Si Opus falló en el retry (timeout / error), el backend devuelve la
   *  card previa de Sonnet intacta + este flag. Mostramos un mensaje
   *  amigable pero preservamos las medidas que el operador ya tenía. */
  opus_error?: string;
  /** Preguntas que el operador tiene que responder antes de confirmar.
   *  Principio: nunca asumir — si el brief no lo dice y el plano no lo
   *  muestra, preguntar. Confirmar queda bloqueado hasta responder todas. */
  pending_questions?: PendingQuestion[];
}

// PR #71 — metadata del tipo de vista para el badge
const VIEW_TYPE_META: Record<string, { label: string; cls: string; emoji: string }> = {
  planta: {
    label: "Planta 2D",
    cls: "bg-emerald-500/10 text-emerald-400 border-emerald-400/30",
    emoji: "📐",
  },
  render_3d: {
    label: "Render 3D",
    cls: "bg-amber-500/10 text-amber-400 border-amber-400/30",
    emoji: "🎨",
  },
  elevation: {
    label: "Elevación",
    cls: "bg-sky-500/10 text-sky-400 border-sky-400/30",
    emoji: "↕️",
  },
  mixed: {
    label: "Vistas mixtas",
    cls: "bg-purple-500/10 text-purple-400 border-purple-400/30",
    emoji: "🗂️",
  },
  unknown: {
    label: "Tipo indeterminado",
    cls: "bg-gray-500/10 text-gray-400 border-gray-400/30",
    emoji: "❓",
  },
  texto: {
    label: "Desde texto",
    cls: "bg-indigo-500/10 text-indigo-300 border-indigo-400/30",
    emoji: "📝",
  },
};

interface Props {
  data: DualReadData;
  quoteId: string;
  onConfirm: (verified: DualReadData) => void;
  onRetry?: (newData: DualReadData) => void;
}

type IconStyle = { cls: string; char: string };
const STATUS_STYLE: Record<string, IconStyle> = {
  CONFIRMADO:   { cls: "bg-grn-bg text-grn",                        char: "✓" },
  ALERTA:       { cls: "bg-amb-bg text-amb",                        char: "!" },
  CONFLICTO:    { cls: "bg-[rgba(255,69,58,0.15)] text-err",        char: "✕" },
  DUDOSO:       { cls: "bg-[rgba(191,85,236,0.15)] text-[#bf55ec]", char: "?" },
  SOLO_SONNET:  { cls: "bg-grn-bg text-grn",                        char: "✓" },
  SOLO_OPUS:    { cls: "bg-grn-bg text-grn",                        char: "✓" },
  UNANCHORED:   { cls: "bg-amb-bg text-amb",                        char: "⚠" },
};

const STATUS_TITLE: Record<string, string> = {
  CONFIRMADO: "Ambos lectores coincidieron",
  ALERTA: "Diferencia menor — se tomó el promedio",
  CONFLICTO: "Conflicto entre lectores — requiere revisión",
  DUDOSO: "Valor dudoso — requiere revisión",
  SOLO_SONNET: "Solo Sonnet detectó este valor",
  SOLO_OPUS: "Solo Opus detectó este valor",
  UNANCHORED: "Este valor no coincide con las cotas del plano — corregí con doble-click",
};

function StatusIcon({
  status,
  onRemove,
}: {
  status: string;
  onRemove?: () => void;
}) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.CONFIRMADO;
  const baseCls = `inline-grid place-items-center w-[18px] h-[18px] rounded-[5px] text-[10px] font-bold ${s.cls}`;
  if (onRemove) {
    // PR #56 — la X de zócalos no confirmados ahora es clickeable para
    // remover el zócalo del despiece (caso típico: Dual Read sugirió un
    // zócalo por nicho visible, pero en realidad ese lado no lleva).
    return (
      <button
        type="button"
        onClick={onRemove}
        className={`${baseCls} cursor-pointer hover:opacity-80 hover:scale-110 transition-transform`}
        title="Remover este zócalo"
        aria-label="Remover este zócalo"
      >
        {s.char}
      </button>
    );
  }
  return (
    <span
      className={baseCls}
      title={STATUS_TITLE[status] || status}
      aria-label={STATUS_TITLE[status] || status}
    >
      {s.char}
    </span>
  );
}

function EditableNumber({
  field,
  onEdit,
  forceEditable = false,
  dblClickEdit = false,
}: {
  field: FieldValue;
  onEdit: (v: number) => void;
  forceEditable?: boolean;
  /** Si true, el campo arranca como label read-only; doble-click entra en
   *  edit mode. Enter/blur commit (solo si valor válido), Esc cancela. */
  dblClickEdit?: boolean;
}) {
  const alwaysEditable = forceEditable
    || field.status === "CONFLICTO"
    || field.status === "DUDOSO"
    || field.status === "UNANCHORED";
  const [editing, setEditing] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  const originalRef = React.useRef<number>(safeNum(field.valor));

  // PR #69 — tooltip revela Opus/Sonnet originales (cuando hay reconciliación)
  const tooltipParts: string[] = [];
  if (field.opus != null) tooltipParts.push(`Opus: ${field.opus}`);
  if (field.sonnet != null) tooltipParts.push(`Sonnet: ${field.sonnet}`);
  const reconcileTip = tooltipParts.length
    ? `Reconciliado — ${tooltipParts.join(" · ")}`
    : "";

  // Modo "siempre input" (legacy / manual / CONFLICTO / DUDOSO / UNANCHORED).
  // defaultValue undefined para valor null → input arranca vacío, el operador
  // lo completa. Si pusiéramos 0 quedaría un "0.00" que mentiría como medida.
  if (alwaysEditable) {
    return (
      <input
        type="number"
        step="0.01"
        defaultValue={field.valor ?? undefined}
        placeholder={field.valor == null ? MISSING : undefined}
        title={reconcileTip || "Valor reconciliado"}
        className="w-16 px-1.5 py-0.5 bg-s1 border border-b2 rounded text-[11px] text-t1 text-right font-mono hover:border-b1/60 focus:border-acc/50 outline-none"
        onChange={(e) => onEdit(parseFloat(e.target.value) || 0)}
      />
    );
  }

  // Modo "dbl-click to edit": read-only por default, input al doble-click
  if (dblClickEdit) {
    const commit = () => {
      const raw = inputRef.current?.value ?? "";
      const n = parseFloat(raw);
      if (Number.isFinite(n) && n > 0) {
        onEdit(n);
      }
      // valor inválido → revert silencioso (no pisa el original)
      setEditing(false);
    };
    const cancel = () => setEditing(false);

    if (editing) {
      return (
        <input
          ref={(el) => {
            inputRef.current = el;
            if (el) {
              el.focus();
              el.select();
            }
          }}
          type="number"
          step="0.01"
          defaultValue={field.valor ?? undefined}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(); }
            else if (e.key === "Escape") { e.preventDefault(); cancel(); }
          }}
          onBlur={commit}
          className="w-16 px-1.5 py-0.5 bg-s1 border border-acc/60 rounded text-[11px] text-t1 text-right font-mono outline-none"
        />
      );
    }

    const label = displayNum(field.valor);
    const title = reconcileTip
      ? `${reconcileTip} · Doble-click para editar`
      : "Doble-click para editar";
    return (
      <span
        onDoubleClick={(e) => {
          e.preventDefault();
          originalRef.current = safeNum(field.valor);
          setEditing(true);
        }}
        title={title}
        className="cursor-text underline decoration-dotted decoration-white/10 underline-offset-[3px] hover:decoration-white/30 transition-colors select-none"
      >
        {label}
      </span>
    );
  }

  // Default: plain read-only label
  return <>{displayNum(field.valor)}</>;
}

function EditableZocalo({
  z,
  onEdit,
  forceEditable = false,
}: {
  z: Zocalo;
  onEdit: (v: number) => void;
  forceEditable?: boolean;
}) {
  const editable = forceEditable || z.status === "CONFLICTO" || z.status === "DUDOSO";
  if (!editable) return <>{displayNum(z.ml)}</>;
  return (
    <input
      type="number"
      step="0.01"
      defaultValue={z.ml ?? undefined}
      className="w-16 px-1.5 py-0.5 bg-s1 border border-b2 rounded text-[11px] text-t1 text-right font-mono"
      onChange={(e) => onEdit(parseFloat(e.target.value) || 0)}
    />
  );
}

export default function DualReadResult({ data, quoteId, onConfirm, onRetry }: Props) {
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [editedData, setEditedData] = useState<DualReadData>(() => normalizeDualReadData(data));
  // Respuestas a pending_questions — se arman a medida que el operador
  // selecciona opciones. Confirmar se bloquea hasta que todas tengan valor.
  const [pendingAnswers, setPendingAnswers] = useState<Record<string, PendingAnswer>>({});
  const pendingQuestions = data.pending_questions || [];
  const allQuestionsAnswered = pendingQuestions.every(q => pendingAnswers[q.id]?.value);

  const handleRetry = async () => {
    setRetrying(true);
    setRetryError(null);
    try {
      const newData = (await apiDualReadRetry(quoteId)) as DualReadData;
      if (newData.opus_error) {
        // El backend nos devolvió la card previa + un flag de error.
        // No pisamos onRetry (no hay nueva lectura), mostramos el aviso.
        setRetryError(
          `Opus no respondió a tiempo (${newData.opus_error}). Corregí las medidas manualmente con doble-click en los valores.`
        );
      } else if (onRetry) {
        onRetry(newData);
      }
    } catch (e: unknown) {
      setRetryError(e instanceof Error ? e.message : "Error");
    } finally {
      setRetrying(false);
    }
  };

  const updateField = (sectorIdx: number, tramoIdx: number, field: string, val: number) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const tramo = next.sectores[sectorIdx].tramos[tramoIdx];
      if (field.startsWith("zocalo_")) {
        const zIdx = parseInt(field.split("_")[1]);
        tramo.zocalos[zIdx].ml = val;
      } else {
        tramo[field].valor = val;
        // Al editar largo o ancho, recalcular m² determinísticamente.
        // m² queda como valor derivado — no dejamos inconsistencia
        // largo×ancho≠m² pasar al confirm.
        if (field === "largo_m" || field === "ancho_m") {
          const largo = tramo.largo_m.valor || 0;
          const ancho = tramo.ancho_m.valor || 0;
          tramo.m2.valor = Math.round(largo * ancho * 100) / 100;
        }
      }
      return next;
    });
  };

  // PR #56 — remover un zócalo del despiece (click en la X del StatusIcon).
  // Útil cuando Dual Read sugiere 3 zócalos por nicho visible pero en realidad
  // uno de los lados no lleva (ej: lateral abierto).
  const removeZocalo = (sectorIdx: number, tramoIdx: number, zIdx: number) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.sectores[sectorIdx].tramos[tramoIdx].zocalos.splice(zIdx, 1);
      return next;
    });
  };

  // PR #68 — remover una mesada (tramo) completa del despiece. Útil cuando
  // el Dual Read duplicó tramos (Opus y Sonnet disagree) o detectó
  // elementos ajenos (heladera, bajo mesada) como piezas.
  const removeTramo = (sectorIdx: number, tramoIdx: number) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.sectores[sectorIdx].tramos.splice(tramoIdx, 1);
      // Si el sector queda vacío, removerlo también.
      if (next.sectores[sectorIdx].tramos.length === 0) {
        next.sectores.splice(sectorIdx, 1);
      }
      return next;
    });
  };

  // ─────────────────────────────────────────────────────────────────
  // PR #78 — Agregar piezas faltantes desde el card
  // Caso: el Dual Read olvidó un zócalo / tramo / sector. El operador
  // lo agrega inline sin tener que rebootear ni editar JSON crudo.
  // ─────────────────────────────────────────────────────────────────

  // Alto default para zócalos nuevos. Usa el alto de otro zócalo del
  // mismo card si existe, sino hardcode 0.05m (operador lo edita después).
  const defaultZocaloAlto = (): number => {
    for (const s of editedData.sectores) {
      for (const t of s.tramos) {
        for (const z of t.zocalos) {
          if (z.alto_m && z.alto_m > 0) return z.alto_m;
        }
      }
    }
    return 0.05;
  };

  const addZocalo = (sectorIdx: number, tramoIdx: number) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.sectores[sectorIdx].tramos[tramoIdx].zocalos.push({
        lado: "trasero",
        ml: 0,
        alto_m: defaultZocaloAlto(),
        status: "CONFIRMADO",
        opus_ml: null,
        sonnet_ml: null,
        _manual: true,
      });
      return next;
    });
  };

  const addTramo = (sectorIdx: number) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const tramosLen = next.sectores[sectorIdx].tramos.length;
      const newId = `manual_${tramosLen + 1}`;
      next.sectores[sectorIdx].tramos.push({
        id: newId,
        descripcion: `Tramo adicional ${tramosLen + 1}`,
        largo_m: { valor: 0, status: "CONFIRMADO", opus: null, sonnet: null },
        ancho_m: { valor: 0.6, status: "CONFIRMADO", opus: null, sonnet: null },
        m2: { valor: 0, status: "CONFIRMADO", opus: null, sonnet: null },
        zocalos: [],
        frentin: [],
        regrueso: [],
        _manual: true,
      });
      return next;
    });
  };

  const addSector = () => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const sectorsLen = next.sectores.length;
      const newId = `sector_manual_${sectorsLen + 1}`;
      next.sectores.push({
        id: newId,
        tipo: "cocina",
        tramos: [
          {
            id: `manual_1`,
            descripcion: "Mesada nueva",
            largo_m: { valor: 0, status: "CONFIRMADO", opus: null, sonnet: null },
            ancho_m: { valor: 0.6, status: "CONFIRMADO", opus: null, sonnet: null },
            m2: { valor: 0, status: "CONFIRMADO", opus: null, sonnet: null },
            zocalos: [],
            frentin: [],
            regrueso: [],
            _manual: true,
          },
        ],
        ambiguedades: [],
        _manual: true,
      });
      return next;
    });
  };

  // Edit descripcion inline (tramo y zócalo lado)
  const updateTramoDesc = (sectorIdx: number, tramoIdx: number, desc: string) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.sectores[sectorIdx].tramos[tramoIdx].descripcion = desc;
      return next;
    });
  };

  const updateZocaloLado = (sectorIdx: number, tramoIdx: number, zIdx: number, lado: string) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.sectores[sectorIdx].tramos[tramoIdx].zocalos[zIdx].lado = lado;
      return next;
    });
  };

  const updateZocaloAlto = (sectorIdx: number, tramoIdx: number, zIdx: number, alto: number) => {
    setEditedData((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      next.sectores[sectorIdx].tramos[tramoIdx].zocalos[zIdx].alto_m = alto;
      return next;
    });
  };

  // Totals
  let mesadasM2 = 0;
  let zocalosM2 = 0;
  let piecesCount = 0;
  let zocalosCount = 0;
  editedData.sectores.forEach((s) =>
    s.tramos.forEach((t) => {
      mesadasM2 += safeNum(t.m2?.valor);
      piecesCount += 1;
      t.zocalos.forEach((z) => {
        const ml = safeNum(z.ml);
        if (ml > 0) {
          zocalosM2 += ml * safeNum(z.alto_m);
          zocalosCount += 1;
        }
      });
    })
  );
  const totalM2 = mesadasM2 + zocalosM2;

  const allAmbiguedades = editedData.sectores.flatMap((s) => s.ambiguedades);
  const title =
    data.source === "DUAL" ? "Doble lectura del plano" : `Lectura ${data.source.replace("SOLO_", "")}`;
  const prettify = (s: string) =>
    s
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());

  // Markdown formatter para copy-to-clipboard. Genera una tabla estructurada
  // con piezas + zócalos + totales, lista para pegar en Claude Code.
  const despieceMarkdown = (() => {
    const lines: string[] = ["## Despiece", "", "| Pieza | Medida | m² |", "|---|---|---|"];
    let total = 0;
    editedData.sectores.forEach((sector) => {
      if (editedData.sectores.length > 1) {
        lines.push(`| **${prettify(sector.id)} — ${prettify(sector.tipo)}** |  |  |`);
      }
      sector.tramos.forEach((tramo) => {
        const desc = tramo.descripcion || tramo.id;
        // Display: "—" cuando falta medida. Math: safeNum (contribuye 0 al total).
        const largo = displayNum(tramo.largo_m?.valor);
        const ancho = displayNum(tramo.ancho_m?.valor);
        const m2 = safeNum(tramo.m2?.valor);
        total += m2;
        const m2Display = tramo.m2?.valor == null ? MISSING : m2.toFixed(2);
        lines.push(`| ${desc} | ${largo} × ${ancho} | ${m2Display} |`);
        tramo.zocalos.forEach((z) => {
          const ml = safeNum(z.ml);
          if (ml <= 0) return;
          const alto = safeNum(z.alto_m);
          const zm2 = ml * alto;
          total += zm2;
          const altoDisplay = z.alto_m == null ? MISSING : alto.toFixed(2);
          lines.push(`| Zóc. ${z.lado} | ${ml.toFixed(2)} ml × ${altoDisplay} | ${zm2.toFixed(2)} |`);
        });
      });
    });
    lines.push(`| **Total** | — | **${total.toFixed(2)}** |`);
    return lines.join("\n");
  })();
  const firstSectorHead = editedData.sectores[0]
    ? `${prettify(editedData.sectores[0].id)} — ${prettify(editedData.sectores[0].tipo)}`
    : "";

  return (
    <div className="my-2 w-full rounded-2xl border border-b1 bg-s1 overflow-hidden shadow-[0_20px_40px_-20px_rgba(0,0,0,0.5)]">
      {/* Header — eyebrow mono + título serif italic editorial */}
      <div className="flex items-center gap-4 px-6 py-5 border-b border-b1 bg-s2">
        <span className="text-[10px] font-mono font-semibold uppercase tracking-[0.12em] text-acc bg-acc-bg border border-acc/30 px-2.5 py-1 rounded-md shrink-0">
          {data.source === "DUAL"
            ? "Doble lectura"
            : data.source === "TEXT"
            ? "Desde texto"
            : data.source.replace("SOLO_", "Solo ")}
        </span>
        {/* PR #71 — badge de tipo de vista (planta / render 3D / etc) */}
        {(() => {
          const vt = data.view_type || "unknown";
          const meta = VIEW_TYPE_META[vt] || VIEW_TYPE_META.unknown;
          const tooltip = data.view_type_reason
            ? `${meta.label} — ${data.view_type_reason}`
            : meta.label;
          return (
            <span
              className={`text-[10px] font-semibold uppercase tracking-[0.1em] px-2 py-1 rounded-md border ${meta.cls}`}
              title={tooltip}
            >
              {meta.emoji} {meta.label}
            </span>
          );
        })()}
        <h3 className="font-serif italic text-[19px] font-medium text-t1 -tracking-[0.01em] leading-tight">{firstSectorHead || title}</h3>
        <span className="ml-auto text-[12px] text-t3 font-mono hidden md:inline tabular-nums">
          {piecesCount} {piecesCount === 1 ? "mesada" : "mesadas"} · {zocalosCount}{" "}
          {zocalosCount === 1 ? "zócalo" : "zócalos"}
        </span>
        <CopyButton
          text={despieceMarkdown}
          label="Copiar despiece"
          className="md:ml-3 ml-auto hidden sm:inline-flex"
        />
        <CopyButton
          text={despieceMarkdown}
          label="Copiar despiece"
          iconOnly
          className="ml-auto sm:hidden"
        />
      </div>

      {data.m2_warning && (
        <div className="mx-5 mt-4 text-[12px] text-amb bg-amb-bg rounded-lg px-3 py-2 border border-amb/25">
          {data.m2_warning}
        </div>
      )}

      {/* Body: pieces + totals */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px]">
        {/* Pieces */}
        <div className="py-2 overflow-x-auto">
          {/* Column headers */}
          <div className="grid grid-cols-[22px_1fr_80px_80px_80px] gap-3 px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-t3 bg-s2 border-b border-b1">
            <span></span>
            <span>Pieza</span>
            <span className="text-right">Largo</span>
            <span className="text-right">Ancho</span>
            <span className="text-right">m²</span>
          </div>

          {editedData.sectores.map((sector, si) => (
            <div key={sector.id}>
              {editedData.sectores.length > 1 && (
                <div className="px-5 pt-3.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-t3">
                  {sector.id} — {sector.tipo}
                </div>
              )}

              {sector.tramos.map((tramo, ti) => (
                <React.Fragment key={tramo.id}>
                  {/* Mesada row */}
                  <div className="grid grid-cols-[22px_1fr_80px_80px_80px] items-center gap-3 px-5 py-2.5 text-[13px] font-mono tabular-nums border-t border-b1">
                    <StatusIcon status={tramo.largo_m.status} />
                    <div className="font-sans">
                      {tramo._manual ? (
                        <input
                          type="text"
                          defaultValue={tramo.descripcion}
                          placeholder="Descripción (ej: Cajonera izq)"
                          className="w-full text-t1 bg-s1 border border-b2 rounded px-1.5 py-0.5 text-[13px] hover:border-b1/60 focus:border-acc/50 outline-none"
                          onChange={(e) => updateTramoDesc(si, ti, e.target.value)}
                        />
                      ) : (
                        <div className="text-t1">{tramo.descripcion || tramo.id}</div>
                      )}
                      <div className="text-[11px] text-t3 mt-0.5">mesada rectangular</div>
                    </div>
                    <div className="text-t2 text-right">
                      <EditableNumber
                        field={tramo.largo_m}
                        onEdit={(v) => updateField(si, ti, "largo_m", v)}
                        forceEditable={tramo._manual}
                        dblClickEdit
                      />
                      <span className="text-t4 ml-0.5">m</span>
                    </div>
                    <div className="text-t2 text-right">
                      <EditableNumber
                        field={tramo.ancho_m}
                        onEdit={(v) => updateField(si, ti, "ancho_m", v)}
                        forceEditable={tramo._manual}
                        dblClickEdit
                      />
                      <span className="text-t4 ml-0.5">m</span>
                    </div>
                    <div className="text-t1 font-medium text-right flex items-center justify-end gap-2">
                      {/* m² es valor derivado (largo × ancho). Read-only
                          salvo que el tramo sea _manual o el field esté en
                          CONFLICTO/DUDOSO — ahí EditableNumber cae en modo
                          "siempre input" por la rama alwaysEditable. */}
                      <EditableNumber
                        field={tramo.m2}
                        onEdit={(v) => updateField(si, ti, "m2", v)}
                        forceEditable={tramo._manual}
                      />
                      {/* PR #68 — botón × también en mesadas para remover duplicados
                          / piezas ajenas (heladera, bajo mesada) que el dual_read
                          detecta mal. */}
                      <button
                        type="button"
                        onClick={() => removeTramo(si, ti)}
                        title="Remover esta mesada"
                        aria-label="Remover esta mesada"
                        className="w-5 h-5 rounded-md grid place-items-center text-[11px] leading-none text-t4 hover:text-err hover:bg-[rgba(255,69,58,0.12)] border border-transparent hover:border-err/30 transition-colors cursor-pointer"
                      >
                        ×
                      </button>
                    </div>
                  </div>

                  {/* Zócalos rows — ocultar siempre los que tienen ml=0.
                      PR #77: antes se mostraban los CONFLICTO/DUDOSO con ml=0
                      (ruido visual sin valor — el operador no puede agregar
                      ml por input funcional y ml=0 no suma al cálculo). */}
                  {tramo.zocalos.map((z, zi) => {
                    const hasMl = (z.ml ?? 0) > 0;
                    // PR #78 — mostrar zócalos manuales recién agregados
                    // aunque ml=0 (el operador todavía no lo llenó).
                    const isManual = z._manual === true;
                    if (!hasMl && !isManual) return null;
                    return (
                      <div
                        key={zi}
                        className="group grid grid-cols-[22px_1fr_80px_80px_80px] items-center gap-3 px-5 py-2 text-[13px] font-mono tabular-nums border-t border-b1 relative"
                      >
                        <StatusIcon status={z.status} />
                        <div className="font-sans text-t2 pl-4 relative">
                          <span className="absolute left-0 top-1/2 w-2.5 h-px bg-b2" />
                          {isManual ? (
                            <input
                              type="text"
                              defaultValue={`Zóc. ${z.lado}`}
                              placeholder="Zóc. descripción"
                              className="w-full bg-s1 border border-b2 rounded px-1.5 py-0.5 text-[13px] hover:border-b1/60 focus:border-acc/50 outline-none"
                              onChange={(e) => {
                                // Si escribió algo distinto a "Zóc. ", lo guardamos como lado (custom).
                                const v = e.target.value.replace(/^Z[óo]c\.\s*/i, "").trim();
                                updateZocaloLado(si, ti, zi, v || "trasero");
                              }}
                            />
                          ) : (
                            <>Zóc. {z.lado}</>
                          )}
                        </div>
                        <div className="text-t2 text-right">
                          <EditableZocalo
                            z={z}
                            onEdit={(v) => updateField(si, ti, `zocalo_${zi}`, v)}
                            forceEditable={isManual}
                          />
                          <span className="text-t4 ml-0.5">ml</span>
                        </div>
                        <div className="text-t2 text-right">
                          {isManual ? (
                            <input
                              type="number"
                              step="0.01"
                              defaultValue={z.alto_m ?? undefined}
                              className="w-16 px-1.5 py-0.5 bg-s1 border border-b2 rounded text-[11px] text-t1 text-right font-mono"
                              onChange={(e) => updateZocaloAlto(si, ti, zi, parseFloat(e.target.value) || 0)}
                            />
                          ) : (
                            <>{displayNum(z.alto_m)}</>
                          )}
                          <span className="text-t4 ml-0.5">m</span>
                        </div>
                        <div className="text-t1 font-medium text-right flex items-center justify-end gap-2">
                          <span>{(z.ml == null || z.alto_m == null) ? MISSING : (z.ml * z.alto_m).toFixed(2)}</span>
                          {/* PR #61 — botón remover siempre disponible, independiente
                              del status (el operador confirma con el cliente si lleva
                              zócalos o no; Dual Read solo sugiere). Hover aumenta
                              contraste para descubribilidad. */}
                          <button
                            type="button"
                            onClick={() => removeZocalo(si, ti, zi)}
                            title="Remover este zócalo"
                            aria-label="Remover este zócalo"
                            className="w-5 h-5 rounded-md grid place-items-center text-[11px] leading-none text-t4 hover:text-err hover:bg-[rgba(255,69,58,0.12)] border border-transparent hover:border-err/30 transition-colors cursor-pointer"
                          >
                            ×
                          </button>
                        </div>
                      </div>
                    );
                  })}

                  {/* PR #78 — botón "+ Zócalo" al final de cada tramo */}
                  <div className="px-5 py-1.5 border-t border-b1/50">
                    <button
                      type="button"
                      onClick={() => addZocalo(si, ti)}
                      className="text-[11px] text-t3 hover:text-acc pl-7 transition-colors cursor-pointer"
                    >
                      + Agregar zócalo
                    </button>
                  </div>
                </React.Fragment>
              ))}

              {/* PR #78 — botón "+ Mesada" al final de cada sector */}
              <div className="px-5 py-2 border-t border-b1/50">
                <button
                  type="button"
                  onClick={() => addTramo(si)}
                  className="text-[12px] text-t3 hover:text-acc transition-colors cursor-pointer"
                >
                  + Agregar mesada
                </button>
              </div>
            </div>
          ))}

          {/* PR #78 — botón "+ Sector" al final del card */}
          <div className="px-5 py-2 border-t border-b1">
            <button
              type="button"
              onClick={addSector}
              className="text-[12px] text-t3 hover:text-acc transition-colors cursor-pointer"
            >
              + Agregar sector (isla, baño, lavadero)
            </button>
          </div>
        </div>

        {/* Totals */}
        <div className="border-t lg:border-t-0 lg:border-l border-b1 bg-gradient-to-b from-s2 to-s1 p-5">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-t3">Total a cortar</div>
          <div className="mt-1.5 text-[44px] leading-none font-semibold tracking-[-1px] font-mono tabular-nums text-t1">
            {totalM2.toFixed(2)}
            <span className="text-[16px] text-t2 font-medium ml-1 tracking-tight font-sans">m²</span>
          </div>
          <div className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-[12px] font-mono tabular-nums">
            <span className="text-t3 font-sans">
              Mesadas <span className="text-t4">({piecesCount})</span>
            </span>
            <span className="text-t1 text-right">{mesadasM2.toFixed(2)} m²</span>
            <span className="text-t3 font-sans">
              Zócalos <span className="text-t4">({zocalosCount})</span>
            </span>
            <span className="text-t1 text-right">{zocalosM2.toFixed(2)} m²</span>
          </div>
        </div>
      </div>

      {/* Alerts categorizadas */}
      {allAmbiguedades.length > 0 && (() => {
        const norm = allAmbiguedades.map((a) =>
          typeof a === "string" ? { tipo: "REVISION" as AmbiguedadTipo, texto: a } : a
        );
        const groups: Record<AmbiguedadTipo, string[]> = { REVISION: [], INFO: [], DEFAULT: [] };
        norm.forEach((a) => {
          const t = (a.tipo || "REVISION") as AmbiguedadTipo;
          (groups[t] || groups.REVISION).push(a.texto);
        });
        const META: Record<AmbiguedadTipo, { label: string; color: string; bg: string; border: string; dot: string }> = {
          REVISION: { label: "Revisar en plano",   color: "text-amb", bg: "bg-amb-bg",                      border: "border-amb/25",                      dot: "bg-amb" },
          INFO:     { label: "Falta dato",         color: "text-acc", bg: "bg-acc-bg",                      border: "border-acc/25",                      dot: "bg-acc" },
          DEFAULT:  { label: "Valores por default", color: "text-t2", bg: "bg-[rgba(255,255,255,0.03)]",    border: "border-b1",                          dot: "bg-t3" },
        };
        const order: AmbiguedadTipo[] = ["REVISION", "INFO", "DEFAULT"];
        return (
          <div className="mx-5 mb-4 flex flex-col gap-2">
            {order.map((t) =>
              groups[t].length === 0 ? null : (
                <div key={t} className={`p-3.5 ${META[t].bg} border ${META[t].border} rounded-xl`}>
                  <h4 className={`text-[11px] font-semibold uppercase tracking-[0.06em] ${META[t].color} mb-2`}>
                    {META[t].label}
                  </h4>
                  <ul className="flex flex-col gap-1.5">
                    {groups[t].map((text, i) => (
                      <li key={i} className="text-t2 text-[12px] leading-[1.5] pl-3.5 relative">
                        <span className={`absolute left-0 top-[9px] w-1 h-1 rounded-full ${META[t].dot}`} />
                        {text}
                      </li>
                    ))}
                  </ul>
                </div>
              )
            )}
          </div>
        );
      })()}

      {/* PR #355 — Candidatas sugeridas para revisión. Aparece solo si
          algún tramo tiene `suggested_candidates` no vacío (el backend
          controla el trigger). El click copia el valor al input del
          largo SIN confirmar — el tramo queda DUDOSO hasta confirmación
          humana explícita. */}
      <SuggestedCandidates
        tramos={editedData.sectores.flatMap<TramoWithSuggestions>(
          (s, sectorIdx) =>
            s.tramos
              .map((t, tramoIdx) => {
                const cands = t.suggested_candidates || [];
                if (cands.length === 0) return null;
                return {
                  sectorIdx,
                  tramoIdx,
                  regionId: t.id,
                  tramoDescripcion: t.descripcion,
                  candidates: cands,
                } satisfies TramoWithSuggestions;
              })
              .filter((x): x is TramoWithSuggestions => x !== null),
        )}
        onUseAsLargo={(sectorIdx, tramoIdx, valor) => {
          // Reusa updateField existente — copia el valor + recalcula m².
          // NO confirma: el status del tramo queda como estaba (DUDOSO
          // mientras los suspicious_reasons existan). El operador tiene
          // que confirmar con "Confirmar medidas" después de verificar.
          updateField(sectorIdx, tramoIdx, "largo_m", valor);
        }}
      />

      {/* Retry if needed */}
      {data.source !== "DUAL" && !data._retry && (
        <div className="px-5 pb-3">
          <button
            className="w-full py-2.5 rounded-lg text-[12px] font-medium bg-orange-600/20 hover:bg-orange-600/30 border border-orange-600/40 text-orange-200 transition disabled:opacity-50"
            onClick={handleRetry}
            disabled={retrying}
          >
            {retrying ? "Consultando a Opus..." : "⚠️ Las medidas no coinciden — verificar con Opus"}
          </button>
          {retryError && <div className="text-[11px] text-err mt-1">{retryError}</div>}
        </div>
      )}

      {/* Pending questions — Valentina no asume: si falta info, pregunta.
          Confirmar queda bloqueado hasta que el operador elija opción para
          cada pregunta (o marque "no" explícito). */}
      {pendingQuestions.length > 0 && (
        <div className="mx-5 mb-4 p-4 rounded-xl border border-amb/30 bg-amb-bg">
          <h4 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-amb mb-3">
            Antes de confirmar — {pendingQuestions.length} pregunta{pendingQuestions.length > 1 ? "s" : ""} pendiente{pendingQuestions.length > 1 ? "s" : ""}
          </h4>
          <div className="flex flex-col gap-4">
            {pendingQuestions.map((q) => {
              const current = pendingAnswers[q.id];
              return (
                <div key={q.id} className="flex flex-col gap-2">
                  <div className="text-[13px] text-t1 leading-[1.5]">{q.question}</div>
                  <div className="flex flex-col gap-1.5">
                    {q.options?.map((opt) => (
                      <label
                        key={opt.value}
                        className={`flex items-start gap-2 text-[12px] cursor-pointer px-2.5 py-1.5 rounded-md border transition ${
                          current?.value === opt.value
                            ? "border-acc bg-acc/10 text-t1"
                            : "border-b1 bg-transparent text-t2 hover:border-b2"
                        }`}
                      >
                        <input
                          type="radio"
                          name={`q-${q.id}`}
                          checked={current?.value === opt.value}
                          onChange={() => setPendingAnswers(prev => ({
                            ...prev,
                            [q.id]: { id: q.id, value: opt.value, detail: current?.detail },
                          }))}
                          className="mt-0.5"
                        />
                        <span>{opt.label}</span>
                      </label>
                    ))}
                    {current?.value === "custom" && q.detail_placeholder && (
                      <input
                        type="text"
                        placeholder={q.detail_placeholder}
                        value={current?.detail || ""}
                        onChange={(e) => setPendingAnswers(prev => ({
                          ...prev,
                          [q.id]: { ...(prev[q.id] || { id: q.id, value: "custom" }), detail: e.target.value },
                        }))}
                        className="mt-1 w-full px-2.5 py-1.5 bg-s1 border border-b2 rounded-md text-[12px] text-t1 focus:border-acc/50 outline-none"
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 px-5 py-4 border-t border-b1 bg-s2">
        <button
          className="flex-1 py-2.5 px-4 rounded-xl text-[13px] font-semibold bg-acc hover:bg-acc-hover text-white transition disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-acc"
          onClick={() => {
            const payload = {
              ...editedData,
              pending_answers: Object.values(pendingAnswers),
            };
            onConfirm(payload as DualReadData);
          }}
          disabled={!allQuestionsAnswered}
          title={!allQuestionsAnswered ? "Respondé las preguntas pendientes primero" : undefined}
        >
          {allQuestionsAnswered
            ? `Confirmar medidas · ${totalM2.toFixed(2)} m²`
            : `Respondé ${pendingQuestions.length - Object.values(pendingAnswers).filter(a => a.value).length} pregunta(s) pendiente(s)`}
        </button>
      </div>
    </div>
  );
}
