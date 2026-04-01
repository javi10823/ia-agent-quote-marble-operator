"use client";

import { useState } from "react";

export default function FilterPreview() {
  const [option, setOption] = useState<1 | 2 | 3>(1);

  return (
    <div style={{ background: "var(--bg)", color: "var(--t1)", minHeight: "100vh", padding: 40 }}>
      <h1 style={{ fontSize: 22, marginBottom: 20 }}>Elegí una opción de filtro</h1>
      <div style={{ display: "flex", gap: 10, marginBottom: 30 }}>
        {[1, 2, 3].map(n => (
          <button key={n} onClick={() => setOption(n as 1|2|3)} style={{
            padding: "10px 20px", borderRadius: 8, fontSize: 14, fontWeight: 500,
            border: option === n ? "2px solid var(--acc)" : "1px solid var(--b2)",
            background: option === n ? "var(--acc2)" : "transparent",
            color: option === n ? "var(--acc)" : "var(--t2)",
            cursor: "pointer", fontFamily: "inherit",
          }}>
            Opción {n}
          </button>
        ))}
      </div>

      {option === 1 && <Option1 />}
      {option === 2 && <Option2 />}
      {option === 3 && <Option3 />}
    </div>
  );
}

/* ── OPCIÓN 1: Barra arriba de la tabla ─────────────────────────────────── */
function Option1() {
  const [active, setActive] = useState("todos");
  return (
    <div>
      <p style={{ fontSize: 12, color: "var(--t3)", marginBottom: 15 }}>
        Opción 1: Barra de filtros + búsqueda arriba de la tabla. Compacto, siempre visible.
      </p>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px", background: "var(--s2)", borderRadius: "10px 10px 0 0",
        border: "1px solid var(--b1)", borderBottom: "none",
      }}>
        {/* Chips de estado */}
        <div style={{ display: "flex", gap: 6 }}>
          {[
            { key: "todos", label: "Todos", count: 12 },
            { key: "draft", label: "Borrador", count: 5 },
            { key: "validated", label: "Validado", count: 4 },
            { key: "sent", label: "Enviado", count: 3 },
          ].map(f => (
            <button key={f.key} onClick={() => setActive(f.key)} style={{
              padding: "5px 12px", borderRadius: 6, fontSize: 12, fontWeight: 500,
              border: active === f.key ? "1px solid var(--acc3)" : "1px solid var(--b1)",
              background: active === f.key ? "var(--acc2)" : "transparent",
              color: active === f.key ? "var(--acc)" : "var(--t3)",
              cursor: "pointer", fontFamily: "inherit",
              display: "flex", alignItems: "center", gap: 6,
            }}>
              {f.label}
              <span style={{
                fontSize: 10, padding: "1px 6px", borderRadius: 99,
                background: active === f.key ? "rgba(79,143,255,.2)" : "rgba(255,255,255,.06)",
              }}>{f.count}</span>
            </button>
          ))}
        </div>

        {/* Búsqueda */}
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 12px", borderRadius: 8,
          border: "1px solid var(--b1)", background: "var(--s3)",
          width: 240,
        }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--t3)", flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input placeholder="Buscar cliente, material..." style={{
            background: "transparent", border: "none", outline: "none",
            color: "var(--t1)", fontSize: 12, fontFamily: "inherit", width: "100%",
          }} />
        </div>
      </div>

      {/* Fake table */}
      <FakeTable />
    </div>
  );
}

