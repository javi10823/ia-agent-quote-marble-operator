import { Fraunces, Inter_Tight, JetBrains_Mono } from "next/font/google";

// Inter Tight — UI primaria (títulos UI, body, labels).
export const interTight = Inter_Tight({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

// Fraunces — serif italic para hero "Hola, soy Valentina", importes editoriales,
// y acentos tipográficos cálidos. Optical size 9..144 porque la usamos desde
// 13px (notas) hasta 42px (saludo hero).
export const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});

// JetBrains Mono — números (medidas, importes USD/ARS, tags mono tipo
// "DEL BRIEF" en tracking wide).
export const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});
