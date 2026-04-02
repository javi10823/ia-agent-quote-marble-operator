import { EditorView } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";

export const catalogEditorTheme = EditorView.theme(
  {
    "&": {
      backgroundColor: "#0a0a14",
      color: "rgba(255,255,255,0.58)",
      fontFamily: "'Geist Mono', monospace",
      fontSize: "13px",
      lineHeight: "1.7",
    },
    ".cm-content": {
      caretColor: "#4f8fff",
      padding: "16px 0",
    },
    ".cm-cursor, .cm-dropCursor": {
      borderLeftColor: "#4f8fff",
      borderLeftWidth: "2px",
    },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": {
      backgroundColor: "rgba(79,143,255,0.15) !important",
    },
    ".cm-activeLine": {
      backgroundColor: "rgba(255,255,255,0.025)",
    },
    ".cm-gutters": {
      backgroundColor: "#07070e",
      color: "rgba(255,255,255,0.14)",
      border: "none",
      borderRight: "1px solid rgba(255,255,255,0.05)",
      paddingRight: "4px",
    },
    ".cm-activeLineGutter": {
      backgroundColor: "rgba(255,255,255,0.03)",
      color: "rgba(255,255,255,0.40)",
    },
    ".cm-lineNumbers .cm-gutterElement": {
      padding: "0 8px 0 16px",
      minWidth: "40px",
      fontSize: "11px",
    },
    ".cm-foldGutter .cm-gutterElement": {
      padding: "0 4px",
      color: "rgba(255,255,255,0.14)",
      cursor: "pointer",
      transition: "color 0.1s",
    },
    ".cm-foldGutter .cm-gutterElement:hover": {
      color: "rgba(255,255,255,0.5)",
    },
    "&.cm-focused .cm-matchingBracket": {
      backgroundColor: "rgba(79,143,255,0.25)",
      outline: "1px solid rgba(79,143,255,0.35)",
    },
    ".cm-searchMatch": {
      backgroundColor: "rgba(245,166,35,0.25)",
      outline: "1px solid rgba(245,166,35,0.4)",
    },
    ".cm-searchMatch.cm-searchMatch-selected": {
      backgroundColor: "rgba(79,143,255,0.30)",
      outline: "1px solid rgba(79,143,255,0.5)",
    },
    ".cm-panels": {
      backgroundColor: "#0c0c16",
      color: "rgba(255,255,255,0.58)",
      borderBottom: "1px solid rgba(255,255,255,0.07)",
    },
    ".cm-panels.cm-panels-top": {
      borderBottom: "1px solid rgba(255,255,255,0.07)",
    },
    ".cm-panel.cm-search": {
      padding: "8px 12px",
      backgroundColor: "#0c0c16",
    },
    ".cm-panel.cm-search input, .cm-panel.cm-search button": {
      fontFamily: "'Geist', sans-serif",
      fontSize: "12px",
    },
    ".cm-panel.cm-search input": {
      backgroundColor: "rgba(0,0,0,0.3)",
      border: "1px solid rgba(255,255,255,0.10)",
      borderRadius: "6px",
      color: "rgba(255,255,255,0.90)",
      padding: "4px 8px",
      outline: "none",
    },
    ".cm-panel.cm-search input:focus": {
      borderColor: "#4f8fff",
    },
    ".cm-panel.cm-search button": {
      backgroundColor: "transparent",
      border: "1px solid rgba(255,255,255,0.10)",
      borderRadius: "6px",
      color: "rgba(255,255,255,0.58)",
      padding: "4px 10px",
      cursor: "pointer",
    },
    ".cm-panel.cm-search button:hover": {
      backgroundColor: "rgba(255,255,255,0.05)",
      color: "rgba(255,255,255,0.80)",
    },
    ".cm-panel.cm-search label": {
      color: "rgba(255,255,255,0.40)",
      fontSize: "11px",
    },
    ".cm-tooltip": {
      backgroundColor: "#15151f",
      border: "1px solid rgba(255,255,255,0.10)",
      borderRadius: "6px",
      boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
    },
    ".cm-tooltip .cm-tooltip-arrow::before": {
      borderTopColor: "transparent",
      borderBottomColor: "transparent",
    },
    ".cm-lintRange-error": {
      backgroundImage: "none",
      textDecoration: "wavy underline #ff453a",
      textDecorationSkipInk: "none",
    },
    ".cm-lintRange-warning": {
      backgroundImage: "none",
      textDecoration: "wavy underline #f5a623",
      textDecorationSkipInk: "none",
    },
    ".cm-diagnostic-error": {
      borderLeftColor: "#ff453a",
    },
    ".cm-diagnostic-warning": {
      borderLeftColor: "#f5a623",
    },
    ".cm-foldPlaceholder": {
      backgroundColor: "rgba(79,143,255,0.10)",
      border: "1px solid rgba(79,143,255,0.20)",
      borderRadius: "3px",
      color: "rgba(79,143,255,0.60)",
      padding: "0 6px",
      margin: "0 4px",
    },
  },
  { dark: true }
);

const catalogHighlightStyle = HighlightStyle.define([
  { tag: tags.propertyName, color: "rgba(255,255,255,0.90)" },
  { tag: tags.string, color: "#30d158" },
  { tag: tags.number, color: "#f5a623" },
  { tag: tags.bool, color: "#f5a623" },
  { tag: tags.null, color: "rgba(255,255,255,0.28)" },
  { tag: tags.keyword, color: "#f5a623" },
  { tag: tags.punctuation, color: "rgba(255,255,255,0.30)" },
  { tag: tags.brace, color: "rgba(255,255,255,0.35)" },
  { tag: tags.squareBracket, color: "rgba(255,255,255,0.35)" },
  { tag: tags.separator, color: "rgba(255,255,255,0.25)" },
]);

export const catalogHighlighting = syntaxHighlighting(catalogHighlightStyle);
