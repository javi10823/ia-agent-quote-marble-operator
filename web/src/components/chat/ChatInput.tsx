import { useState } from "react";
import IconBtn from "@/components/ui/IconBtn";
import { A, I, DOT, DASH } from "@/lib/chars";

const VALID_TYPES = ["application/pdf", "image/jpeg", "image/jpg", "image/png", "image/webp"];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const MAX_FILES = 5;

export interface ChatInputProps {
  input: string;
  setInput: (v: string) => void;
  files: File[];
  setFiles: (f: File[]) => void;
  dragActive: boolean;
  setDragActive: (v: boolean) => void;
  dragCounterRef: React.MutableRefObject<number>;
  sending: boolean;
  send: () => void;
  onKey: (e: React.KeyboardEvent) => void;
  fileRef: React.RefObject<HTMLInputElement>;
}

export default function ChatInput({ input, setInput, files, setFiles, dragActive, setDragActive, dragCounterRef, sending, send, onKey, fileRef }: ChatInputProps) {
  const [fileError, setFileError] = useState<string | null>(null);

  const addFiles = (newFiles: FileList | File[]) => {
    const arr = Array.from(newFiles);
    const valid: File[] = [];
    for (const f of arr) {
      if (!VALID_TYPES.some(t => f.type.includes(t.split("/")[1]))) {
        setFileError(`"${f.name}" — tipo no soportado`);
        setTimeout(() => setFileError(null), 3000);
        continue;
      }
      if (f.size > MAX_FILE_SIZE) {
        setFileError(`"${f.name}" ${DASH} m${A}ximo 10MB`);
        setTimeout(() => setFileError(null), 3000);
        continue;
      }
      if (files.length + valid.length >= MAX_FILES) {
        setFileError(`M${A}ximo 5 archivos`);
        setTimeout(() => setFileError(null), 3000);
        break;
      }
      if (files.some(ef => ef.name === f.name && ef.size === f.size)) continue;
      if (valid.some(ef => ef.name === f.name && ef.size === f.size)) continue;
      valid.push(f);
    }
    if (valid.length > 0) setFiles([...files, ...valid]);
  };

  const removeFile = (idx: number) => setFiles(files.filter((_, i) => i !== idx));

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current++;
    setDragActive(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current--;
    if (dragCounterRef.current <= 0) { dragCounterRef.current = 0; setDragActive(false); }
  };
  const handleDragOver = (e: React.DragEvent) => e.preventDefault();
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current = 0;
    setDragActive(false);
    if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files);
  };

  const fmtSize = (b: number) => b < 1024 ? `${b} B` : b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(1)} MB`;
  const fmtType = (t: string) => t.includes("pdf") ? "PDF" : t.includes("jpeg") || t.includes("jpg") ? "JPG" : t.includes("png") ? "PNG" : "WEBP";
  const fileIcon = (t: string) => t.includes("pdf") ? "📄" : "🖼️";

  return (
    <div
      onDragEnter={handleDragEnter} onDragLeave={handleDragLeave}
      onDragOver={handleDragOver} onDrop={handleDrop}
      style={{ position: "relative" }}
    >
      {/* Drag overlay */}
      {dragActive && (
        <div style={{
          position: "absolute", inset: 0, zIndex: 10,
          background: "rgba(79,143,255,0.08)", border: "2px dashed var(--acc)",
          borderRadius: 12, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", gap: 6,
          pointerEvents: "none",
        }}>
          <span style={{ fontSize: 28 }}>📁</span>
          <span style={{ fontSize: 14, fontWeight: 500, color: "var(--acc)" }}>{`Solt${A} tu plano PDF o imagen ac${A}`}</span>
          <span style={{ fontSize: 11, color: "var(--t3)" }}>{`PDF, JPG, PNG ${DOT} M${A}ximo 10MB`}</span>
        </div>
      )}

      {/* File chips */}
      {(files.length > 0 || fileError) && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
          {files.map((f, i) => (
            <div key={`${f.name}-${i}`} style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "5px 10px", borderRadius: 6,
              background: "var(--s3)", border: "1px solid var(--b1)",
              fontSize: 11, color: "var(--t2)", maxWidth: 280,
            }}>
              <span style={{ fontSize: 14 }}>{fileIcon(f.type)}</span>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{f.name}</span>
              <span style={{ color: "var(--t3)", flexShrink: 0 }}>{fmtType(f.type)} {DOT} {fmtSize(f.size)}</span>
              <button onClick={() => removeFile(i)} style={{ background: "none", border: "none", color: "var(--t3)", cursor: "pointer", fontSize: 13, padding: "0 2px" }}>✕</button>
            </div>
          ))}
          {fileError && (
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "5px 10px", borderRadius: 6,
              background: "rgba(255,69,58,0.08)", border: "1px solid rgba(255,69,58,0.3)",
              fontSize: 11, color: "var(--red)",
            }}>
              ⚠️ {fileError}
            </div>
          )}
        </div>
      )}

      {/* Input row */}
      <div style={{
        display: "flex", alignItems: "flex-end", gap: 8,
        background: "var(--s3)",
        border: dragActive ? "1px solid var(--acc)" : "1px solid var(--b2)",
        boxShadow: dragActive ? "0 0 20px rgba(79,143,255,0.15)" : "none",
        borderRadius: 12, padding: "10px 10px 10px 16px",
        transition: "border-color 0.15s, box-shadow 0.15s",
      }}>
        <textarea value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={onKey} rows={1} disabled={sending} autoFocus
          placeholder={`Escrib${I} el enunciado o arrastr${A} el plano ac${A}...`}
          style={{
            flex: 1, background: "transparent", border: "none", outline: "none",
            fontFamily: "inherit", fontSize: 13, color: "var(--t1)",
            resize: "none", lineHeight: 1.5, maxHeight: 110,
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 5, flexShrink: 0 }}>
          <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" multiple style={{ display: "none" }}
            onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
          />
          <IconBtn onClick={() => fileRef.current?.click()} title="Adjuntar plano">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
            </svg>
          </IconBtn>
          <IconBtn onClick={send} primary disabled={sending || (!input.trim() && files.length === 0)}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </IconBtn>
        </div>
      </div>
    </div>
  );
}
