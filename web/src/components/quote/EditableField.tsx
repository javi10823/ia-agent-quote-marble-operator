"use client";

import { useEffect, useRef, useState } from "react";

type FieldType = "text" | "textarea" | "select" | "toggle";

interface BaseProps {
  label: string;
  type: FieldType;
  disabled?: boolean;
  highlight?: boolean;
  placeholder?: string;
}

interface TextProps extends BaseProps {
  type: "text" | "textarea";
  value: string | null | undefined;
  onSave: (next: string) => Promise<void>;
  options?: never;
}

interface SelectProps extends BaseProps {
  type: "select";
  value: string | null | undefined;
  onSave: (next: string) => Promise<void>;
  options: Array<{ value: string; label: string }>;
}

interface ToggleProps extends BaseProps {
  type: "toggle";
  value: boolean | null | undefined;
  onSave: (next: boolean) => Promise<void>;
  options?: never;
}

type Props = TextProps | SelectProps | ToggleProps;

const LABEL_STYLE: React.CSSProperties = {
  fontSize: 10,
  color: "var(--t3)",
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  marginBottom: 3,
  display: "flex",
  alignItems: "center",
  gap: 6,
};
const VALUE_STYLE: React.CSSProperties = {
  fontSize: 14,
  color: "var(--t2)",
  minHeight: 20,
  lineHeight: 1.4,
};
const EMPTY_STYLE: React.CSSProperties = { ...VALUE_STYLE, color: "var(--t3)", fontStyle: "italic" };
const INPUT_STYLE: React.CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  fontSize: 14,
  fontFamily: "inherit",
  background: "var(--s2)",
  color: "var(--t1)",
  border: "1px solid var(--acc)",
  borderRadius: 6,
  outline: "none",
};
const BTN: React.CSSProperties = {
  padding: "4px 10px",
  fontSize: 11,
  fontWeight: 500,
  borderRadius: 6,
  border: "1px solid var(--b2)",
  background: "transparent",
  color: "var(--t2)",
  cursor: "pointer",
  fontFamily: "inherit",
};
const BTN_PRIMARY: React.CSSProperties = {
  ...BTN,
  background: "var(--acc)",
  borderColor: "var(--acc)",
  color: "#fff",
};

