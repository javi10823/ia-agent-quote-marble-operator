import Section from "./Section";

interface SourceFile {
  filename: string;
  type?: string;
  size?: number;
  url: string;
}

interface Props {
  files: SourceFile[];
}

export default function SourceFilesSection({ files }: Props) {
  if (files.length === 0) return null;

  const fmtSize = (b: number) =>
    b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`;

  const fmtType = (t?: string) => {
    if (!t) return "Archivo";
    if (t.includes("pdf")) return "PDF";
    if (t.includes("jpeg") || t.includes("jpg")) return "JPG";
    if (t.includes("png")) return "PNG";
    return "Archivo";
  };

  return (
    <Section title="Archivos Fuente">
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {files.map((f, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 12,
            padding: "12px 16px", borderRadius: 8,
            background: i % 2 === 0 ? "rgba(255,255,255,.02)" : "transparent",
            border: "1px solid var(--b1)",
          }}>
            <span style={{ fontSize: 20, flexShrink: 0 }}>
              {f.type?.includes("pdf") ? "📄" : f.type?.includes("image") ? "🖼️" : "📎"}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: "var(--t1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {f.filename}
              </div>
              <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 2 }}>
                {fmtType(f.type)}
                {f.size ? ` · ${fmtSize(f.size)}` : ""}
              </div>
            </div>
            <a href={f.url} download style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "6px 14px", borderRadius: 6,
              fontSize: 11, fontWeight: 500, textDecoration: "none",
              border: "1px solid var(--acc3)", background: "transparent",
              color: "var(--acc)", cursor: "pointer", flexShrink: 0,
            }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Descargar
            </a>
          </div>
        ))}
      </div>
    </Section>
  );
}
