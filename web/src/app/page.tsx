/**
 * Home definitiva · Sprint 2.5 switch-to-main.
 *
 * Reemplaza el placeholder de QA del Sprint 2 (`Sprint 2 · Design system
 * migrated`). Saludo de Valentina con vbubble + CTA primario "+ Nuevo
 * presupuesto" que lleva al paso 1 (`/quotes/new`).
 *
 * Reusa clases legacy de operator-shared.css (.ia-banner, .vbubble,
 * .btn.primary) — NO modificamos CSS.
 */
import Link from "next/link";

export default function Home() {
  return (
    <main
      style={{
        maxWidth: 720,
        margin: "0 auto",
        padding: "80px 24px",
        display: "flex",
        flexDirection: "column",
        gap: 32,
      }}
    >
      <div className="ia-banner">
        <div className="vbubble" aria-hidden="true" />
        <div className="text">
          <div
            className="font-mono"
            style={{
              fontSize: 11,
              color: "var(--ink-mute)",
              letterSpacing: "0.6px",
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            Presupuestos · D&apos;Angelo
          </div>
          <h1
            className="font-serif"
            style={{
              fontStyle: "italic",
              fontWeight: 500,
              fontSize: 32,
              color: "var(--ink)",
              letterSpacing: "-0.3px",
              margin: 0,
              lineHeight: 1.2,
            }}
          >
            Hola Marina, ¿arrancamos un presupuesto nuevo?
          </h1>
          <p
            style={{
              fontFamily: "var(--sans)",
              color: "var(--ink-soft)",
              marginTop: 16,
              lineHeight: 1.6,
              fontSize: 14,
            }}
          >
            Soy <em>Valentina</em>. Subí un plano y un brief — aunque sea informal — y extraigo
            cliente, ambiente, medidas, material y armo el contexto del paso 2 sola.
          </p>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "center" }}>
        <Link
          href="/quotes/new"
          className="btn primary"
          data-testid="cta-new-quote"
          style={{
            fontSize: 15,
            padding: "12px 24px",
          }}
        >
          + Nuevo presupuesto
        </Link>
      </div>
    </main>
  );
}
