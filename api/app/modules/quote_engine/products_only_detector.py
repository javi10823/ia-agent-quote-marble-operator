"""Detector + parser determinístico para briefs de "solo producto".

**Por qué este módulo existe (PR #427, caso DYSCON 29/04/2026):**

PR #424 implementó el modo `products_only` en el calculator + validator
+ renderers. Pero el flujo upstream del agente (text-parser, dual-read,
context_analysis) sigue corriendo igual para briefs de "solo piletas":
muestra un "Análisis de contexto" con "Frentín: Mencionado" y un
despiece inventado, antes de llegar al cálculo correcto.

Para evitar ese ruido, este módulo provee:

1. **Detector binario** `is_products_only_brief(brief)` — devuelve
   True solo si el brief tiene 3 señales fuertes simultáneas:
   - "solo producto" / "solo piletas" / "solo bachas" (variantes).
   - "sin MO" / "sin mano de obra".
   - Mención de pileta/bacha.

   3 señales requeridas para minimizar falsos positivos. Un brief
   normal de cocina/edificio no las tiene todas a la vez.

2. **Parser determinístico** `parse_products_brief(brief)` — extrae
   `{pileta_sku, pileta_qty, discount_pct, client_name, project}`
   con regex. Devuelve None si no encuentra producto/cantidad.

**Decisiones de diseño:**

- **Determinístico, no LLM.** El review feedback de PR #423 fue
  explícito: "el system prompt es demasiado frágil en conversaciones
  largas". Mismo principio acá — regex que cualquier humano puede
  auditar.
- **3 señales requeridas, no OR.** Si solo aparece "sin MO" en un
  brief de mesadas que pide "sin MO de colocación específica", NO
  queremos disparar. Las 3 juntas son señal de cotización pura de
  producto.
- **Match case-insensitive con word-boundaries** donde aplica, para
  evitar false positives ("frentín" no debería matchear "frente").

**Edge cases conocidos** (NO se manejan, fallan loud o se documentan):

- "solo producto pileta apoyo" → matchea (correcto, es solo producto).
- "solo producto pero con MO de instalación" → NO matchea (falta
  "sin MO" → flujo normal).
- "Pileta Johnson sin MO" sin la frase "solo producto" → NO matchea
  (falta señal "solo *"). Decisión conservadora.
"""
from __future__ import annotations

import re
from typing import Optional

# ─────────────────────────────────────────────────────────────────────
# Detector
# ─────────────────────────────────────────────────────────────────────

# Variantes de "solo producto" que el operador puede escribir.
# Lista deliberadamente cerrada — ampliarla solo si aparece un caso
# real con frases distintas.
_SOLO_PRODUCTO_PHRASES = (
    "solo producto",
    "solo piletas",
    "solo pileta",
    "solo bachas",
    "solo bacha",
    "sólo producto",
    "sólo piletas",
)

# "Sin MO" en sus variantes habituales. Word-boundary en `\bmo\b` para
# no matchear "minimo", "modelo", etc.
_SIN_MO_RE = re.compile(
    r"\bsin\s+(?:m\.?o\.?|mano\s+de\s+obra)\b",
    re.IGNORECASE,
)

# Mención de producto pileta/bacha como palabra suelta.
_HAS_PILETA_RE = re.compile(r"\b(pileta|bacha)\b", re.IGNORECASE)


def is_products_only_brief(brief: str) -> bool:
    """¿El brief indica cotización solo de producto sin MO/instalación?

    Requiere LAS TRES señales simultáneamente:
    1. Frase del tipo "solo producto"/"solo piletas".
    2. "sin MO" / "sin mano de obra".
    3. Mención de "pileta" o "bacha".

    Cualquier 2-de-3 NO dispara — minimiza falsos positivos.

    Returns:
        True si las 3 señales están presentes. False en cualquier otro
        caso, incluido `brief` vacío o None.
    """
    if not brief:
        return False
    b_lower = brief.lower()
    has_solo = any(s in b_lower for s in _SOLO_PRODUCTO_PHRASES)
    if not has_solo:
        return False
    has_no_mo = bool(_SIN_MO_RE.search(brief))
    if not has_no_mo:
        return False
    has_product = bool(_HAS_PILETA_RE.search(brief))
    return has_product


