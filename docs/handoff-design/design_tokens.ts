// Design tokens · Marmoleria Operator IA
// Generated from operator-shared.css
// All colors in OKLCH where source uses OKLCH; hex preserved as hex.

export const colors = {
  surface: {
    bg:        '#0f1318',
    bgMuted:   '#161b22',
    surface:   '#1c2129',
    surface2:  '#232932',
  },
  line: {
    line:       'rgba(232,237,229,0.08)',
    lineStrong: 'rgba(232,237,229,0.14)',
    lineSoft:   'rgba(232,237,229,0.06)',
  },
  ink: {
    ink:     '#e8ede5',
    inkSoft: '#b9c0c8',
    inkMute: '#6d7682',
  },
  semantic: {
    accent:  '#a9c1d6',
    ok:      'oklch(0.78 0.13 150)',
    warn:    'oklch(0.84 0.13 75)',
    info:    'oklch(0.82 0.09 255)',
    human:   'oklch(0.74 0.09 300)',
    humanBg: 'oklch(0.70 0.09 300 / 0.10)',
    humanBd: 'oklch(0.70 0.09 300 / 0.32)',
    error:   'oklch(0.72 0.16 25)',
  },
} as const;

export const typography = {
  family: {
    serif: "'Fraunces', Georgia, serif",
    sans:  "'Inter Tight', system-ui, -apple-system, sans-serif",
    mono:  "'JetBrains Mono', ui-monospace, monospace",
  },
  size: {
    base:  '14px',
    h1:    '26px',
    h2:    '22px',
    h3:    '19px',
    label: '13px',
    small: '12.5px',
    micro: '10.5px',
  },
} as const;

export const radius = {
  sm:   '6px',
  md:   '10px',
  lg:   '14px',
  pill: '999px',
} as const;

export const layout = {
  topbarH:    56,
  sidebarW:   240,
  chatW:      480,
  pageMinW:   1440,
  mobileW:    375,
} as const;

export const motion = {
  ease: 'ease-in-out',
  durations: {
    pulse:       '1.6s',
    think:       '2.4s',
    skel:        '1.4s',
    cursorBlink: '1s',
  },
} as const;

export type ColorTokens = typeof colors;
export type TypographyTokens = typeof typography;