/* ── OPCIÓN 2: Filtros en los KPIs (clickeables) ────────────────────────── */
function Option2() {
  const [active, setActive] = useState("todos");
  return (
    <div>
      <p style={{ fontSize: 12, color: "var(--t3)", marginBottom: 15 }}>
        Opción 2: Los KPIs son filtros clickeables + búsqueda en el header. Los KPIs ya existen, solo se hacen interactivos.
      </p>

      {/* Search in header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 16,
      }}>
        <div style={{ fontSize: 18, fontWeight: 500 }}>Presupuestos</div>
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "7px 14px", borderRadius: 8,
          border: "1px solid var(--b2)", background: "var(--s3)", width: 280,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--t3)" }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input placeholder="Buscar por cliente o material..." style={{
            background: "transparent", border: "none", outline: "none",
            color: "var(--t1)", fontSize: 13, fontFamily: "inherit", width: "100%",
          }} />
        </div>
      </div>

      {/* KPIs as filters */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(4,1fr)",
        gap: 1, marginBottom: 20,
        background: "var(--b1)", borderRadius: 10, overflow: "hidden",
      }}>
        {[
          { key: "todos", label: "Total", value: 12, sub: "presupuestos", main: true },
          { key: "draft", label: "Borradores", value: 5, sub: "en proceso" },
          { key: "validated", label: "Validados", value: 4, sub: "listos" },
          { key: "sent", label: "Enviados", value: 3, sub: "este mes" },
        ].map(k => (
          <button key={k.key} onClick={() => setActive(k.key)} style={{
            background: active === k.key ? "var(--s3)" : "var(--s2)",
            padding: "18px 20px", border: "none", cursor: "pointer",
            borderLeft: active === k.key ? "2px solid var(--acc)" : "2px solid transparent",
            textAlign: "left", fontFamily: "inherit",
            transition: "all .15s",
          }}>
            <div style={{ fontSize: 10, fontWeight: 500, color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.09em", marginBottom: 10 }}>{k.label}</div>
            <div style={{
              fontSize: k.main ? 34 : 26, fontWeight: 300, letterSpacing: "-0.04em",
              color: active === k.key ? "var(--acc)" : "var(--t1)", lineHeight: 1,
            }}>{k.value}</div>
            <div style={{ fontSize: 11, color: "var(--t3)", marginTop: 5 }}>{k.sub}</div>
          </button>
        ))}
      </div>

      <FakeTable />
    </div>
  );
}

/* ── OPCIÓN 3: Tabs + búsqueda integrada ─────────────────────────────────── */
function Option3() {
  const [active, setActive] = useState("todos");
  return (
    <div>
      <p style={{ fontSize: 12, color: "var(--t3)", marginBottom: 15 }}>
        Opción 3: Tabs debajo del header con contador + búsqueda inline. Estilo minimalista.
      </p>

      <div style={{ fontSize: 18, fontWeight: 500, marginBottom: 16 }}>Presupuestos</div>

      {/* Tabs + search row */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        borderBottom: "1px solid var(--b1)", marginBottom: 16,
      }}>
        <div style={{ display: "flex", gap: 0 }}>
          {[
            { key: "todos", label: "Todos", count: 12 },
            { key: "draft", label: "Borrador", count: 5 },
            { key: "validated", label: "Validado", count: 4 },
            { key: "sent", label: "Enviado", count: 3 },
          ].map(f => (
            <button key={f.key} onClick={() => setActive(f.key)} style={{
              padding: "10px 18px", fontSize: 13, fontWeight: 500,
              border: "none", borderBottom: active === f.key ? "2px solid var(--acc)" : "2px solid transparent",
              background: "transparent",
              color: active === f.key ? "var(--acc)" : "var(--t3)",
              cursor: "pointer", fontFamily: "inherit",
              display: "flex", alignItems: "center", gap: 6,
            }}>
              {f.label}
              <span style={{
                fontSize: 10, padding: "2px 7px", borderRadius: 99,
                background: active === f.key ? "var(--acc2)" : "rgba(255,255,255,.06)",
                color: active === f.key ? "var(--acc)" : "var(--t3)",
              }}>{f.count}</span>
            </button>
          ))}
        </div>

        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 12px", borderRadius: 8,
          border: "1px solid var(--b1)", background: "var(--s3)", width: 240,
          marginBottom: 8,
        }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--t3)" }}>
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input placeholder="Buscar..." style={{
            background: "transparent", border: "none", outline: "none",
            color: "var(--t1)", fontSize: 12, fontFamily: "inherit", width: "100%",
          }} />
        </div>
      </div>

      <FakeTable />
    </div>
  );
}

/* ── Tabla fake para preview ─────────────────────────────────────────────── */
function FakeTable() {
  const rows = [
    { client: "Consumidor Final", material: "SILESTONE BLANCO NORTE", ars: "$384.668", usd: "USD 1937", status: "validated" },
    { client: "Juan Carlos", material: "PURASTONE BLANCO PALOMA", ars: "$238.420", usd: "USD 816", status: "sent" },
    { client: "María López", material: "NEGRO BRASIL", ars: "$180.000", usd: "", status: "draft" },
    { client: "Arq. Nadia", material: "DEKTON SIRIUS", ars: "$520.300", usd: "USD 3200", status: "validated" },
  ];

  const badge: Record<string, { bg: string; color: string; label: string }> = {
    draft: { bg: "var(--amb2)", color: "var(--amb)", label: "Borrador" },
    validated: { bg: "var(--grn2)", color: "var(--grn)", label: "Validado" },
    sent: { bg: "var(--acc2)", color: "var(--acc)", label: "Enviado" },
  };

  return (
    <div style={{ background: "var(--s1)", border: "1px solid var(--b1)", borderRadius: "0 0 10px 10px", overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead style={{ background: "var(--s2)" }}>
          <tr>
            {["Cliente", "Material", "Importe", "Estado"].map(h => (
              <th key={h} style={{ textAlign: "left", padding: "10px 18px", fontSize: 10, fontWeight: 500, color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.09em" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,.045)" }}>
              <td style={{ padding: "13px 18px", fontSize: 13, fontWeight: 500 }}>{r.client}</td>
              <td style={{ padding: "13px 18px", fontSize: 12, color: "var(--t2)" }}>{r.material}</td>
              <td style={{ padding: "13px 18px" }}>
                <div style={{ fontSize: 13 }}>{r.ars}</div>
                {r.usd && <div style={{ fontSize: 11, color: "var(--t3)" }}>{r.usd}</div>}
              </td>
              <td style={{ padding: "13px 18px" }}>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 5,
                  padding: "3px 9px", borderRadius: 999, fontSize: 11, fontWeight: 500,
                  background: badge[r.status].bg, color: badge[r.status].color,
                }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: "currentColor" }} />
                  {badge[r.status].label}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
