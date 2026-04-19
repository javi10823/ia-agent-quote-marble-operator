"use client";

import { useId } from "react";

interface Props {
  size?: number;
  /** Color del centro de la esfera. Por defecto `var(--acc)`. */
  accent?: string;
  /** Congela todas las animaciones (útil para screenshots, PDF export,
   * favicon, prefers-reduced-motion). */
  still?: boolean;
  className?: string;
}

/**
 * Avatar de Valentina — esfera "piedra pulida" con 3 capas de animación
 * desfasadas (breathing ring 2.4s / conic shimmer 5.5s / pulsing core
 * 2.4s). La bola NO se mueve de posición — el efecto es actividad
 * interna, no movimiento.
 *
 * Las 3 capas:
 *  1. Outer breathing ring — radial gradient expandiéndose/contrayéndose
 *  2. Conic shimmer — segmento de color rotando a 5.5s, enmascarado en
 *     anillo para que nunca tape el centro. `mix-blend-mode: screen`
 *     — sólo se ve bien sobre fondo oscuro.
 *  3. Pulsing core — highlight central (radial white→transparent) que
 *     pulsa en sincronía con el ring, dando la impresión de que "late".
 *
 * Keyframes: `vcore`, `vring`, `vspin` en globals.css.
 *
 * Uso:
 *   <VAvatar />                         // default 28px, acento sistema
 *   <VAvatar size={52} />                // hero
 *   <VAvatar size={30} still />          // congelar (screenshot)
 */
export default function VAvatar({ size = 28, accent = "var(--acc)", still, className }: Props) {
  const gid = useId();
  const anim = !still;

  return (
    <span
      className={className}
      style={{
        display: "inline-block",
        position: "relative",
        width: size,
        height: size,
        flexShrink: 0,
      }}
    >
      {/* outer breathing ring */}
      {anim && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            inset: -2,
            borderRadius: "50%",
            background: `radial-gradient(closest-side, transparent 58%, ${accent} 70%, transparent 88%)`,
            animation: "vring 2.4s ease-in-out infinite",
            pointerEvents: "none",
          }}
        />
      )}

      {/* conic shimmer — slow rotation, masked to a ring */}
      {anim && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            inset: 2,
            borderRadius: "50%",
            background: `conic-gradient(from 0deg, transparent 0deg, ${accent} 60deg, transparent 140deg, transparent 360deg)`,
            opacity: 0.5,
            mixBlendMode: "screen",
            maskImage: "radial-gradient(circle, black 55%, transparent 80%)",
            WebkitMaskImage: "radial-gradient(circle, black 55%, transparent 80%)",
            animation: "vspin 5.5s linear infinite",
            pointerEvents: "none",
          }}
        />
      )}

      {/* sphere + pulsing core + specular highlight */}
      <svg
        width={size}
        height={size}
        viewBox="0 0 40 40"
        style={{ position: "relative", display: "block" }}
        aria-hidden
      >
        <defs>
          <radialGradient id={`g${gid}`} cx="35%" cy="30%" r="70%">
            <stop offset="0%" stopColor="oklch(0.88 0.07 200)" />
            <stop offset="55%" stopColor={accent} />
            <stop offset="100%" stopColor="oklch(0.38 0.06 220)" />
          </radialGradient>
          <radialGradient id={`core${gid}`} cx="40%" cy="38%" r="55%">
            <stop offset="0%" stopColor="rgba(255,255,255,0.85)" />
            <stop offset="55%" stopColor="rgba(255,255,255,0)" />
            <stop offset="100%" stopColor="rgba(255,255,255,0)" />
          </radialGradient>
        </defs>
        <circle cx="20" cy="20" r="18" fill={`url(#g${gid})`} />
        <circle
          cx="20"
          cy="20"
          r="15"
          fill={`url(#core${gid})`}
          style={
            anim
              ? { animation: "vcore 2.4s ease-in-out infinite", transformOrigin: "20px 20px" }
              : undefined
          }
        />
        <ellipse cx="14" cy="14" rx="6" ry="3" fill="rgba(255,255,255,0.4)" />
        <ellipse cx="12" cy="12" rx="2" ry="1.2" fill="rgba(255,255,255,0.75)" />
      </svg>
    </span>
  );
}
