/**
 * `<details class="datos-pdf">` plegable · form 5 inputs.
 * UI editable SIN persist (decisión Javi #4 · persist Sprint 4).
 */
"use client";

import { useState } from "react";
import type { DatosPdfDefaults } from "@/lib/api";

interface Props {
  defaults: DatosPdfDefaults;
}

export function DatosPdfDetails({ defaults }: Props) {
  const [form, setForm] = useState<DatosPdfDefaults>(defaults);
  const update = <K extends keyof DatosPdfDefaults>(key: K, v: DatosPdfDefaults[K]) =>
    setForm((p) => ({ ...p, [key]: v }));

  return (
    <details className="datos-pdf" data-testid="datos-pdf">
      <summary>
        <span className="dp-tag">PDF</span>
        <span className="dp-ttl">Datos para el documento del cliente</span>
        <span className="dp-meta">plazo · anticipo · saldo · envío · notas</span>
        <span className="dp-chev" aria-hidden="true">
          ▾
        </span>
      </summary>
      <div className="dp-body">
        <div className="dp-row">
          <label className="dp-lbl">Plazo</label>
          <input
            className="dp-inp"
            type="text"
            value={form.plazo}
            onChange={(e) => update("plazo", e.target.value)}
            data-testid="dp-plazo"
          />
        </div>
        <div className="dp-row">
          <label className="dp-lbl">Anticipo</label>
          <div className="dp-inline">
            <input
              className="dp-inp-sm"
              type="text"
              value={form.anticipoPct}
              onChange={(e) => update("anticipoPct", e.target.value)}
              data-testid="dp-anticipo"
            />
            <span className="dp-unit">%</span>
          </div>
        </div>
        <div className="dp-row">
          <label className="dp-lbl">Saldo</label>
          <input
            className="dp-inp"
            type="text"
            value={form.saldo}
            onChange={(e) => update("saldo", e.target.value)}
            data-testid="dp-saldo"
          />
        </div>
        <div className="dp-row">
          <label className="dp-lbl">Datos envío</label>
          <input
            className="dp-inp"
            type="text"
            value={form.envio}
            onChange={(e) => update("envio", e.target.value)}
            data-testid="dp-envio"
          />
        </div>
        <div className="dp-row">
          <label className="dp-lbl">Notas internas</label>
          <textarea
            className="dp-ta"
            rows={3}
            value={form.notas}
            onChange={(e) => update("notas", e.target.value)}
            data-testid="dp-notas"
          />
        </div>
        <div className="dp-hint">
          Estos campos se incluyen en el PDF del paso 5. (Sprint 4: persistencia)
        </div>
      </div>
    </details>
  );
}
