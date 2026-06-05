/**
 * PDF preview inline · Sprint 4 paso-5-pdf-preview · fix-up #1 post visual Javi.
 *
 * Replica el template HTML del backend (`api/templates/quote-template.html`)
 * **1:1 LITERAL**. Source-of-truth visual: ese archivo. Si cambia el template,
 * este componente se debe re-alinear (drift se detectaría con visual check).
 *
 * Mapeo Jinja → datos del frontend:
 * - `fecha`                       → `fechaFmt` (server-side determinístico)
 * - `cliente`                     → `quote.clientFull`
 * - `forma_pago`                  → `${state.anticipoPct}% anticipo · ${datosPdf.saldo}`
 * - `proyecto`                    → `context.tipologia` ?? `quote.client`
 * - `fecha_entrega`               → `state.plazo`
 * - `material_nombre+espesor`     → `calculation.material.rows[0].label`
 * - `material_m2/precio/total`    → `calculation.material.rows[0].qty/unit/total`
 * - `pieza_descripcion` (loop)    → `pieces[].label`
 * - `descuento_monto` (cond)      → `calculation.material.rows[1].total` (variant=discount)
 * - `material_total_neto`         → `calculation.material.subtotal`
 * - `sobrante_*` (cond)           → `calculation.merma.rows[0]` cuando `status='aplica'`
 * - `pileta_*` (cond)             → `calculation.piletas.*` cuando `variant='info'`
 * - `mo_*` (loop)                 → `calculation.labor.rows[].label/qty/basePrice/total`
 * - `total_pesos`                 → `calculation.labor.subtotal`
 * - `grand_total`                 → "${totals.ars.value} mano de obra + ${totals.usd.value} material"
 *
 * Side-issue arquitectónico (documentado en PR description): el backend YA
 * tiene este template pero NO LO USA. El PDF actual se genera con `fpdf2`
 * (programático, `document_tool.py:1285`). Hasta que un sub-PR backend
 * posterior migre a WeasyPrint + este template, el preview frontend puede
 * diferir del PDF que recibe el cliente.
 */
"use client";

import type { CalculationResult, Piece, PdfTrace, QuoteHeader } from "@/lib/api";
import type { PdfFormState } from "@/lib/hooks/usePdfForm";
import { DANGELO_LOGO_SVG } from "./dangeloLogoSvg";

interface Props {
  quote: QuoteHeader;
  calculation: CalculationResult;
  trace: PdfTrace;
  state: PdfFormState;
  /** Fecha formateada `dd.mm.yyyy` · pre-calculada en el container. */
  fechaFmt: string;
  /** Piezas del paso-3 (loop `row-piece`). */
  pieces: Piece[];
  /** Tipología del paso-2 (campo `proyecto` del PDF · contexto). */
  proyecto: string;
}

function isValidText(s: string | null | undefined): s is string {
  if (typeof s !== "string") return false;
  const t = s.trim();
  return t.length > 0 && t !== "—";
}

