import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // ── Legacy tokens (sin tocar — mantener intactos) ─────────────
        bg: "var(--bg)",
        s1: "var(--s1)",
        s2: "var(--s2)",
        s3: "var(--s3)",
        b1: "var(--b1)",
        b2: "var(--b2)",
        b3: "var(--b3)",
        t1: "var(--t1)",
        t2: "var(--t2)",
        t3: "var(--t3)",
        t4: "var(--t4)",
        acc: "var(--acc)",
        "acc-bg": "var(--acc2)",
        "acc-ring": "var(--acc3)",
        "acc-hover": "var(--acc-hover)",
        "acc-ink": "var(--acc-ink)",
        grn: "var(--grn)",
        "grn-bg": "var(--grn2)",
        amb: "var(--amb)",
        "amb-bg": "var(--amb2)",
        err: "var(--red)",

        // ── V2 tokens · Sprint 2 (handoff-design/design_tokens.ts) ────
        // Apuntan a CSS vars definidas en src/app/v2/globals.css. Sin
        // colisión con legacy — nombres distintos. Compartidos con
        // operator-shared.css (que también declara las mismas vars en
        // su :root, así que cualquier source que se cargue first gana).
        accent: "var(--accent)", //  #a9c1d6 celeste polvo · IA
        human: "var(--human)", //   oklch(0.74 0.09 300) púrpura · editado
        "human-bg": "var(--human-bg)",
        "human-bd": "var(--human-bd)",
        ok: "var(--ok)",
        warn: "var(--warn)",
        info: "var(--info)",
        error: "var(--error)",
        ink: "var(--ink)",
        "ink-soft": "var(--ink-soft)",
        "ink-mute": "var(--ink-mute)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        "bg-muted": "var(--bg-muted)",
        line: "var(--line)",
        "line-strong": "var(--line-strong)",
        "line-soft": "var(--line-soft)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "-apple-system", "BlinkMacSystemFont", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      // ── V2 border radius tokens ──────────────────────────────────
      // NO overrideamos rounded-sm/md/lg defaults de Tailwind — el
      // legacy los usa con valores defaults (2/6/8 px). Para v2 se
      // usan via arbitrary values: `rounded-[var(--r-md)]` o las
      // clases custom `rounded-r-sm/r-md/r-lg` definidas acá.
      borderRadius: {
        "r-sm": "var(--r-sm)", // 6px
        "r-md": "var(--r-md)", // 10px
        "r-lg": "var(--r-lg)", // 14px
      },
    },
  },
  plugins: [],
};

export default config;
