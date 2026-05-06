# Known Issues · Sprint 2-5

Este archivo lista bugs conocidos, deuda técnica y gaps detectados en audit que NO bloquean merge pero deben revisitarse en Sprint 5 (QA + perf).

Reglas:
- Cada item documenta: PR de origen, severidad, descripción, plan
- Severidades: BLOCKER (bloquea producción), MAJOR (visible al usuario), MINOR (cosmético/test)
- Cuando un item se resuelve, mover a sección "Resueltos" con commit hash

## Issues abiertos

### sprint-2/paso-1-brief-upload (PR #457) · MINOR · Cobertura E2E parcial de validaciones

**Detectado:** audit independiente PR #457, 06.05.2026, NICE-TO-HAVE 2.

**Descripción:** El mock client `createDraftQuote` implementa 6 validaciones client-side (PDF mime, PDF 20MB, photos count <=5, photo mime, photo 5MB, brief 2000 chars). Los tests E2E cubren 3 de 6 validaciones. Faltan tests para:
- Foto > 5MB rechaza con error
- Brief text > 2000 chars rechaza con error
- Más de 5 fotos rechaza con error

**Impacto:** Las validaciones SÍ funcionan en el código (verificado en audit). Solo no hay tests E2E que prevengan regresiones futuras.

**Plan:** agregar 3 tests E2E faltantes en Sprint 5 (sprint-5/qa-e2e-suite) o como tarea preventiva en cualquier PR posterior que toque el flujo de archivos del paso 1.

### sprint-2/chrome-refactor (PR #456) · MINOR · Inline styles heredados

Detectado en audit independiente PR #457 NICE-TO-HAVE 5. Inline `style={{...}}` en algún componente del chrome shell. Cleanup: Sprint 5.

## Resueltos

_(vacío al inicio)_
