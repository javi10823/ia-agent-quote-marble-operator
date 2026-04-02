"use client";

import { useCallback, useMemo, useRef } from "react";
import CodeMirror, { type ReactCodeMirrorRef } from "@uiw/react-codemirror";
import { json, jsonParseLinter } from "@codemirror/lang-json";
import { linter } from "@codemirror/lint";
import { search } from "@codemirror/search";
import { bracketMatching, foldGutter } from "@codemirror/language";
import { highlightActiveLine, lineNumbers, EditorView } from "@codemirror/view";
import { catalogEditorTheme, catalogHighlighting } from "./catalog-theme";

interface Props {
  value: string;
  onChange: (value: string) => void;
  loading: boolean;
  loadError: string | null;
  onRetry: () => void;
}

export default function CatalogEditor({ value, onChange, loading, loadError, onRetry }: Props) {
  const editorRef = useRef<ReactCodeMirrorRef>(null);

  const extensions = useMemo(
    () => [
      json(),
      linter(jsonParseLinter()),
      foldGutter(),
      bracketMatching(),
      highlightActiveLine(),
      lineNumbers(),
      search(),
      catalogHighlighting,
      EditorView.lineWrapping,
    ],
    []
  );

  const handleChange = useCallback(
    (val: string) => {
      onChange(val);
    },
    [onChange]
  );

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-5 h-5 border-2 border-acc/30 border-t-acc rounded-full animate-spin" />
          <span className="text-xs text-t3">Cargando catalogo...</span>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="text-red text-sm font-medium">{loadError}</div>
          <button
            onClick={onRetry}
            className="px-3 py-1.5 rounded-md text-xs font-medium border border-b1 bg-transparent text-t2 cursor-pointer hover:border-b2 hover:text-t1 transition font-sans"
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-hidden">
      <CodeMirror
        ref={editorRef}
        value={value}
        onChange={handleChange}
        theme={catalogEditorTheme}
        extensions={extensions}
        basicSetup={false}
        height="100%"
        style={{ height: "100%", overflow: "auto" }}
      />
    </div>
  );
}
