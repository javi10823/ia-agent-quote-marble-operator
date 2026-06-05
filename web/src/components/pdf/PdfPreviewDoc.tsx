/**
 * PDF preview inline · mockup 18 LITERAL.
 *
 * Renderea el A4 directamente en el DOM (no iframe) usando las clases
 * legacy `.pdf-doc-inline` + sub-clases del operator-shared.css. Reflee
 * datos en vivo del `state` del sidebar (vigencia/anticipo/plazo).
 *
 * Logo: placeholder SVG inline simple. El base64 del mockup 18 (logo real
 * D'Angelo) puede inyectarse en sub-PR posterior · acá usamos texto con
 * misma altura (~32px) para no inflar el bundle del componente.
 */
"use client";

import type { CalculationResult, PdfTrace, QuoteHeader } from "@/lib/api";
import type { PdfFormState } from "@/lib/hooks/usePdfForm";

interface Props {
  quote: QuoteHeader;
  calculation: CalculationResult;
  trace: PdfTrace;
  state: PdfFormState;
  /** Fecha formateada `dd.mm.yyyy` · pre-calculada en el container. */
  fechaFmt: string;
}

export function PdfPreviewDoc({ quote, calculation, state, fechaFmt }: Props) {
  const m2Fmt =
    typeof quote.m2 === "number"
      ? quote.m2.toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : String(quote.m2);

  return (
    <div className="pdf-doc-inline" data-testid="pdf-doc-inline">
      <div className="top-bar" aria-hidden="true" />
      <div className="content">
        <div className="header">
          <div
            className="logo-img"
            aria-label="Logo D'Angelo Marmolería"
            data-testid="pdf-logo"
            style={{
              fontFamily: "Georgia, serif",
              fontStyle: "italic",
              fontSize: 22,
              fontWeight: 700,
              color: "#1a1a1a",
              lineHeight: 1.2,
            }}
          >
            D&apos;Angelo
            <span style={{ fontSize: 10, fontStyle: "normal", letterSpacing: 1.5, marginLeft: 6 }}>
              MARMOLERÍA
            </span>
          </div>
          <div className="contact">
            Tel: 11 4444-5555 · WhatsApp: 11 5555-6666
            <br />
            ventas@dangelo.com.ar · @dangelo.marmoleria
          </div>
        </div>

        <div className="title-section">
          <h1>Presupuesto</h1>
          <div className="fecha" data-testid="pdf-fecha">
            Fecha: {fechaFmt}
          </div>
        </div>

        <div className="client-grid">
          <div className="client-cell">
            <span className="client-label">Cliente</span>
            <span className="client-value" data-testid="pdf-cliente">
              {quote.clientFull}
            </span>
          </div>
          <div className="client-cell">
            <span className="client-label">Proyecto</span>
            <span className="client-value">{quote.client}</span>
          </div>
          <div className="client-cell">
            <span className="client-label">Datos de envío</span>
            <span
              className="client-value"
              style={{ whiteSpace: "pre-wrap" }}
              data-testid="pdf-envio"
            >
              {state.envio || "—"}
            </span>
          </div>
          <div className="client-cell">
            <span className="client-label">Vigencia</span>
            <span className="client-value" data-testid="pdf-vigencia">
              {state.vigenciaDias || "—"} {state.vigenciaDias === "1" ? "día" : "días"} desde hoy
            </span>
          </div>
        </div>

        <hr />

        <table className="items-table">
          <thead>
            <tr>
              <th className="col-desc">Detalle</th>
              <th className="col-cant right">Cant.</th>
              <th className="col-precio right">Precio</th>
              <th className="col-total right">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr className="row-material">
              <td>{quote.material}</td>
              <td className="right">{m2Fmt} m²</td>
              <td className="right">{calculation.material.rows[0]?.unit ?? "—"}</td>
              <td className="right">{calculation.material.rows[0]?.total ?? "—"}</td>
            </tr>
            {calculation.material.rows.length > 1 && (
              <tr className="row-desc">
                <td colSpan={2} />
                <td className="right">
                  <em>DESC arq.</em>
                </td>
                <td className="right">{calculation.material.rows[1]?.total}</td>
              </tr>
            )}
            <tr className="row-subtotal">
              <td colSpan={2} />
              <td>Total USD</td>
              <td data-testid="pdf-subtotal-usd">{calculation.material.subtotal}</td>
            </tr>

            <tr className="row-spacer">
              <td colSpan={4} />
            </tr>

            <tr className="row-mo-header">
              <td colSpan={4}>MANO DE OBRA</td>
            </tr>
            {calculation.labor.rows.map((r) => (
              <tr className="row-labor" key={r.sku}>
                <td>{r.label}</td>
                <td className="right">{r.qty}</td>
                <td className="right">{r.basePrice}</td>
                <td className="right">{r.total}</td>
              </tr>
            ))}
            <tr className="row-total-pesos">
              <td colSpan={2} />
              <td>Total PESOS</td>
              <td data-testid="pdf-subtotal-ars">{calculation.labor.subtotal}</td>
            </tr>
          </tbody>
        </table>

        <div className="grand-total" data-testid="pdf-grand-total">
          PRESUPUESTO TOTAL: {calculation.totals.ars.value} mano de obra +{" "}
          {calculation.totals.usd.value} material
        </div>

        <div className="footer">
          <p>
            <span className="bold">*COTIZACION OFICIAL:</span> dolar venta banco nacion. Los
            materiales expresados en dólares se pagan en pesos según la cotizacion del dia.
          </p>
          <p className="section">
            NOTA: Por ser el granito y mármol un producto de la naturaleza, las tonalidades, vetas y
            manchas pueden diferir de las muestras exhibidas.
          </p>
          <p className="section bold">CONDICIONES</p>
          <p>*PRESUPUESTO SUJETO A VARIACIÓN DE PRECIO</p>
          <p>
            *MATERIALES IMPORTADOS SEGÚN COTIZACION DOLAR VENTA BANCO NACIÓN AL MOMENTO DE LA
            CONFIRMACION
          </p>
          <p data-testid="pdf-plazo-cond">
            *PLAZO: <span style={{ whiteSpace: "pre-wrap" }}>{state.plazo || "—"}</span>
          </p>
          <p>
            *LA TOMA DE MEDIDAS NO PODRÁ SUPERAR LOS 30 DÍAS DESDE LA CONFIRMACIÓN DEL TRABAJO, CASO
            CONTRARIO EL 20% RESTANTE SE ACTUALIZARÁ AL MOMENTO DE LA CANCELACIÓN SEGÚN INDICE LA
            CONSTRUCCIÓN
          </p>
          <p>*PRESUPUESTO DEFINITIVO SEGÚN MEDIDAS TOMADAS EN OBRA</p>
          <p>*LOS PRECIOS INCLUYEN IVA</p>

          <p className="section bold">FORMAS DE PAGO</p>
          <p data-testid="pdf-anticipo-cond">
            *ANTICIPO: <strong>{state.anticipoPct || "—"}%</strong> a la firma, el resto contra
            entrega.
          </p>
          <p>
            *Materiales Importados: pago contra entrega en pesos (cotización dolar venta BCO
            NACIÓN).
          </p>
          <p>*Materiales Nacionales: pago contado / transferencia / débito / crédito / cheques.</p>
        </div>
      </div>
    </div>
  );
}
