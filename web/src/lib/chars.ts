/**
 * Runtime-safe accented characters.
 *
 * Next.js 14 SWC double-escapes \uXXXX sequences in dynamic-route
 * bundles, rendering them as literal "\u00ED" on screen.
 * String.fromCharCode() produces the characters at runtime,
 * bypassing the serialiser entirely.
 */
const _ = String.fromCharCode;

export const A = _(0xe1); // á
export const E = _(0xe9); // é
export const I = _(0xed); // í
export const O = _(0xf3); // ó
export const U = _(0xfa); // ú
export const N = _(0xf1); // ñ
export const DOT = _(0xb7); // ·
export const SUP2 = _(0xb2); // ²
export const DASH = _(0x2014); // —
export const ITEM = _(0xcd); // Í (uppercase for "Ítem")
export const WARN = _(0x26a0) + _(0xfe0f); // ⚠️
export const CIRCLE = _(0x25cf); // ●
export const ARROW = _(0x2192); // →
export const XMARK = _(0x2715); // ✕
export const CLOUD = _(0x2601); // ☁
export const WAVE = _(0xd83d, 0xdc4b); // 👋
export const PAGE = _(0xd83d, 0xdcc4); // 📄
export const PICTURE = _(0xd83d, 0xddbc) + _(0xfe0f); // 🖼️
export const CLIP = _(0xd83d, 0xdcce); // 📎
export const RULER = _(0xd83d, 0xdcd0); // 📐
export const TAG = _(0xd83c, 0xdff7) + _(0xfe0f); // 🏷️
export const FOLDER = _(0xd83d, 0xdcc1); // 📁
export const CHART = _(0xd83d, 0xdcca); // 📊
