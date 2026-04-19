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
      },
      fontFamily: {
        sans: ["var(--font-sans)", "-apple-system", "BlinkMacSystemFont", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