export default function EditableField(props: Props) {
  const { label, type, disabled, highlight, placeholder } = props;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(() => stringifyValue(props));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState(false);
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null>(null);

  useEffect(() => {
    if (!editing) setDraft(stringifyValue(props));
  }, [props, editing]);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      if ("select" in inputRef.current) (inputRef.current as HTMLInputElement).select?.();
    }
  }, [editing]);

  const startEdit = () => {
    if (disabled || saving) return;
    setError(null);
    setDraft(stringifyValue(props));
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    setError(null);
    setDraft(stringifyValue(props));
  };

  const commit = async (rawNext: string | boolean) => {
    setSaving(true);
    setError(null);
    try {
      if (type === "toggle") {
        await (props as ToggleProps).onSave(Boolean(rawNext));
      } else {
        await (props as TextProps | SelectProps).onSave(String(rawNext));
      }
      setEditing(false);
    } catch (e: any) {
      setError(e?.message || "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  };

  // ── TOGGLE: no edit mode, instant save ────────────────────────────────────
  if (type === "toggle") {
    const checked = Boolean((props as ToggleProps).value);
    return (
      <div>
        <div style={LABEL_STYLE}>{label}</div>
        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            cursor: disabled || saving ? "not-allowed" : "pointer",
            opacity: disabled || saving ? 0.6 : 1,
          }}
        >
          <span
            style={{
              width: 32, height: 18, borderRadius: 9,
              background: checked ? "var(--acc)" : "var(--b2)",
              position: "relative", transition: "background 0.15s",
              flexShrink: 0,
            }}
          >
            <span
              style={{
                position: "absolute", top: 2, left: checked ? 16 : 2,
                width: 14, height: 14, borderRadius: "50%",
                background: "#fff", transition: "left 0.15s",
              }}
            />
          </span>
          <input
            type="checkbox"
            checked={checked}
            disabled={disabled || saving}
            onChange={(e) => commit(e.target.checked)}
            style={{ position: "absolute", opacity: 0, pointerEvents: "none" }}
          />
          <span style={{ fontSize: 13, color: "var(--t2)" }}>{checked ? "Sí" : "No"}</span>
          {saving && <Spinner />}
        </label>
        {error && <ErrorLine message={error} />}
      </div>
    );
  }

  // ── TEXT / TEXTAREA / SELECT: click-to-edit ───────────────────────────────
  const rawValue = stringifyValue(props);
  const hasValue = rawValue.trim().length > 0;

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div style={LABEL_STYLE}>
        <span>{label}</span>
        {!editing && hover && !disabled && (
          <button
            type="button"
            onClick={startEdit}
            aria-label={`Editar ${label}`}
            style={{
              background: "transparent", border: "none", padding: 0,
              color: "var(--acc)", cursor: "pointer", fontSize: 11, lineHeight: 1,
            }}
          >
            ✏
          </button>
        )}
      </div>

      {editing ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {type === "textarea" ? (
            <textarea
              ref={(el) => { inputRef.current = el; }}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") cancel();
                // Ctrl/Cmd+Enter to save in textarea
                if ((e.ctrlKey || e.metaKey) && e.key === "Enter") commit(draft);
              }}
              placeholder={placeholder}
              rows={3}
              disabled={saving}
              style={{ ...INPUT_STYLE, resize: "vertical", minHeight: 60 }}
            />
          ) : type === "select" ? (
            <select
              ref={(el) => { inputRef.current = el; }}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Escape") cancel(); }}
              disabled={saving}
              style={INPUT_STYLE}
            >
              {(props as SelectProps).options.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          ) : (
            <input
              ref={(el) => { inputRef.current = el; }}
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") cancel();
                if (e.key === "Enter") commit(draft);
              }}
              placeholder={placeholder}
              disabled={saving}
              style={INPUT_STYLE}
            />
          )}
          <div style={{ display: "flex", gap: 6 }}>
            <button
              type="button"
              onClick={() => commit(draft)}
              disabled={saving || draft === stringifyValue(props)}
              style={{ ...BTN_PRIMARY, opacity: saving || draft === stringifyValue(props) ? 0.5 : 1 }}
            >
              {saving ? "Guardando..." : "Guardar"}
            </button>
            <button type="button" onClick={cancel} disabled={saving} style={BTN}>
              Cancelar
            </button>
          </div>
          {error && <ErrorLine message={error} />}
        </div>
      ) : (
        <div
          onClick={startEdit}
          title={disabled ? undefined : "Clic para editar"}
          style={{
            ...(hasValue ? VALUE_STYLE : EMPTY_STYLE),
            fontWeight: highlight ? 600 : 400,
            color: highlight && hasValue ? "var(--t1)" : hasValue ? "var(--t2)" : "var(--t3)",
            cursor: disabled ? "default" : "text",
            whiteSpace: type === "textarea" ? "pre-wrap" : undefined,
          }}
        >
          {hasValue ? rawValue : (placeholder || "—")}
        </div>
      )}
    </div>
  );
}

function stringifyValue(props: Props): string {
  if (props.type === "toggle") return props.value ? "true" : "false";
  const v = props.value;
  if (v == null) return "";
  return String(v);
}

function Spinner() {
  return (
    <span
      style={{
        width: 10, height: 10, borderRadius: "50%",
        border: "2px solid var(--b2)", borderTopColor: "var(--acc)",
        animation: "spin 0.8s linear infinite", display: "inline-block",
      }}
    />
  );
}

function ErrorLine({ message }: { message: string }) {
  return <div style={{ fontSize: 11, color: "var(--red, #f87171)", marginTop: 4 }}>{message}</div>;
}
