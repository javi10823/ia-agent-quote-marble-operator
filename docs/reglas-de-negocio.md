# Reglas de negocio — decisiones y dónde viven

Las reglas fuente (prompt del LLM, con tope de tokens: test_token_budget) están en `api/rules/*.md` (las lee el LLM) y los valores editables en `api/catalog/config.json`
(panel `/configuracion`). Este archivo guarda las **decisiones** y cómo las aplica el código.

## Descuento de edificio (18 %) — decidido por Javi el 27/11/2026
- Aplica cuando la **suma de m² de todos los materiales de la obra** es **> 15** (estricto: con 15,00 no aplica).
- Config: `discount.building_min_m2_threshold` (15) y `discount.building_percentage` (18) — panel → Descuentos.
- Código: `calculate_quote` recibe `edificio_otros_m2` (m² de los otros materiales ya cotizados de la obra, que arma el
  handler desde el breakdown y `_prior_calcs`) y devuelve `edificio_total_m2`.
- Un material cotizado antes de que la obra pasara el umbral queda sin el 18 %: el Paso 2 avisa "recalculá X". No se
  recalcula solo.
- Un descuento manual del operador gana sobre el automático. Edificio exige que el operador lo haya dicho
  (`edificio_authority.py`).

## "Sin pileta" — regla configurable (27/11/2026)
- Config: `defaults.sin_pileta_cobra_agujero` (panel → Defaults operativos). Default `true`.
- `true` (histórico): "sin pileta" / "sacar pileta" / "quitar pileta" a secas = el cliente la trae → no se cobra el
  producto pero SÍ el agujero y pegado (PEGADOPILETA).
- `false`: esas frases = no hay pileta → no se cobra nada de pileta.
- Las frases que nombran el producto ("sin producto de pileta", "cliente trae la pileta", "D'Angelo no provee")
  siempre significan "el cliente la trae" (se cobra el agujero), con la regla en `true` o `false`.

## Descuentos comerciales
- Los decide el operador: un `discount_pct` / `mo_discount_pct` que pasa el LLM solo vale si ese % figura en lo que
  escribió el operador (o ya estaba en el cálculo guardado), entre 1 y 50 (`discount_authority.py`). "Sacá el
  descuento" lo anula. Los automáticos (arquitecta, edificio, cantidad) no cambian.

## Preguntas abiertas
Ver `docs/known-issues.md` (secciones DEUDA-PREGUNTA): refuerzo MDF, plazo de entrega.
