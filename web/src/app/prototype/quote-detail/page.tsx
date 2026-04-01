"use client";

import { useState } from "react";

// ── MOCK DATA ───────────────────────────────────────────────────────────────

const MOCK_QUOTE = {
  id: "5dd15936-5b60-45ba-aa9b-74738480fba7",
  ref: "Q-035",
  client_name: "Consumidor Final",
  project: "Cocina",
  material: "SILESTONE BLANCO NORTE",
  status: "validated" as const,
  source: "operator" as const,
  created_at: "2026-04-01T14:30:00Z",
  updated_at: "2026-04-01T15:45:00Z",
  plazo: "30 días desde la toma de medidas",
  total_ars: 384708,
  total_usd: 1937,
  pdf_url: "/files/xxx/Consumidor Final - SILESTONE BLANCO NORTE - 01.04.2026.pdf",
  excel_url: "/files/xxx/Consumidor Final - SILESTONE BLANCO NORTE - 01.04.2026.xlsx",
  drive_url: "https://docs.google.com/spreadsheets/d/1xxx/edit",
};

const MOCK_REQUEST = {
  client: "Consumidor Final",
  tipo_trabajo: "Mesada de cocina",
  material: "Silestone Blanco Norte E 20mm",
  localidad: "Rosario",
  colocacion: true,
  pileta: "Empotrada — la trae el cliente",
  anafe: true,
  zocalo: "Trasero, 15cm de alto",
  frentin: false,
  plazo: "30 días",
  notas: "2 tramos de mesada con bacha y anafe",
};

const MOCK_PIECES = [
  { desc: "Mesada tramo 1", medida: "2,507 × 0,60", m2: 1.504, nota: "c/anafe" },
  { desc: "Mesada tramo 2", medida: "2,470 × 0,60", m2: 1.482, nota: "c/bacha" },
  { desc: "Zócalo trasero", medida: "4,977ml × 0,15", m2: 0.747, nota: "" },
];

const MOCK_MO = [
  { desc: "Agujero y pegado pileta", qty: 1, price: 65147, total: 65147 },
  { desc: "Agujero anafe", qty: 1, price: 43097, total: 43097 },
  { desc: "Colocación", qty: 3.73, price: 60135, total: 224304 },
  { desc: "Flete + toma medidas Rosario", qty: 1, price: 52000, total: 52000 },
  { desc: "Agujero toma corriente", qty: 1, price: 7818, total: 7818 },
];

const MOCK_MESSAGES = [
  { role: "user", content: "Mesada Silestone blanco E 20mm Tramo 2507x600mm c/corte anafe Tramo 2470x600mm c/corte Bacha. Tramo zócalo trasero altura 150mm. Silestone blanco norte con colocación en Rosario. Tengo bacha. Cliente: Consumidor final" },
  { role: "assistant", content: "Tengo los datos del enunciado. Busco los precios en catálogo.\n\n**Material encontrado:** Silestone Blanco Norte — USD 519/m² sin IVA → **USD 628/m² con IVA**\n\nAntes de generar la validación, necesito confirmar:\n\n¿Cuántos días de demora?" },
  { role: "user", content: "30 días" },
  { role: "assistant", content: "## Validación — Consumidor Final / Cocina\n\n**Fecha:** 01/04/2026 | **Demora:** 30 días | **Rosario**\n\n### MATERIAL — 3,733 m²\n\n| Pieza | Medida | m² |\n|---|---|---|\n| Mesada tramo 1 | 2,507 × 0,60 | 1,504 |\n| Mesada tramo 2 | 2,470 × 0,60 | 1,482 |\n| Zócalo trasero | 4,977ml × 0,15 | 0,747 |\n| **TOTAL** | | **3,733 m²** |\n\n### MERMA — NO APLICA\nDesperdicio: 0,47 m² (< 1,0 m²) → sin sobrante\n\n### MANO DE OBRA\n\n| Ítem | Cant | Precio | Total |\n|---|---|---|---|\n| Pegado pileta | 1 | $65.147 | $65.147 |\n| Anafe | 1 | $43.097 | $43.097 |\n| Colocación | 3,73 | $60.135 | $224.304 |\n| Flete Rosario | 1 | $52.000 | $52.000 |\n| Toma corriente | 1 | $7.818 | $7.818 |\n| **TOTAL MO** | | | **$392.366** |\n\n### DESCUENTOS — NO APLICA\n\n---\n\n**GRAND TOTAL:** $392.366 mano de obra + USD 1.937 material\n\n¿Confirmás para generar PDF y Excel?" },
  { role: "user", content: "dale" },
  { role: "assistant", content: "✅ **Presupuestos generados y subidos a Drive**\n\n- [Descargar PDF](/files/xxx/file.pdf)\n- [Descargar Excel](/files/xxx/file.xlsx)\n- [Abrir en Drive](https://drive.google.com/...)\n\n**Total:** $392.366 + USD 1.937" },
];