export function PdfPreviewDoc({
  quote,
  calculation,
  state,
  fechaFmt,
  pieces,
  proyecto,
}: Props) {
  const materialRow = calculation.material.rows[0];
  const discountRow =
    calculation.material.rows.length > 1
      ? calculation.material.rows[calculation.material.rows.length - 1]
      : undefined;
  const hasDiscount = discountRow?.variant === "discount";

  const mermaAplica = calculation.merma.status === "aplica";
  const sobranteRow = mermaAplica ? calculation.merma.rows?.[0] : undefined;

  const piletaInfo = calculation.piletas.variant === "info" ? calculation.piletas : null;

  const formaPago = isValidText(state.anticipoPct)
    ? `${state.anticipoPct}% anticipo · ${calculation.datosPdf.saldo}`
    : calculation.datosPdf.saldo;

  return (
    <div className="pdf-doc-inline" data-testid="pdf-doc-inline">
      <div className="top-bar" aria-hidden="true" />
      <div className="content">
        <div className="header">
          {/* Logo SVG vectorial extraído LITERAL del template
              (api/templates/quote-template.html). Ver dangeloLogoSvg.ts. */}
          <div
            className="logo-svg-wrap"
            data-testid="pdf-logo"
            aria-label="Logo D'Angelo Marmolería"
            dangerouslySetInnerHTML={{ __html: DANGELO_LOGO_SVG }}
          />
          <div className="contact">
            SAN NICOLAS 1160
            <br />
            341-3082996
            <br />
            marmoleriadangelo@gmail.com
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
            <span className="client-label">Cliente: </span>
            <span className="client-value" data-testid="pdf-cliente">
              {quote.clientFull}
            </span>
          </div>
          <div className="client-cell">
            <span className="client-label">Forma de pago</span>
            <br />
            <span className="client-value" data-testid="pdf-forma-pago">
              {formaPago}
            </span>
          </div>
          <div className="client-cell" style={{ marginTop: "2mm" }}>
            <span className="client-label">Proyecto </span>
            <span className="client-value" data-testid="pdf-proyecto">
              {isValidText(proyecto) ? proyecto : quote.client}
            </span>
          </div>
          <div className="client-cell" style={{ marginTop: "2mm" }}>
            <span className="client-label">Fecha de entrega</span>
            <br />
            <span
              className="client-value"
              style={{ whiteSpace: "pre-wrap" }}
              data-testid="pdf-fecha-entrega"
            >
              {state.plazo || "—"}
            </span>
          </div>
        </div>

        <hr />

        <table className="items-table">
          <thead>
            <tr>
              <th className="col-desc">Descripción</th>
              <th className="col-cant right">Cantidad</th>
              <th className="col-precio right">Precio unitario</th>
              <th className="col-total right">Precio total</th>
            </tr>
          </thead>
          <tbody>
            {/* ── MATERIAL ── */}
            <tr className="row-material">
              <td>{materialRow?.label ?? quote.material}</td>
              <td className="right">{materialRow?.qty ?? "—"}</td>
              <td className="right">{materialRow?.unit ?? "—"}</td>
              <td className="right">{materialRow?.total ?? "—"}</td>
            </tr>

            {/* ── Sub-filas piezas (row-piece) ── */}
            {pieces.map((p, idx) => {
              const isLast = idx === pieces.length - 1;
              return (
                <tr
                  className={`row-piece${isLast ? " row-piece-last" : ""}`}
                  key={p.id}
                  data-testid="pdf-row-piece"
                >
                  <td>{p.label}</td>
                  <td />
                  <td />
                  <td />
                </tr>
              );
            })}

            {/* ── DESCUENTO (cond) ── */}
            {hasDiscount && (
              <tr className="row-desc">
                <td />
                <td />
                <td className="right">
                  <em>DESC</em>
                </td>
                <td className="right" data-testid="pdf-descuento">
                  {discountRow?.total}
                </td>
              </tr>
            )}

            {/* ── Subtotal material ── */}
            <tr className="row-subtotal">
              <td colSpan={2} />
              <td>Total USD</td>
              <td data-testid="pdf-subtotal-usd">{calculation.material.subtotal}</td>
            </tr>

            <tr className="row-spacer">
              <td colSpan={4} />
            </tr>

            {/* ── SOBRANTE (cond · merma.status='aplica') ── */}
            {sobranteRow && (
              <>
                <tr className="row-material" data-testid="pdf-row-sobrante">
                  <td>SOBRANTE</td>
                  <td className="right">{sobranteRow.qty}</td>
                  <td className="right">{sobranteRow.unit}</td>
                  <td className="right">{sobranteRow.total}</td>
                </tr>
                <tr className="row-subtotal">
                  <td colSpan={2} />
                  <td>Total USD</td>
                  <td>{sobranteRow.total}</td>
                </tr>
                <tr className="row-spacer">
                  <td colSpan={4} />
                </tr>
              </>
            )}

            {/* ── PILETA (cond · piletas.variant='info') ── */}
            {piletaInfo && (
              <>
                <tr className="row-pileta" data-testid="pdf-row-pileta">
                  <td>{piletaInfo.chipLabel}</td>
                  <td className="right" />
                  <td className="right" />
                  <td className="right" />
                </tr>
                <tr className="row-spacer">
                  <td colSpan={4} />
                </tr>
              </>
            )}

            {/* ── MANO DE OBRA ── */}
            <tr className="row-mo-header">
              <td colSpan={4}>MANO DE OBRA</td>
            </tr>
            {calculation.labor.rows.map((r) => (
              <tr className="row-labor" key={r.sku} data-testid="pdf-row-labor">
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

        {/* FOOTER · copy LITERAL del template */}
        <div className="footer">
          <p>
            <span className="bold">*COTIZACION OFICIAL:</span> dolar venta banco nacion. Los
            materiales expresados en dólares se pagan en pesos según la cotizacion del dia.
          </p>

          <p className="section">
            NOTA: Por ser el granito y mármol un producto de la naturaleza, las tonalidades,
            vetas y manchas pueden diferir de las muestras exhibidas.
          </p>

          <p className="section bold">CONDICIONES</p>
          <p>*PRESUPUESTO SUJETO A VARIACIÓN DE PRECIO</p>
          <p>
            *MATERIALES IMPORTADOS SEGÚN COTIZACION DOLAR VENTA BANCO NACIÓN AL MOMENTO DE LA
            CONFIRMACION
          </p>
          <p>
            *LA TOMA DE MEDIDAS NO PODRÁ SUPERAR LOS 30 DÍAS DESDE LA CONFIRMACIÓN DEL TRABAJO,
            CASO CONTRARIO EL 20 % RESTANTE SE ACTUALIZARA AL MOMENTO DE LA CANCELACIÓN SEGÚN
            INDICE LA CONSTRUCCIÓN
          </p>
          <p>*PRESUPUESTO DEFINITIVO SEGÚN MEDIDAS TOMADAS EN OBRA</p>
          <p>*LOS PRECIOS INCLUYEN IVA</p>

          <p className="section bold">FORMAS DE PAGO</p>
          <p>
            *Materiales Importados: 80% seña , 20% restante contra entrega (cotización dolar
            venta BCO NACIÓN).
          </p>
          <p>*Materiales Nacionales: 80% seña , 20% restante contra entrega.</p>
          <p>
            Pago contado / transferencia / débito / crédito / cheques 15 días para importados y
            30 días para nacionales
          </p>
          <p className="section">TARJETAS DE CREDITO CONSULTAR PLANES</p>
        </div>
      </div>
    </div>
  );
}
