# PDF snapshot tests · `_generate_pdf` golden files

Red de seguridad contra regresiones backend silenciosas del renderer fpdf2.
Tests definidos en `api/tests/test_pdf_snapshots.py`. Goldens (uno por caso
canónico) en este directorio bajo `test_pdf_snapshots.ambr` (formato syrupy).

## Qué validan estos goldens

Que **dado un fixture FIJO de inputs** (datos canónicos replicados del
frontend mock), el output del PDF (texto extraído + estructura) **se mantiene
estable entre commits**. Cuando el snapshot rompe en CI sin que se haya tocado
`_generate_pdf` ni el template, **es una alerta legítima** que debe
investigarse antes de regenerar.

## Qué NO validan

**Los goldens NO certifican que las cifras matcheen el calculator real del
backend.** Certifican que dado un fixture específico de inputs, el output del
PDF es estable. Para validar cifras vs calculator real → ver sub-PR
`paso-1-real` futuro.

Ej: si en el golden de PRES-018 aparece "USD 1.538" como total, eso solo
significa que con los inputs del fixture el renderer escribe ese número en
el PDF. NO significa que el calculator real produzca USD 1.538 para esos
inputs (puede ser USD 1.540, USD 1.527, etc.).

## Cuándo regenerar

ÚNICAMENTE cuando hay un cambio INTENCIONAL al output del PDF (ej: nuevo
campo en el footer, copy actualizado por D'Angelo, nuevo formato de fecha
en el header). Antes de regenerar:

1. **Verificá que el cambio sea intencional**. Si CI rompe y no tocaste
   `_generate_pdf`, NO regeneres — el snapshot está cumpliendo su función
   detectando un cambio inadvertido. Investigá la causa.
2. **Revisá el diff** de los snapshots manualmente antes de commit.
3. **Documentá la razón** en el commit message o PR description.

## Cómo regenerar

```bash
cd api
python -m pytest tests/test_pdf_snapshots.py --snapshot-update
git diff tests/__snapshots__/  # revisión humana obligatoria
git add tests/__snapshots__/
git commit -m "test(pdf): regen snapshots por <razón intencional>"
```

## Estabilidad determinística

El helper `_normalize_pdf_text` en el test sustituye:

- Fechas `dd/mm/yyyy` y `dd.mm.yyyy` → `DATE` (porque
  `_generate_pdf` embebe `datetime.now()` 10+ veces)
- Whitespace múltiple → 1 espacio
- Líneas vacías múltiples → 1 línea vacía

Si necesitás agregar otra normalización (ej: trace_id random, hash hex que
cambia entre runs), extendé `_normalize_pdf_text` con la regex correspondiente.

## Cobertura actual

| Renderer | Cubierto |
|---|---|
| `_generate_pdf` modo standard | ✅ PRES-018 (con descuento) + PRES-017 (sin) |
| `_generate_edificio_pdf` | ❌ deuda · sub-PR futuro |
| `_generate_resumen_obra_pdf` | ❌ deuda |
| products_only mode | ❌ deuda |
| m² override + planilla footnote | ❌ deuda |
| `_generate_excel` | ❌ otro renderer · fuera de scope |

## Decisión arquitectónica

Este sub-PR es el resultado del análisis FASE 1 del sub-PR cancelado
`sprint-4/pdf-template-engine`. El scope real para migrar fpdf2 → WeasyPrint
es 12-18h (3 renderers × system deps en Railway) y arriesga regresión en
producción. Mantener fpdf2 + agregar snapshot tests (Opción D) es más
pragmático: 2-3h de trabajo, cero riesgo de producción, red de seguridad
permanente contra regresiones silenciosas.