# ─────────────────────────────────────────────────────────────────────
# Parser — extracción de campos del brief
# ─────────────────────────────────────────────────────────────────────

# "Pileta Johnson E50 × 32" / "× 32 unidades" / "x 32u" / "32 unidades"
# Capturamos la cantidad. El × puede ser "×" Unicode o "x" ASCII.
# Para 'Pileta ... × N' o 'N unidades/u' al final.
_QTY_RE_AFTER_PRODUCT = re.compile(
    r"(?:[×x]\s*)(\d+)(?:\s*(?:unidades?|u\b))?",
    re.IGNORECASE,
)
_QTY_RE_BEFORE_PRODUCT = re.compile(
    r"\b(\d+)\s*(?:unidades?|u\b)",
    re.IGNORECASE,
)

# SKU Johnson: matchea letra(s) seguidas de números, opcionalmente
# con "/" y más números (ej: E50, E50/18, LUXOR S171, Q71A).
_JOHNSON_SKU_RE = re.compile(
    r"\b(?:johnson\s+)?([A-Z]{1,5}\d{1,4}[A-Z]?(?:/\d{1,4})?)\b",
    re.IGNORECASE,
)

# Descuento: "descuento 5%", "dto 5%", "5% descuento".
_DISCOUNT_RE = re.compile(
    r"(?:descuento|dto\.?|desc\.?)\s*(\d+(?:[.,]\d+)?)\s*%"
    r"|(\d+(?:[.,]\d+)?)\s*%\s*(?:de\s+)?descuento",
    re.IGNORECASE,
)

# Cliente / Obra: regex con anchor de keywords. PR #429 — caso DYSCON
# real: "CLIENTE: DYSCON S.A. OBRA: Unidad Penal N°8 — Piñero PAGO:
# Contado | ENTREGA: A confirmar". Todo en UNA línea, sin `\n`. El
# regex previo (`(?:\n|$|\|)` como tope) matcheaba hasta el primer
# `|`, agarrando "DYSCON S.A. OBRA: Unidad Penal N°8 — Piñero PAGO:
# Contado" en client_name. Ahora cortamos ante el siguiente label
# conocido (lookahead).
#
# Labels reconocidos como tope: cualquier keyword del header (cliente,
# obra, proyecto, pago, entrega, archivo, material, demora, plazo).
_FIELD_LABEL_LOOKAHEAD = (
    r"(?=\s*(?:cliente|obra|proyecto|pago|entrega|archivo|material|"
    r"demora|plazo|localidad|forma\s+de\s+pago)\s*:|$|\n|\|)"
)

_CLIENT_RE = re.compile(
    r"cliente\s*:\s*(.+?)" + _FIELD_LABEL_LOOKAHEAD,
    re.IGNORECASE | re.DOTALL,
)

_PROJECT_RE = re.compile(
    r"(?:obra|proyecto)\s*:\s*(.+?)" + _FIELD_LABEL_LOOKAHEAD,
    re.IGNORECASE | re.DOTALL,
)


def _extract_qty(brief: str) -> Optional[int]:
    """Extrae la cantidad de productos. Prefiere "× N" / "x N" después
    del producto; cae en "N unidades" si no encuentra el primero.

    Returns: int positivo o None si no encuentra cantidad confiable.
    """
    m = _QTY_RE_AFTER_PRODUCT.search(brief)
    if m:
        try:
            n = int(m.group(1))
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    m = _QTY_RE_BEFORE_PRODUCT.search(brief)
    if m:
        try:
            n = int(m.group(1))
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    return None


def _extract_sku(brief: str) -> Optional[str]:
    """Extrae el SKU de la pileta Johnson del brief.

    Busca un patrón tipo `E50`, `E50/18`, `Q71A`, etc. opcionalmente
    precedido por "Johnson ". Devuelve el SKU canonicalizado (uppercase,
    sin "johnson " prefix).

    NO valida contra el catálogo — eso lo hace `_calculate_quote_products_only`
    via `catalog_lookup`. Acá solo extraemos el string candidato.
    """
    m = _JOHNSON_SKU_RE.search(brief)
    if not m:
        return None
    return m.group(1).upper()


