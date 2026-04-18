# Mockups · Estado actual del producto

36 archivos HTML standalone que capturan **cómo luce HOY** la app de Valentina (D'Angelo Marmolería). Se exportaron para pasarlos a Claude Design como referencia y que sobre eso proponga el rediseño.

## Cómo abrirlos

Cada archivo es autocontenido — zero build, zero dependencias. `open docs/mockups/<archivo>.html` en el navegador.

Cada mockup tiene un label arriba indicando el viewport objetivo (`Desktop 1440×900` o `Mobile 390×844`). El marco interno replica exactamente esos píxeles.

## Caso de datos

Todos los mockups usan el caso **Bernardi** (realista, extraído de tickets reales):

- **Cliente:** Erica Bernardi
- **Proyecto:** Casa Bernardi — Rosario
- **Material:** Puraprima Onix White Mate (3 cm)
- **Sectores:** Cocina en U + Isla central (4 tramos)
- **Pileta:** doble (empotrada por regla D'Angelo)
- **Anafe:** 2 (gas + eléctrico)
- **Zócalos:** trasero 7 cm por tramo
- **Colocación:** sí
- **Total:** USD 3.180 / $ 4.284.000

En el dashboard hay ~8 presupuestos variados (Bernardi como borrador activo, más casos de otros materiales y estados) para mostrar la grilla llena.

## Index

### Pantallas completas (10 = 5 vistas × desktop/mobile)
| # | Vista | Desktop | Mobile |
|---|---|---|---|
| 01 | Login | `01-login-desktop.html` | `01-login-mobile.html` |
| 02 | Dashboard con presupuestos | `02-dashboard-populated-desktop.html` | `02-dashboard-populated-mobile.html` |
| 02b | Dashboard vacío | `02b-dashboard-empty-desktop.html` | `02b-dashboard-empty-mobile.html` |
| 03 | Detalle de presupuesto (tab Detalle) | `03-quote-detail-desktop.html` | `03-quote-detail-mobile.html` |
| 04 | Catálogo / Configuración | `04-settings-catalog-desktop.html` | `04-settings-catalog-mobile.html` |

### Estados del chat (18 = 9 estados × desktop/mobile)
| # | Estado | Desktop | Mobile |
|---|---|---|---|
| 10 | Chat vacío (quote recién creado) | `10-chat-empty-desktop.html` | `10-chat-empty-mobile.html` |
| 11 | Brief enviado, Valentina pensando | `11-chat-brief-sent-desktop.html` | `11-chat-brief-sent-mobile.html` |
| 12 | Plano procesándose | `12-chat-plano-processing-desktop.html` | `12-chat-plano-processing-mobile.html` |
| 13 | Zone selector (plano multi-página) | `13-chat-zone-selector-desktop.html` | `13-chat-zone-selector-mobile.html` |
| 14 | Análisis de contexto | `14-chat-context-analysis-desktop.html` | `14-chat-context-analysis-mobile.html` |
| 15 | Despiece (dual read) confirmado | `15-chat-dual-read-desktop.html` | `15-chat-dual-read-mobile.html` |
| 16 | Calculando | `16-chat-calculating-desktop.html` | `16-chat-calculating-mobile.html` |
| 17 | Final con PDF/Excel/Drive | `17-chat-final-with-pdfs-desktop.html` | `17-chat-final-with-pdfs-mobile.html` |
| 18 | Error / Retry | `18-chat-error-retry-desktop.html` | `18-chat-error-retry-mobile.html` |

### Cards individuales (8, desktop only ~900px)
| # | Card | Archivo |
|---|---|---|
| 20 | Context Analysis (3 secciones) | `20-card-context-analysis.html` |
| 21 | Dual Read Result (despiece) | `21-card-dual-read.html` |
| 22 | Zone Selector | `22-card-zone-selector.html` |
| 23 | Resumen de Obra | `23-card-resumen-obra.html` |
| 24 | Email Draft | `24-card-email-draft.html` |
| 25 | Condiciones | `25-card-condiciones.html` |
| 26 | Message bubbles (user / thinking / text / calc / tabla) | `26-card-message-bubbles.html` |
| 27 | Composer / ChatInput (incl. drag&drop overlay) | `27-composer-chat-input.html` |

## Sistema visual actual

- **Fuentes:** Geist Sans (UI), Geist Mono (números), fallback `-apple-system,BlinkMacSystemFont,system-ui`.
- **Paleta:** dark puro. Fondo `#07070e`, superficies `#0c0c16 / #101018 / #15151f`.
- **Bordes:** `rgba(255,255,255,.07 / .13 / .20)`.
- **Tinta:** `rgba(255,255,255,.96 / .58 / .28 / .14)`.
- **Acento:** azul `#4f8fff` (+ alphas 0.12 / 0.22).
- **Estado:** verde `#30d158` (validado), amber `#f5a623` (borrador / warning), rojo `#ff453a` (error).
- **Overlay de ruido:** SVG fractalNoise 0.02 opacity sobre todo el body.
- **Escrollbar:** 3px en pointer fino, 6px en táctil.

Ver `web/src/app/globals.css` para la fuente canónica de tokens.
