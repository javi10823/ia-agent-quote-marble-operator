/**
 * Placeholder de la home de v2 (`/v2`).
 *
 * Sprint 2 design-system-migration: confirma que tokens + fonts +
 * operator-shared.css están cableados. Texto y estilos son demo
 * exclusivamente del sistema de design — no datos funcionales. El
 * dashboard real va en Sprint 4 (mockups 23/25 del Master §6).
 */
export default function V2HomePage() {
  return (
    <main className="p-8">
      <h1 className="text-3xl font-sans text-ink">Sprint 2 · Design system migrated</h1>

      {/* Fraunces serif italic — voz de Valentina */}
      <p className="mt-2 font-serif italic text-ink-soft">
        Hola, soy Valentina. Acá hablo con tipografía serif itálica.
      </p>

      {/* JetBrains Mono — eyebrow demo (no es dato real, es ilustración del token) */}
      <p className="mt-4 font-mono text-sm uppercase tracking-wide text-ink-mute">
        DEMO · token mono
      </p>

      {/* Botones demo de la convención IA-celeste / Humano-púrpura */}
      <div className="mt-6 flex gap-2">
        <button type="button" className="rounded-r-md bg-accent px-4 py-2 text-bg">
          Acción IA
        </button>
        <button
          type="button"
          className="rounded-r-md border border-human bg-human-bg px-4 py-2 text-human"
        >
          Editado por humano
        </button>
      </div>

      {/* Footer técnico — referencia para audit visual del PR */}
      <p className="mt-10 font-mono text-xs text-ink-mute">
        Tokens · fonts · operator-shared.css · v2 layout — wire-up de features en sub-PRs siguientes
        (chrome-refactor, paso-1, paso-2).
      </p>
    </main>
  );
}