// ── HELPERS ──────────────────────────────────────────────────────────────────

const fmtARS = (n: number) => {
  const formatted = Math.round(n).toLocaleString("es-AR");
  return `$${formatted}`;
};
const fmtUSD = (n: number) => `USD ${Math.round(n).toLocaleString("es-AR")}`;
const fmtQty = (n: number) => n === Math.floor(n) ? String(n) : n.toFixed(2).replace(".", ",");

const STATUS: Record<string, { label: string; bg: string; color: string }> = {
  draft: { label: "Borrador", bg: "var(--amb2)", color: "var(--amb)" },
  validated: { label: "Validado", bg: "var(--grn2)", color: "var(--grn)" },
  sent: { label: "Enviado", bg: "var(--acc2)", color: "var(--acc)" },
};

// ── MAIN COMPONENT ──────────────────────────────────────────────────────────

export default function QuoteDetailPrototype() {
  const [tab, setTab] = useState<"detail" | "chat">("detail");
  const q = MOCK_QUOTE;
  const st = STATUS[q.status];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "var(--bg)" }}>
      {/* ── HEADER ─────────────────────────────────────────────────── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 28px", borderBottom: "1px solid var(--b1)",
        flexShrink: 0, background: "var(--s1)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <button style={backBtnStyle}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>
          </button>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 16, fontWeight: 600, color: "var(--t1)" }}>{q.client_name}</span>
              <span style={{ ...badgeStyle, background: st.bg, color: st.color }}>● {st.label}</span>
              {q.source === "web" && <span style={{ ...badgeStyle, background: "rgba(138,43,226,.15)", color: "#a855f7" }}>WEB</span>}
            </div>
            <div style={{ fontSize: 12, color: "var(--t3)", marginTop: 2 }}>
              {q.project} · {q.material} · {q.ref}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          {q.pdf_url && <FileBtn label="PDF" color="#ff6b63" />}
          {q.excel_url && <FileBtn label="Excel" color="var(--grn)" />}
          {q.drive_url && <FileBtn label="Drive" color="var(--acc)" />}
        </div>
      </div>

      {/* ── TABS ───────────────────────────────────────────────────── */}
      <div style={{
        display: "flex", gap: 0, borderBottom: "1px solid var(--b1)",
        background: "var(--s1)", paddingLeft: 28,
      }}>
        <TabBtn active={tab === "detail"} onClick={() => setTab("detail")}>Detalle</TabBtn>
        <TabBtn active={tab === "chat"} onClick={() => setTab("chat")}>Chat</TabBtn>
      </div>

      {/* ── CONTENT ────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>
        {tab === "detail" ? <DetailTab /> : <ChatTab />}
      </div>
    </div>
  );
}

// ── DETAIL TAB ──────────────────────────────────────────────────────────────

function DetailTab() {
  const q = MOCK_QUOTE;
  const totalMO = MOCK_MO.reduce((s, m) => s + m.total, 0);
  const totalM2 = MOCK_PIECES.reduce((s, p) => s + p.m2, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* A. METADATA SUMMARY */}
      <Section title="Resumen">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 16 }}>
          <MetaItem label="Cliente" value={q.client_name} />
          <MetaItem label="Proyecto" value={q.project} />
          <MetaItem label="Material" value={q.material} />
          <MetaItem label="Fecha" value={new Date(q.created_at).toLocaleDateString("es-AR")} />
          <MetaItem label="Demora" value={q.plazo} />
          <MetaItem label="Origen" value={q.source === "web" ? "Web (chatbot)" : "Operador"} />
          <MetaItem label="Total ARS" value={fmtARS(q.total_ars)} highlight />
          <MetaItem label="Total USD" value={fmtUSD(q.total_usd)} highlight />
        </div>
      </Section>

      {/* B. PARSED REQUEST */}
      <Section title="Solicitud">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <ReqField label="Tipo de trabajo" value={MOCK_REQUEST.tipo_trabajo} />
          <ReqField label="Material" value={MOCK_REQUEST.material} />
          <ReqField label="Localidad" value={MOCK_REQUEST.localidad} />
          <ReqField label="Colocación" value={MOCK_REQUEST.colocacion ? "Sí" : "No"} />
          <ReqField label="Pileta" value={MOCK_REQUEST.pileta} />
          <ReqField label="Anafe" value={MOCK_REQUEST.anafe ? "Sí" : "No"} />
          <ReqField label="Zócalo" value={MOCK_REQUEST.zocalo} />
          <ReqField label="Frentín" value={MOCK_REQUEST.frentin ? "Sí" : "No"} />
          <ReqField label="Plazo" value={MOCK_REQUEST.plazo} />
          <ReqField label="Notas" value={MOCK_REQUEST.notas} />
        </div>
      </Section>

      {/* C. QUOTE BREAKDOWN */}
      <Section title="Desglose del Presupuesto">

        {/* Material table */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--t1)", marginBottom: 8 }}>
            Material — {fmtQty(totalM2)} m²
          </div>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Pieza</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Medida</th>
                <th style={{ ...thStyle, textAlign: "right" }}>m²</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Nota</th>
              </tr>
            </thead>
            <tbody>
              {MOCK_PIECES.map((p, i) => (
                <tr key={i} style={{ background: i % 2 === 1 ? "rgba(255,255,255,.03)" : "transparent" }}>
                  <td style={tdStyle}>{p.desc}</td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>{p.medida}</td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>{fmtQty(p.m2)}</td>
                  <td style={{ ...tdStyle, textAlign: "right", color: "var(--t3)" }}>{p.nota}</td>
                </tr>
              ))}
              <tr style={{ background: "rgba(255,255,255,.05)" }}>
                <td style={{ ...tdStyle, fontWeight: 600 }}>TOTAL</td>
                <td style={tdStyle}></td>
                <td style={{ ...tdStyle, textAlign: "right", fontWeight: 600 }}>{fmtQty(totalM2)} m²</td>
                <td style={tdStyle}></td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Merma */}
        <InfoBar icon="📐" label="Merma" status="NO APLICA" detail="Desperdicio: 0,47 m² (< 1,0 m²) → sin sobrante" />

        {/* MO table */}
        <div style={{ marginTop: 16, marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--t1)", marginBottom: 8 }}>
            Mano de Obra
          </div>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Ítem</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Cant</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Precio</th>
                <th style={{ ...thStyle, textAlign: "right" }}>Total</th>
              </tr>
            </thead>
            <tbody>
              {MOCK_MO.map((m, i) => (
                <tr key={i} style={{ background: i % 2 === 1 ? "rgba(255,255,255,.03)" : "transparent" }}>
                  <td style={tdStyle}>{m.desc}</td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>{fmtQty(m.qty)}</td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>{fmtARS(m.price)}</td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>{fmtARS(m.total)}</td>
                </tr>
              ))}
              <tr style={{ background: "rgba(255,255,255,.05)" }}>
                <td style={{ ...tdStyle, fontWeight: 600 }}>TOTAL MO</td>
                <td style={tdStyle}></td>
                <td style={tdStyle}></td>
                <td style={{ ...tdStyle, textAlign: "right", fontWeight: 600 }}>{fmtARS(totalMO)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Descuentos */}
        <InfoBar icon="🏷️" label="Descuentos" status="NO APLICA" detail="Particular sin umbral de m²" />

        {/* Grand total */}
        <div style={{
          marginTop: 20, padding: "16px 20px", borderRadius: 10,
          background: "var(--s3)", border: "1px solid var(--b2)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--t1)" }}>PRESUPUESTO TOTAL</span>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: "var(--t1)" }}>
              {fmtARS(MOCK_QUOTE.total_ars)} <span style={{ color: "var(--t3)", fontWeight: 400, fontSize: 13 }}>mano de obra</span>
            </div>
            <div style={{ fontSize: 15, fontWeight: 600, color: "var(--acc)", marginTop: 2 }}>
              + {fmtUSD(MOCK_QUOTE.total_usd)} <span style={{ color: "var(--t3)", fontWeight: 400, fontSize: 13 }}>material</span>
            </div>
          </div>
        </div>
      </Section>

      {/* D. QUICK CHAT */}
      <Section title="Modificaciones">
        <div style={{ fontSize: 12, color: "var(--t3)", marginBottom: 10 }}>
          Escribí un cambio y Valentina regenera los documentos automáticamente.
        </div>
        <div style={{
          display: "flex", gap: 8, alignItems: "center",
          background: "var(--s3)", border: "1px solid var(--b2)",
          borderRadius: 10, padding: "10px 14px",
        }}>
          <input
            placeholder="Ej: cambiá el nombre del cliente a María López..."
            style={{
              flex: 1, background: "transparent", border: "none", outline: "none",
              color: "var(--t1)", fontSize: 13, fontFamily: "inherit",
            }}
          />
          <button style={{
            width: 32, height: 32, borderRadius: "50%",
            background: "var(--acc)", border: "none", color: "#fff",
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
        <button onClick={() => {}} style={{
          marginTop: 8, background: "none", border: "none", color: "var(--acc)",
          fontSize: 12, cursor: "pointer", fontFamily: "inherit", padding: 0,
        }}>
          Ver historial completo →
        </button>
      </Section>
    </div>
  );
}

