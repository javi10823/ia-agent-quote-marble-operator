# Backlog — Mejoras pendientes post-rediseño

Anotaciones durante la implementación del rediseño UI/UX (Claude Design handoff v2, abril 2026).

## UX — Navegación del chat

### Scroll-to interno al chat (tabs decorativas → anclas)
El rediseño propone tabs top-level **Desafío · Chat · Piezas · Resumen** para navegar rápido entre secciones. Decisión: diferido.

Cuando se implemente, la versión preferida es **anclas scroll-to dentro del mismo chat** (no vistas separadas). El usuario hace click en "Piezas" y el chat hace smooth-scroll hasta la card de despiece. Mantiene el flujo conversacional lineal actual pero acelera la navegación en presupuestos largos.

**Alternativa descartada:** vistas separadas por tab con estado persistido — implicaría refactor grande del ChatPage + nueva estructura de mensajes.

## UX — Split view con panel Piezas persistente

La propuesta "B" original (split view: chat a la izquierda, panel Piezas editable a la derecha en vivo) quedó descartada. Se mantiene el flujo actual: **todas las cards renderizan inline en el chat**.

Razón: la interactividad inline actual (doble-click para editar medidas en DualReadResult, radios en ContextAnalysis) ya cubre el caso. Un panel fijo agregaría complejidad de sincronización sin beneficio claro.

## Feature — "Desde obra anterior" (clonar quote con otro material)

Chip visible en el Home hero **pero deshabilitado** (gris, sin acción).

Feature propuesta: desde un presupuesto previo validado, crear uno nuevo **clonando estructura** (sectores, tramos, m², MO) pero permitiendo **cambiar el material**. Use case: cliente pidió Silestone, ahora quiere ver mismo plano en Dekton.

Backend necesita:
- Endpoint `POST /quotes/{id}/clone` que duplica el `dual_read_result` + `quote_breakdown` pero vacía `material` + `total_*`.
- Front navega al nuevo `quoteId` con el chat pre-poblado y pide solo el material nuevo.
- Valentina dispara directo el cálculo (sin volver a leer el plano).

## Feature — "Solo medidas" (dictar medidas sin plano)

Descartado. No había entry point en el backend actual y agregarlo implicaba un flow paralelo sin plano-reader. Si reaparece, el chip se re-habilita en HomeQuickActions.
