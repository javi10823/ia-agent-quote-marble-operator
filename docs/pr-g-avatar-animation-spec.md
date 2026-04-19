# PR G — Avatar Valentina animado (breathing ring + shimmer + pulsing core)

Spec provisto por el usuario vía chat. Objetivo: reemplazar el avatar estático de Valentina por una versión con **actividad interna animada** que no mueva la bola (centro fijo), para dar sensación de vida sin distraer.

## 1 · Keyframes (agregar al `<style>` global)

```css
@keyframes vcore {
  0%, 100% { opacity: 0.3; transform: scale(0.92); }
  50%      { opacity: 1;   transform: scale(1.04); }
}
@keyframes vring {
  0%, 100% { opacity: 0.35; transform: scale(0.96); }
  50%      { opacity: 0.85; transform: scale(1.06); }
}
@keyframes vspin {
  0%   { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
```

## 2 · Componente `VAvatar` (reemplaza el actual)

```tsx
// Valentina avatar — breathing ring + rotating conic shimmer + pulsing core.
// No position shift; size/location stay fixed. Pass `still` to freeze
// (e.g. print/favicon/screenshot).
function VAvatar({ size = 28, accent = '#a9c1d6', still }) {
  const id = React.useId();
  const anim = !still;
  return (
    <span style={{
      display: 'inline-block', position: 'relative',
      width: size, height: size, flexShrink: 0,
    }}>
      {/* outer breathing ring */}
      {anim && (
        <span style={{
          position: 'absolute', inset: -2, borderRadius: '50%',
          background: `radial-gradient(closest-side, transparent 58%, ${accent} 70%, transparent 88%)`,
          animation: 'vring 2.4s ease-in-out infinite',
          pointerEvents: 'none',
        }} />
      )}
      {/* conic shimmer — slow rotation, masked to a ring */}
      {anim && (
        <span style={{
          position: 'absolute', inset: 2, borderRadius: '50%',
          background: `conic-gradient(from 0deg, transparent 0deg, ${accent} 60deg, transparent 140deg, transparent 360deg)`,
          opacity: 0.5, mixBlendMode: 'screen',
          maskImage: 'radial-gradient(circle, black 55%, transparent 80%)',
          WebkitMaskImage: 'radial-gradient(circle, black 55%, transparent 80%)',
          animation: 'vspin 5.5s linear infinite',
          pointerEvents: 'none',
        }} />
      )}
      {/* sphere + pulsing core + specular highlight */}
      <svg width={size} height={size} viewBox="0 0 40 40" style={{ position: 'relative', display: 'block' }}>
        <defs>
          <radialGradient id={`g${id}`} cx="35%" cy="30%" r="70%">
            <stop offset="0%"   stopColor="oklch(0.88 0.07 200)" />
            <stop offset="55%"  stopColor={accent} />
            <stop offset="100%" stopColor="oklch(0.38 0.06 220)" />
          </radialGradient>
          <radialGradient id={`core${id}`} cx="40%" cy="38%" r="55%">
            <stop offset="0%"   stopColor="rgba(255,255,255,0.85)" />
            <stop offset="55%"  stopColor="rgba(255,255,255,0)" />
            <stop offset="100%" stopColor="rgba(255,255,255,0)" />
          </radialGradient>
        </defs>
        <circle cx="20" cy="20" r="18" fill={`url(#g${id})`} />
        <circle cx="20" cy="20" r="15" fill={`url(#core${id})`}
          style={anim ? { animation: 'vcore 2.4s ease-in-out infinite', transformOrigin: '20px 20px' } : undefined} />
        <ellipse cx="14" cy="14" rx="6" ry="3" fill="rgba(255,255,255,0.4)" />
        <ellipse cx="12" cy="12" rx="2" ry="1.2" fill="rgba(255,255,255,0.75)" />
      </svg>
    </span>
  );
}
```

## Notas del spec

- 3 ciclos desfasados (**2.4s / 5.5s / 2.4s**) — da sensación de actividad interna sin que la bola se mueva.
- `mix-blend-mode: screen` en el shimmer — solo funciona bien sobre fondo oscuro; si se pone sobre light mode, cambiar a `overlay` o bajar opacidad.
- `accent` ahora es prop — pasar el color del sistema (`var(--acc)` = `#5f7da0` en la app). El default del spec es `#a9c1d6` (celeste polvo del design).
- `still` freeza todo (útil para screenshots, PDF export, favicon).

## Dónde va en el código actual

Hoy **no existe** un `VAvatar` en la app. Los avatares de Valentina en el chat son un simple div Tailwind:
```tsx
// web/src/components/chat/MessageBubble.tsx — avatar assistant
<div className="w-[30px] h-[30px] rounded-full bg-acc text-white text-[11px] font-semibold flex items-center justify-center">V</div>
```

Plan de implementación cuando llegue el turno:

1. Crear `web/src/components/ui/VAvatar.tsx` con el componente + keyframes inline (via `styled-jsx` o en `globals.css`).
2. Agregar los 3 keyframes a `globals.css` en la sección `/* Animations */`.
3. Reemplazar el avatar "V" de `MessageBubble.tsx` (role="assistant") por `<VAvatar size={30} accent="var(--acc)" />`.
4. En contextos donde no conviene animar (PDF export, condición `prefers-reduced-motion`), pasar `still`. Agregar media query global que active `still` automáticamente con `@media (prefers-reduced-motion: reduce)` si es posible, o escucharlo vía JS hook.
5. Verificar que el hash `conic-gradient` render correcto en Safari ≥ 13 y Chrome/Firefox modernos.
6. Screenshot comparativo antes/después.

## Prioridad

Depende del usuario — probablemente post-PR D (chat restyle) para poder integrarlo con el message bubble restyleado.