// ── CHAT TAB ────────────────────────────────────────────────────────────────

function ChatTab() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {MOCK_MESSAGES.map((msg, i) => (
        <div key={i} style={{
          display: "flex", gap: 10,
          flexDirection: msg.role === "user" ? "row-reverse" : "row",
          alignItems: "flex-start",
        }}>
          <div style={{
            width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 10, fontWeight: 600,
            background: msg.role === "assistant" ? "var(--acc)" : "var(--s3)",
            color: msg.role === "assistant" ? "#fff" : "var(--t2)",
            border: msg.role === "user" ? "1px solid var(--b2)" : "none",
          }}>
            {msg.role === "assistant" ? "V" : "OP"}
          </div>
          <div style={{
            maxWidth: "70%", padding: "10px 14px",
            background: msg.role === "user" ? "var(--acc2)" : "var(--s2)",
            border: `1px solid ${msg.role === "user" ? "var(--acc3)" : "var(--b1)"}`,
            borderRadius: msg.role === "user" ? "12px 2px 12px 12px" : "2px 12px 12px 12px",
            fontSize: 13, lineHeight: 1.6, color: "var(--t2)",
            whiteSpace: "pre-wrap",
          }}>
            {msg.content}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── SUB-COMPONENTS ──────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: "var(--s1)", border: "1px solid var(--b1)",
      borderRadius: 12, padding: "18px 22px",
    }}>
      <div style={{
        fontSize: 13, fontWeight: 600, color: "var(--t1)",
        textTransform: "uppercase", letterSpacing: "0.06em",
        marginBottom: 14, paddingBottom: 8, borderBottom: "1px solid var(--b1)",
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function MetaItem({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: highlight ? 600 : 400, color: highlight ? "var(--t1)" : "var(--t2)" }}>{value}</div>
    </div>
  );
}

function ReqField({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", gap: 8, fontSize: 13 }}>
      <span style={{ color: "var(--t3)", minWidth: 110, flexShrink: 0 }}>{label}</span>
      <span style={{ color: "var(--t1)" }}>{value}</span>
    </div>
  );
}

function InfoBar({ icon, label, status, detail }: { icon: string; label: string; status: string; detail: string }) {
  const isNo = status.includes("NO");
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "10px 14px", borderRadius: 8,
      background: isNo ? "rgba(255,255,255,.02)" : "rgba(245,166,35,.06)",
      border: `1px solid ${isNo ? "var(--b1)" : "rgba(245,166,35,.16)"}`,
      fontSize: 12,
    }}>
      <span>{icon}</span>
      <span style={{ fontWeight: 600, color: "var(--t1)" }}>{label} — {status}</span>
      <span style={{ color: "var(--t3)" }}>{detail}</span>
    </div>
  );
}