def _extract_discount(brief: str) -> Optional[float]:
    """Extrae el porcentaje de descuento como float (5%, 12.5%, etc.).

    Returns: float positivo o None.
    """
    m = _DISCOUNT_RE.search(brief)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    if not raw:
        return None
    try:
        return float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return None


def _extract_client_project(brief: str) -> tuple[Optional[str], Optional[str]]:
    """Extrae cliente y proyecto del brief, si están en formato
    `CLIENTE: ...` / `OBRA: ...`. Devuelve (client, project) — cualquiera
    puede ser None si no aparece."""
    client = None
    project = None
    m = _CLIENT_RE.search(brief)
    if m:
        client = m.group(1).strip()
    m = _PROJECT_RE.search(brief)
    if m:
        project = m.group(1).strip()
    return client, project


def build_products_only_material_label(sinks: list[dict] | None) -> str:
    """Construye el label que aparece en la columna 'material' del listado
    del dashboard para una quote en modo `products_only`.

    **Por qué existe (PR #428):** el `_po_persist` del short-circuit
    (PR #427) seteaba `material=""` → en el listado se mostraba "—"
    (em-dash) y el operador no podía identificar qué cotización era
    al escanear la lista.

    Formato:
    - 1 sink: ``"<name> × <qty>"`` (ej: "PILETA JOHNSON E50/18 × 32").
    - N sinks: ``"<first.name> × <first.qty> (+<N-1> más)"`` para
      indicar que hay más productos. El operador entra al detalle
      si quiere ver el resto.
    - 0 sinks: string vacío (defensivo — no debería ocurrir si el
      flujo de products_only se activó correctamente).

    NO valida el shape de los sinks — confía en lo que produjo
    `_calculate_quote_products_only` (que ya filtra entradas mal
    formadas).
    """
    if not sinks:
        return ""
    first = sinks[0] if isinstance(sinks[0], dict) else {}
    name = (first.get("name") or "PRODUCTO").strip()
    qty = first.get("quantity") or 1
    label = f"{name} × {qty}"
    extras = len(sinks) - 1
    if extras > 0:
        label += f" (+{extras} más)"
    return label


def resolve_material_label_for_db(calc_result: dict) -> str:
    """Devuelve el string que va en `Quote.material` (columna DB usada
    por el listado del dashboard).

    **Por qué existe (PR #434):** sin este helper, los handlers de
    `calculate_quote` y `generate_documents` hacían
    `quote.material = calc_result.get("material_name")`. Para
    products_only `material_name = ""` → sobrescribía el label
    descriptivo del PR #428 → en el listado se veía "—".

    Reglas:
    - Si `_quote_mode == "products_only"` → label desde sinks
      (mismo helper que usa el short-circuit del PR #427).
    - Si no → `material_name` directo (flujo normal intacto).

    Si el calc_result no tiene `_quote_mode` explícito pero TIENE
    sinks Y NO tiene material_name (caso defensivo: products_only
    persistido viejo sin flag), también usa el label de sinks.
    """
    if calc_result.get("_quote_mode") == "products_only":
        return build_products_only_material_label(calc_result.get("sinks"))
    # Flujo normal: usar material_name directo.
    return calc_result.get("material_name") or ""


def parse_products_brief(brief: str) -> Optional[dict]:
    """Parsea un brief de "solo producto" a un dict listo para
    `calculate_quote`.

    Returns:
        dict con `client_name`, `project`, `pileta_sku`, `pileta_qty`,
        `discount_pct`, `pieces=[]`, `plazo`. None si falta SKU o qty
        (sin esos dos no podemos cotizar).

    NO chequea `is_products_only_brief` adentro — el caller decide
    cuándo invocarlo. Acá solo extraemos campos.
    """
    if not brief:
        return None

    qty = _extract_qty(brief)
    sku = _extract_sku(brief)
    if not qty or not sku:
        return None

    discount = _extract_discount(brief)
    client, project = _extract_client_project(brief)

    return {
        "client_name": client or "",
        "project": project or "",
        "pieces": [],
        "pileta_sku": sku,
        "pileta_qty": qty,
        "discount_pct": discount or 0.0,
        "plazo": "A confirmar",
    }
