import { EditorView } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import { COLORS } from "@/lib/design-tokens";

// Helper: convertir hex + opacity a rgba inline (evitamos sumar otra
// utility). Si después pasamos a `color-mix()` reemplazamos este helper.
function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

export const catalogEditorTheme = EditorView.theme(
  {
    "&": {
      backgroundColor: COLORS.bg,
      color: COLORS.t2,
      fontFamily: "var(--font-mono), ui-monospace, monospace",
      fontSize: "13px",
      lineHeight: "1.7",
    },
    ".cm-content": {
      caretColor: COLORS.acc,
      padding: "16px 0",
    },
    ".cm-cursor, .cm-dropCursor": {
      borderLeftColor: COLORS.acc,
      borderLeftWidth: "2px",
    },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": {
      backgroundColor: `${withAlpha(COLORS.acc, 0.18)} !important`,
    },
    ".cm-activeLine": {
      backgroundColor: "rgba(232,237,229,0.025)",
    },
    ".cm-gutters": {
      backgroundColor: COLORS.s1,
      color: COLORS.t4,
      border: "none",
      borderRight: `1px solid ${COLORS.b1}`,
      paddingRight: "4px",
    },
    ".cm-activeLineGutter": {
      backgroundColor: "rgba(232,237,229,0.03)",
      color: COLORS.t2,
    },
    ".cm-lineNumbers .cm-gutterElement": {
      padding: "0 8px 0 16px",
      minWidth: "40px",
      fontSize: "11px",
    },
    ".cm-foldGutter .cm-gutterElement": {
      padding: "0 4px",
      color: COLORS.t4,
      cursor: "pointer",
      transition: "color 0.1s",
    },
    ".cm-foldGutter .cm-gutterElement:hover": {
      color: COLORS.t2,
    },
    "&.cm-focused .cm-matchingBracket": {
      backgroundColor: withAlpha(COLORS.acc, 0.25),
      outline: `1px solid ${withAlpha(COLORS.acc, 0.35)}`,
    },
    ".cm-searchMatch": {
      backgroundColor: withAlpha(COLORS.amb, 0.25),
      outline: `1px solid ${withAlpha(COLORS.amb, 0.4)}`,
    },
    ".cm-searchMatch.cm-searchMatch-selected": {
      backgroundColor: withAlpha(COLORS.acc, 0.30),
      outline: `1px solid ${withAlpha(COLORS.acc, 0.5)}`,
    },
    ".cm-panels": {
      backgroundColor: COLORS.s1,
      color: COLORS.t2,
      borderBottom: `1px solid ${COLORS.b1}`,
    },
    ".cm-panels.cm-panels-top": {
      borderBottom: `1px solid ${COLORS.b1}`,
    },
    ".cm-panel.cm-search": {
      padding: "8px 12px",
      backgroundColor: COLORS.s1,
    },
    ".cm-panel.cm-search input, .cm-panel.cm-search button": {
      fontFamily: "var(--font-sans), -apple-system, sans-serif",
      fontSize: "12px",
    },
    ".cm-panel.cm-search input": {
      backgroundColor: "rgba(0,0,0,0.3)",
      border: `1px solid ${COLORS.b2}`,
      borderRadius: "6px",
      color: COLORS.t1,
      padding: "4px 8px",
      outline: "none",
    },
    ".cm-panel.cm-search input:focus": {
      borderColor: COLORS.acc,
    },
    ".cm-panel.cm-search button": {
      backgroundColor: "transparent",
      border: `1px solid ${COLORS.b2}`,
      borderRadius: "6px",
      color: COLORS.t2,
      padding: "4px 10px",
      cursor: "pointer",
    },
    ".cm-panel.cm-search button:hover": {
      backgroundColor: "rgba(232,237,229,0.05)",
      color: COLORS.t1,
    },
    ".cm-panel.cm-search label": {
      color: COLORS.t3,
      fontSize: "11px",
    },
    ".cm-tooltip": {
      backgroundColor: COLORS.s3,
      border: `1px solid ${COLORS.b2}`,
      borderRadius: "6px",
      boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
    },
    ".cm-tooltip .cm-tooltip-arrow::before": {
      borderTopColor: "transparent",
      borderBottomColor: "transparent",
    },
    ".cm-lintRange-error": {
      backgroundImage: "none",
      textDecoration: `wavy underline ${COLORS.red}`,
      textDecorationSkipInk: "none",
    },
    ".cm-lintRange-warning": {
      backgroundImage: "none",
      textDecoration: `wavy underline ${COLORS.amb}`,
      textDecorationSkipInk: "none",
    },
    ".cm-diagnostic-error": {
      borderLeftColor: COLORS.red,
    },
    ".cm-diagnostic-warning": {
      borderLeftColor: COLORS.amb,
    },
    ".cm-foldPlaceholder": {
      backgroundColor: withAlpha(COLORS.acc, 0.10),
      border: `1px solid ${withAlpha(COLORS.acc, 0.20)}`,
      borderRadius: "3px",
      color: withAlpha(COLORS.acc, 0.60),
      padding: "0 6px",
      margin: "0 4px",
    },
  },
  { dark: true }
);

const catalogHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: COLORS.t1 },
  { tag: tags.string, color: COLORS.grn },
  { tag: tags.number, color: COLORS.amb },
  { tag: tags.bool, color: COLORS.amb },
  { tag: tags.null, color: COLORS.t3 },
  { tag: tags.keyword, color: COLORS.amb },
  { tag: tags.punctuation, color: COLORS.t3 },
  { tag: tags.brace, color: COLORS.t3 },
  { tag: tags.squareBracket, color: COLORS.t3 },
  { tag: tags.separator, color: COLORS.t3 },
]);

export const catalogHighlighting = syntaxHighlighting(catalogHighlightStyle);