function TabBtn({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      padding: "10px 20px", fontSize: 13, fontWeight: 500,
      border: "none", borderBottom: active ? "2px solid var(--acc)" : "2px solid transparent",
      background: "transparent",
      color: active ? "var(--acc)" : "var(--t3)",
      cursor: "pointer", fontFamily: "inherit",
    }}>
      {children}
    </button>
  );
}

function FileBtn({ label, color }: { label: string; color: string }) {
  const emoji = label === "PDF" ? "📄" : label === "Excel" ? "📊" : "☁";
  return (
    <a style={{
      display: "flex", alignItems: "center", gap: 5,
      padding: "6px 12px", borderRadius: 6,
      fontSize: 11, fontWeight: 500, textDecoration: "none",
      border: `1px solid ${color}33`, background: "transparent", color,
    }}>
      {emoji} {label}
    </a>
  );
}

// ── STYLES ───────────────────────────────────────────────────────────────────

const backBtnStyle: React.CSSProperties = {
  width: 30, height: 30, borderRadius: 6,
  border: "1px solid var(--b1)", background: "transparent",
  color: "var(--t2)", cursor: "pointer",
  display: "flex", alignItems: "center", justifyContent: "center",
};

const badgeStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 4,
  padding: "2px 8px", borderRadius: 999,
  fontSize: 10, fontWeight: 600,
};

const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse",
  border: "1px solid var(--b1)", borderRadius: 8, overflow: "hidden",
};

const thStyle: React.CSSProperties = {
  padding: "8px 12px", fontSize: 11, fontWeight: 600,
  color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.05em",
  background: "rgba(255,255,255,.03)", borderBottom: "1px solid var(--b1)",
  textAlign: "left",
};

const tdStyle: React.CSSProperties = {
  padding: "9px 12px", fontSize: 13, color: "var(--t2)",
  borderBottom: "1px solid rgba(255,255,255,.04)",
};
