import anthropic
import asyncio
import json
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select

from app.core.config import settings
from app.models.quote import Quote, QuoteStatus
from app.modules.agent.tools.catalog_tool import catalog_lookup, catalog_batch_lookup, check_stock, check_architect, get_ai_config
from app.modules.agent.tools.plan_tool import read_plan
from app.modules.agent.tools.document_tool import generate_documents
from app.modules.agent.tools.drive_tool import upload_to_drive
from app.modules.quote_engine.calculator import calculate_quote
from app.modules.agent.tools.validation_tool import validate_despiece

BASE_DIR = Path(__file__).parent.parent.parent.parent

# Materials that MUST have merma
from app.core.company_config import get as _cfg
_SYNTHETIC_MATERIALS = _cfg("materials.sinteticos", ["silestone", "dekton", "neolith", "puraprima", "purastone", "laminatto"])


def _validate_quote_data(qdata: dict) -> tuple[list[str], list[str]]:
    """Pre-flight checklist before PDF generation. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # ── Errors (block generation) ──
    if not qdata.get("client_name"):
        errors.append("Falta nombre del cliente")
    if not qdata.get("material_name"):
        errors.append("Falta material")
    if not qdata.get("delivery_days"):
        # Read default from config.json (editable from the catalog panel)
        try:
            cfg = json.loads((BASE_DIR / "catalog" / "config.json").read_text(encoding="utf-8"))
            qdata["delivery_days"] = cfg.get("delivery_days", {}).get("display", "40 dias desde la toma de medidas")
        except Exception:
            qdata["delivery_days"] = "40 dias desde la toma de medidas"
    if not qdata.get("total_ars") and not qdata.get("total_usd"):
        errors.append("Totales en $0 — verificar cálculo")
    sectors = qdata.get("sectors", [])
    if not sectors or not any(s.get("pieces") for s in sectors):
        errors.append("Sin piezas definidas")
    if not qdata.get("mo_items"):
        errors.append("Sin ítems de mano de obra")

    # ── Warnings (alert but allow) ──
    mat = (qdata.get("material_name") or "").lower()
    merma = qdata.get("merma") or {}

    # Negro Brasil NEVER has merma
    if "negro brasil" in mat and merma.get("aplica"):
        warnings.append("Negro Brasil NUNCA lleva merma — verificar")

    # Synthetic materials SHOULD have merma
    if any(s in mat for s in _SYNTHETIC_MATERIALS) and not merma.get("aplica"):
        warnings.append(f"Material sintético ({qdata.get('material_name')}) debería llevar merma")

    # MO items with $0 price
    for mo in qdata.get("mo_items", []):
        if mo.get("unit_price", 0) == 0 and mo.get("description"):
            warnings.append(f"MO ítem '{mo['description']}' tiene precio $0")

    # Check if pileta was likely requested but missing from MO
    mo_descriptions = " ".join(m.get("description", "").lower() for m in qdata.get("mo_items", []))
    sinks = qdata.get("sinks", [])
    has_pileta_in_quote = (
        "pileta" in mo_descriptions or "pegado" in mo_descriptions
        or "johnson" in mo_descriptions or len(sinks) > 0
    )
    if not has_pileta_in_quote:
        warnings.append("No hay pileta/bacha en el presupuesto — verificar si el operador la pidió")

    return errors, warnings

# ── BUILDING DETECTION ───────────────────────────────────────────────────────

BUILDING_KEYWORDS = [
    "edificio", "edificios", "departamento", "departamentos",
    "unidades", "torre", "torres", "constructora", "consorcio",
    "cantidad:", "cantidad :", "pisos", "obra nueva",
]


def _detect_building(user_message: str) -> bool:
    text = user_message.lower()
    return any(kw in text for kw in BUILDING_KEYWORDS)


# ── EXAMPLE SELECTION ────────────────────────────────────────────────────────

# Feature keywords → tags mapping for example selection
_FEATURE_TAGS = {
    # Material types
    "silestone": "silestone",
    "dekton": "dekton",
    "neolith": "neolith",
    "purastone": "purastone",
    "puraprima": "puraprima",
    "pura prima": "puraprima",
    "laminatto": "laminatto",
    "granito": "granito_importado",
    "negro brasil": "granito_importado",
    "gris mara": "granito_nacional",
    "negro boreal": "granito_nacional",
    # Work features
    "isla": "isla",
    "anafe": "anafe",
    "hornalla": "anafe",
    "pileta": "pileta_empotrada",
    "bacha": "pileta_empotrada",
    "apoyo": "pileta_apoyo",
    "johnson": "pileta_johnson",
    "alzada": "alzas",
    "alza": "alzas",
    "frentin": "faldon",
    "faldón": "faldon",
    "faldon": "faldon",
    "corte 45": "corte45",
    "inglete": "corte45",
    "zócalo": "zocalo",
    "zocalo": "zocalo",
    "toma": "tomas",
    "regrueso": "regrueso",
    "pulido": "pulido",
    "descuento": "descuento",
    "arquitecta": "descuento_arquitecta",
    "sobrante": "sobrante",
    # Context
    "edificio": "building",
    "departamento": "building",
    "baño": "pileta_apoyo",
    "toilette": "pileta_apoyo",
}


def _extract_features(user_message: str, is_building: bool) -> set:
    """Extract feature tags from user message for example matching."""
    text = user_message.lower()
    tags = set()
    if is_building:
        tags.add("building")
    else:
        tags.add("residential")
    for keyword, tag in _FEATURE_TAGS.items():
        if keyword in text:
            tags.add(tag)
    return tags


def _load_example_index() -> list:
    """Load examples/index.json once."""
    index_path = BASE_DIR / "examples" / "index.json"
    if not index_path.exists():
        return []
    import json
    with open(index_path) as f:
        return json.load(f)


_EXAMPLE_INDEX = _load_example_index()

# Pre-build a map of example ID → file path to avoid glob() on every request
_EXAMPLE_FILE_MAP: dict[str, Path] = {}
_examples_dir = BASE_DIR / "examples"
if _examples_dir.exists():
    for md_file in _examples_dir.glob("*.md"):
        _EXAMPLE_FILE_MAP[md_file.stem.split("-")[0] + "-" + md_file.stem.split("-")[1] if "-" in md_file.stem else md_file.stem] = md_file
    # Rebuild with proper ID matching from index
    _EXAMPLE_FILE_MAP.clear()
    for md_file in _examples_dir.glob("*.md"):
        for entry in _EXAMPLE_INDEX:
            if md_file.name.startswith(entry["id"]):
                _EXAMPLE_FILE_MAP[entry["id"]] = md_file
                break


# Examples already included in the cached stable block — skip them in dynamic selection
_CACHED_EXAMPLE_IDS = {"quote-013", "quote-003", "quote-004", "quote-010", "quote-030"}


def select_examples(user_message: str, is_building: bool, max_examples: int = None) -> list:
    if max_examples is None:
        max_examples = get_ai_config().get("max_examples", 1)
    """
    Select the most relevant examples based on tag overlap with the current case.
    Skips examples already in the cached stable block.
    Returns list of example file paths (sorted by relevance, most relevant first).
    """
    features = _extract_features(user_message, is_building)
    examples_dir = BASE_DIR / "examples"

    # Score each example by tag overlap — skip cached ones
    scored = []
    for entry in _EXAMPLE_INDEX:
        if entry["id"] in _CACHED_EXAMPLE_IDS:
            continue  # Already in stable cache, don't pay twice
        entry_tags = set(entry.get("tags", []))
        overlap = len(features & entry_tags)
        # Bonus: exact material match
        material = entry.get("material", "").lower()
        if material and material in user_message.lower():
            overlap += 3
        scored.append((overlap, entry["id"], entry))

    # Sort by score descending, then by ID for stability
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Pick top N, ensuring diversity (not all same material type)
    selected = []
    seen_materials = set()
    for score, eid, entry in scored:
        if len(selected) >= max_examples:
            break
        mat = entry.get("material", "")
        if len(selected) < 1 or mat not in seen_materials:
            selected.append(eid)
            seen_materials.add(mat)

    # Resolve to file paths using pre-built map (no filesystem glob)
    paths = []
    for eid in selected:
        if eid in _EXAMPLE_FILE_MAP:
            paths.append(_EXAMPLE_FILE_MAP[eid])

    logging.info(f"Example selection: features={features}, selected={selected}")
    return paths


# ── EXPLICIT REQUIREMENT DETECTION ────────────────────────────────────────────
# Scans all user messages for explicit requirements that MUST appear in the quote.
# Returns a reminder block injected at the END of the system prompt (recency bias).

_REQUIREMENT_PATTERNS: list[tuple[list[str], str, str]] = [
    # (keywords, requirement_id, human_label)
    (["bacha", "pileta", "sink"], "pileta", "PILETA/BACHA — el operador pidió cotizar pileta. DEBE aparecer en el presupuesto. Si no se definió tipo, presupuestar Johnson por defecto."),
    (["anafe", "hornalla"], "anafe", "ANAFE — el operador mencionó anafe. Incluir agujero de anafe en MO."),
    (["zócalo", "zocalo"], "zocalo", "ZÓCALO — el operador mencionó zócalo. Incluir en piezas y MO."),
    (["frentín", "frentin"], "frentin", "FRENTÍN — el operador mencionó frentín. Incluir como pieza (suma m²) + FALDON/CORTE45 en MO."),
    (["regrueso"], "regrueso", "REGRUESO — el operador mencionó regrueso. Incluir REGRUESO por ml en MO."),
    (["pulido"], "pulido", "PULIDO — el operador mencionó pulido de cantos. Incluir PUL en MO."),
    (["colocación", "colocacion", "con colocacion", "instalación", "instalacion"], "colocacion", "COLOCACIÓN — el operador pidió colocación. Incluir en MO."),
]


def _build_requirement_reminder(user_message: str, conversation_history: list | None) -> str | None:
    """Scan all user messages and build a reminder of explicit requirements."""
    # Collect all user text from conversation
    all_user_text = user_message.lower()
    if conversation_history:
        for msg in conversation_history:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    all_user_text += " " + content.lower()
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            all_user_text += " " + block.get("text", "").lower()

    # Detect requirements
    detected = []
    for keywords, req_id, label in _REQUIREMENT_PATTERNS:
        if any(kw in all_user_text for kw in keywords):
            detected.append(label)

    if not detected:
        return None

    lines = "\n".join(f"- {d}" for d in detected)
    return (
        f"\n\n⚠️ RECORDATORIO — REQUERIMIENTOS EXPLÍCITOS DEL OPERADOR:\n"
        f"Los siguientes requerimientos fueron mencionados explícitamente en la conversación. "
        f"TODOS deben estar reflejados en el presupuesto. NO omitir ninguno.\n\n"
        f"{lines}\n\n"
        f"Si alguno de estos no está incluido en tu cálculo actual, DETENETE y agregalo antes de continuar."
    )




# ── SYSTEM PROMPT CACHE ───────────────────────────────────────────────────────
# Stable text (CONTEXT.md + core rules) doesn't change between requests.
# Cache in memory to avoid 6+ disk reads per request.
_stable_text_cache: str | None = None
_conditional_file_cache: dict[str, str] = {}


def _get_stable_text() -> str:
    global _stable_text_cache
    if _stable_text_cache is not None:
        return _stable_text_cache

    context = (BASE_DIR / "CONTEXT.md").read_text(encoding="utf-8")
    rules_dir = BASE_DIR / "rules"
    core_files = [
        "calculation-formulas.md",
        "commercial-conditions.md",
        "materials-guide.md",
        "pricing-variables.md",
        "quote-process-general.md",
    ]
    core_rules = []
    for name in core_files:
        path = rules_dir / name
        if path.exists():
            core_rules.append(f"## {path.stem}\n\n{path.read_text(encoding='utf-8')}")

    # OPT-01: Include top 5 most universal examples in the cached block
    # These cover ~80% of cases and pay 10% price when cached vs full price as conditional
    core_rules.append(
        "## ⛔ NOTA SOBRE LOS EJEMPLOS ⛔\n\n"
        "Los ejemplos que siguen muestran SOLO el formato de salida correcto (tablas, estructura, orden de secciones). "
        "NO muestran el flujo de confirmación. **El flujo de 3 pasos de la REGLA #1 SIEMPRE aplica** — "
        "nunca calcular todo en un solo mensaje como muestran estos ejemplos. "
        "Primero piezas + m² → esperar confirmación → después precios + MO → esperar confirmación → después generar docs."
    )
    _CACHED_EXAMPLES = ["quote-013", "quote-003", "quote-004", "quote-010", "quote-030"]
    examples_dir = BASE_DIR / "examples"
    for eid in _CACHED_EXAMPLES:
        matches = list(examples_dir.glob(f"{eid}*.md"))
        if matches:
            core_rules.append(f"## Ejemplo: {matches[0].stem}\n\n{matches[0].read_text(encoding='utf-8')}")

    # Inject config.json values so Valentina has the real defaults (not hardcoded)
    try:
        import json as _json
        _config = _json.loads((BASE_DIR / "catalog" / "config.json").read_text(encoding="utf-8"))
        _delivery = _config.get("delivery_days", {}).get("display", "40 dias")
        config_block = f"## Valores actuales de config.json\n\n- **Plazo de entrega default:** {_delivery}\n- SIEMPRE usar este valor cuando el operador no especifica plazo. NUNCA inventar otro."
        core_rules.append(config_block)
    except Exception:
        pass

    _stable_text_cache = "\n\n---\n\n".join([context] + core_rules)
    logging.info(f"System prompt stable text cached ({len(_stable_text_cache)} chars, includes 5 core examples)")
    return _stable_text_cache


def _read_cached_file(path) -> str:
    """Read file with in-memory cache."""
    key = str(path)
    if key not in _conditional_file_cache:
        _conditional_file_cache[key] = path.read_text(encoding="utf-8")
    return _conditional_file_cache[key]


def build_system_prompt(has_plan: bool = False, is_building: bool = False, user_message: str = "", conversation_history: list | None = None) -> list:
    """
    Build system prompt as a list of content blocks with cache_control.
    Stable core content is cached in memory + Anthropic prompt cache (5 min TTL).
    """
    stable_text = _get_stable_text()
    rules_dir = BASE_DIR / "rules"

    # Conditional content — loaded based on context
    conditional_parts = []

    if is_building:
        bldg_path = rules_dir / "quote-process-buildings.md"
        if bldg_path.exists():
            conditional_parts.append(f"## {bldg_path.stem}\n\n{_read_cached_file(bldg_path)}")

    if has_plan:
        plan_path = rules_dir / "plan-reading.md"
        if plan_path.exists():
            conditional_parts.append(f"## {plan_path.stem}\n\n{_read_cached_file(plan_path)}")

    # Examples — select 2 most relevant (5 core examples already in stable block)
    example_paths = select_examples(user_message, is_building, max_examples=2)
    for ep in example_paths:
        conditional_parts.append(f"## Ejemplo: {ep.stem}\n\n{_read_cached_file(ep)}")

    # Build system content blocks with cache_control on stable block
    blocks = [
        {
            "type": "text",
            "text": stable_text,
            "cache_control": {"type": "ephemeral"},
        },
    ]

    if conditional_parts:
        conditional_text = "\n\n---\n\n".join(conditional_parts)
        blocks.append({
            "type": "text",
            "text": conditional_text,
        })

    # ── Requirement reminder — scan ALL user messages for explicit requests ──
    reminder = _build_requirement_reminder(user_message, conversation_history)
    if reminder:
        blocks.append({"type": "text", "text": reminder})

    stable_chars = len(stable_text)
    cond_chars = sum(len(p) for p in conditional_parts)
    logging.info(
        f"System prompt blocks: {len(blocks)}, "
        f"stable chars: {stable_chars}, "
        f"conditional chars: {cond_chars}, "
        f"total chars: {stable_chars + cond_chars}"
    )
    return blocks


# ── TOOL DEFINITIONS ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "catalog_lookup",
        "description": "Busca el precio de un material, SKU de MO, pileta o zona de flete en los catálogos JSON. Siempre usar antes de cotizar cualquier ítem.",
        "input_schema": {
            "type": "object",
            "properties": {
                "catalog": {
                    "type": "string",
                    "description": "Nombre del catálogo: materials-silestone, materials-granito-importado, materials-granito-nacional, materials-marmol, materials-dekton, materials-neolith, materials-purastone, materials-puraprima, materials-laminatto, labor, delivery-zones, sinks, architects",
                },
                "sku": {
                    "type": "string",
                    "description": "SKU exacto del ítem a buscar (ej: SILESTONENORTE, PEGADOPILETA, ENVIOROS)",
                },
            },
            "required": ["catalog", "sku"],
        },
    },
    {
        "name": "catalog_batch_lookup",
        "description": "Busca MÚLTIPLES SKUs en una sola llamada. PREFERIR esta tool sobre catalog_lookup cuando necesitás buscar 2 o más precios (material, MO, flete, pileta, etc.). Reduce tiempos drásticamente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "description": "Lista de búsquedas. Cada una con catalog y sku.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "catalog": {"type": "string", "description": "Nombre del catálogo"},
                            "sku": {"type": "string", "description": "SKU a buscar"},
                        },
                        "required": ["catalog", "sku"],
                    },
                },
            },
            "required": ["queries"],
        },
    },
    {
        "name": "check_stock",
        "description": "Verifica si hay retazos disponibles en stock para un material dado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_sku": {"type": "string", "description": "SKU del material a verificar"},
            },
            "required": ["material_sku"],
        },
    },
    {
        "name": "check_architect",
        "description": "Verifica si un cliente es arquitecta registrada con descuento. SIEMPRE llamar cuando se conoce el nombre del cliente, ANTES de calcular. Retorna si hay match exacto, parcial, o ninguno.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Nombre del cliente a verificar"},
            },
            "required": ["client_name"],
        },
    },
    {
        "name": "read_plan",
        "description": "Rasteriza un plano a 300 DPI con crop por pieza. OBLIGATORIO cuando el plano tiene 2+ piezas en boxes/cuadros separados (ej: múltiples solías, múltiples mesadas). Cropear CADA pieza individualmente para leer sus medidas sin mezclar con las de otras piezas. También útil para leer texto pequeño o cotas que no se distinguen bien en la vista general.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Nombre del archivo del plano"},
                "crop_instructions": {
                    "type": "array",
                    "description": "Lista de áreas a recortar. Cada item: {label, x1, y1, x2, y2}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "x1": {"type": "integer"},
                            "y1": {"type": "integer"},
                            "x2": {"type": "integer"},
                            "y2": {"type": "integer"},
                        },
                    },
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": "generate_documents",
        "description": "Genera PDF y Excel para uno o varios materiales. Si hay varios materiales, el sistema crea automáticamente un presupuesto separado por cada material. Llamar UNA SOLA VEZ con todos los materiales en el array 'quotes'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quotes": {
                    "type": "array",
                    "description": "Array de presupuestos a generar. Uno por material. El primero usa el quote_id actual, los demás crean quotes nuevos automáticamente.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "client_name": {"type": "string"},
                            "project": {"type": "string"},
                            "date": {"type": "string"},
                            "delivery_days": {"type": "string"},
                            "material_name": {"type": "string"},
                            "material_m2": {"type": "number"},
                            "material_price_unit": {"type": "number"},
                            "material_currency": {"type": "string", "enum": ["USD", "ARS"]},
                            "discount_pct": {"type": "number"},
                            "sectors": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "pieces": {"type": "array", "items": {"type": "string"}},
                                    },
                                },
                            },
                            "sinks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "quantity": {"type": "integer"},
                                        "unit_price": {"type": "number"},
                                    },
                                },
                            },
                            "mo_items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "description": {"type": "string"},
                                        "quantity": {"type": "number"},
                                        "unit_price": {"type": "number"},
                                        "total": {"type": "number", "description": "quantity × unit_price"},
                                    },
                                },
                            },
                            "total_ars": {"type": "number"},
                            "total_usd": {"type": "number"},
                        },
                        "required": ["client_name", "material_name"],
                    },
                },
            },
            "required": ["quotes"],
        },
    },
    {
        "name": "update_quote",
        "description": "Actualiza datos del presupuesto en la base de datos. Usar cuando el operador pide corregir nombre del cliente, proyecto, material u otros datos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quote_id": {"type": "string"},
                "updates": {
                    "type": "object",
                    "description": "Campos a actualizar. Solo incluir los que cambian.",
                    "properties": {
                        "client_name": {"type": "string", "description": "Nombre del cliente"},
                        "project": {"type": "string", "description": "Nombre del proyecto"},
                        "material": {"type": "string", "description": "Material del presupuesto"},
                        "total_ars": {"type": "number", "description": "Total en pesos"},
                        "total_usd": {"type": "number", "description": "Total en dólares"},
                        "status": {"type": "string", "enum": ["draft", "validated", "sent"], "description": "Estado del presupuesto"},
                    },
                },
            },
            "required": ["quote_id", "updates"],
        },
    },
    {
        "name": "calculate_quote",
        "description": "Calcula m², merma, material total, y mano de obra de forma determinística. SIEMPRE usar para cálculos numéricos — NUNCA calcular inline. Devuelve piece_details, mo_items con base_price (traceability IVA), totales ARS/USD, y merma. Usar estos valores exactos en el preview y pasarlos a generate_documents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Nombre del cliente"},
                "project": {"type": "string", "description": "Nombre del proyecto"},
                "material": {"type": "string", "description": "Nombre del material (ej: Pura Stone Blanco Nube)"},
                "pieces": {
                    "type": "array",
                    "description": "Lista de piezas con medidas en metros",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string", "description": "Nombre de la pieza (ej: Mesada principal)"},
                            "largo": {"type": "number", "description": "Largo en metros"},
                            "prof": {"type": "number", "description": "Profundidad en metros (para mesadas, zócalos horizontales)"},
                            "alto": {"type": "number", "description": "Alto en metros (para revestimientos, patas)"},
                        },
                        "required": ["description", "largo"],
                    },
                },
                "localidad": {"type": "string", "description": "Zona de flete (ej: Rosario)"},
                "colocacion": {"type": "boolean", "description": "Si lleva colocación (default: true). Edificios: siempre false."},
                "is_edificio": {"type": "boolean", "description": "true si es un edificio/concesionario. Activa: flete ceil(piezas/8), MO ÷1.05, sin colocación."},
                "pileta": {
                    "type": "string",
                    "enum": ["empotrada_cliente", "empotrada_johnson", "apoyo"],
                    "description": "Tipo de pileta. empotrada_johnson = incluir producto Johnson + MO. empotrada_cliente = solo MO. Omitir si no hay pileta.",
                },
                "pileta_qty": {"type": "integer", "description": "Cantidad de piletas (default: 1). Para edificios, contar cuántas mesadas llevan pileta."},
                "pileta_sku": {
                    "type": "string",
                    "description": "SKU del modelo de pileta en sinks.json (ej: QUADRAQ71A). Solo para empotrada_johnson.",
                },
                "anafe": {"type": "boolean", "description": "SOLO true si hay evidencia de anafe en plano o enunciado."},
                "frentin": {"type": "boolean", "description": "Si lleva frentín/faldón."},
                "frentin_ml": {"type": "number", "description": "Metros lineales totales de frentín/faldón. Si no se especifica, se auto-calcula sumando los largos de las piezas que tengan 'faldón' o 'frentín' en su descripción."},
                "inglete": {"type": "boolean", "description": "Si el frentín lleva corte a 45° (inglete). Si true: MO = armado frentín (ml) + corte 45 (ml×2). Si false: solo armado frentín (ml)."},
                "pulido": {"type": "boolean", "description": "Si lleva pulido de cantos"},
                "plazo": {"type": "string", "description": "Plazo de entrega"},
                "discount_pct": {"type": "number", "description": "Porcentaje de descuento (0-100)"},
            },
            "required": ["client_name", "material", "pieces", "localidad", "plazo"],
        },
    },
    {
        "name": "patch_quote_mo",
        "description": "Modifica la mano de obra de un presupuesto EXISTENTE sin recalcular todo. Usar en modo patch cuando el operador pide agregar o quitar ítems de MO (flete, colocación, etc.) sin cambiar material ni piezas. MÁS SEGURO que calculate_quote para cambios simples de MO.",
        "input_schema": {
            "type": "object",
            "properties": {
                "remove_items": {
                    "type": "array",
                    "description": "Palabras clave de ítems de MO a ELIMINAR (ej: ['flete', 'colocación']). Se busca por coincidencia parcial en la descripción.",
                    "items": {"type": "string"},
                },
                "add_colocacion": {"type": "boolean", "description": "Agregar colocación (calcula automáticamente según m² y material)"},
                "add_flete": {"type": "string", "description": "Agregar flete para esta localidad (ej: 'Rosario'). Busca precio en catálogo."},
            },
            "required": [],
        },
    },
]


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _extract_quote_info(user_message: str) -> dict:
    """Extract client name and material from user message for early DB update."""
    import re
    info = {}

    # Try to find client name after "cliente" keyword (case insensitive)
    # Cut at business keywords that signal the name ended
    _DELIMITERS = (
        r"\s*,|\s+con\s|\s+en\s|\s+lleva|\s+sin\s"
        r"|\s+proyecto\s|\s+presupuesto\s|\s+mesada\s|\s+cocina\s"
        r"|\s+ba[ñn]o\s|\s+departamento\s|\s+edificio\s|\s+cotizar\s"
        r"|\s+medidas\s|\s+colocacion\s|\s+colocación\s|\s+z[oó]calo\s"
        r"|\s+anafe\s|\s+bacha\s|\s+pileta\s|\s+flete\s|\s+demora\s"
        r"|\s+plazo\s|\s+material\s|\s+isla\s|\s+lavadero\s|\s+vanitory\s"
        r"|\s+revestimiento\s|\s+frentin\s|\s+frent[ií]n\s|\s+regrueso\s"
        r"|\s+pulido\s|\s+descuento\s|\s+consultar\s"
    )
    match = re.search(
        rf"(?:cliente|clienta)[:\s]+(.+?)(?:{_DELIMITERS}|\n|$)",
        user_message, re.IGNORECASE,
    )
    if match:
        name = match.group(1).strip()
        info["client_name"] = name.title()

    # Try to find project name
    proj_match = re.search(
        r"(?:proyecto)[:\s]+(.+?)(?:\n|$)",
        user_message, re.IGNORECASE,
    )
    if proj_match:
        info["project"] = proj_match.group(1).strip().title()

    # Try to find material name
    material_keywords = [
        "silestone", "dekton", "neolith", "purastone", "puraprima",
        "laminatto", "negro brasil", "blanco norte", "granito",
        "mármol", "marmol",
    ]
    msg_lower = user_message.lower()
    for kw in material_keywords:
        if kw in msg_lower:
            # Find the full material name around the keyword
            idx = msg_lower.index(kw)
            # Grab surrounding words for context
            start = max(0, user_message.rfind(" ", 0, max(0, idx - 1)) + 1)
            end = user_message.find(",", idx)
            if end == -1:
                end = user_message.find(" con ", idx)
            if end == -1:
                end = min(len(user_message), idx + 30)
            info["material"] = user_message[start:end].strip()
            break

    return info


def _serialize_content(content) -> list:
    """Convert Anthropic SDK content blocks to JSON-serializable dicts."""
    result = []
    for block in content:
        if hasattr(block, "model_dump"):
            result.append(block.model_dump())
        elif isinstance(block, dict):
            result.append(block)
        else:
            result.append({"type": "text", "text": str(block)})
    return result


# ── TOOL RESULT COMPACTION ────────────────────────────────────────────────────
# After the agent processes a tool result, we don't need the full JSON in
# subsequent iterations. Compact it to save ~3,000-5,000 tokens per quote.

_COMPACT_KEYS = {
    "calculate_quote": ["ok", "material_name", "material_m2", "material_total", "material_currency",
                        "total_ars", "total_usd", "discount_pct", "merma"],
    "catalog_batch_lookup": None,  # Already compact, keep as-is
    "generate_documents": ["ok", "generated", "results"],
}


def _compact_tool_results(assistant_messages: list) -> list:
    """Compact old tool results in assistant_messages to reduce context size.
    Only compacts messages before the last assistant+user pair (keeps the most recent full)."""
    if len(assistant_messages) < 4:
        return assistant_messages  # Not enough history to compact

    compacted = []
    # Keep last 2 messages (latest assistant response + tool results) intact
    to_compact = assistant_messages[:-2]
    to_keep = assistant_messages[-2:]

    for msg in to_compact:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            new_content = []
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    try:
                        result = json.loads(block["content"])
                        # Compact known large results
                        compacted_result = _compact_single_result(result)
                        new_content.append({
                            **block,
                            "content": json.dumps(compacted_result),
                        })
                    except (json.JSONDecodeError, TypeError):
                        new_content.append(block)
                else:
                    new_content.append(block)
            compacted.append({**msg, "content": new_content})
        else:
            compacted.append(msg)

    return compacted + to_keep


def _compact_single_result(result: dict) -> dict:
    """Reduce a tool result to essential fields."""
    if not isinstance(result, dict):
        return result

    # For calculate_quote results (largest: ~2000 tokens)
    if result.get("ok") and result.get("piece_details"):
        return {
            "ok": True,
            "_compacted": True,
            "material_name": result.get("material_name"),
            "material_m2": result.get("material_m2"),
            "material_total": result.get("material_total"),
            "material_currency": result.get("material_currency"),
            "total_ars": result.get("total_ars"),
            "total_usd": result.get("total_usd"),
            "discount_pct": result.get("discount_pct"),
            "mo_count": len(result.get("mo_items", [])),
            "sinks_count": len(result.get("sinks", [])),
        }

    # For batch lookup results (moderate)
    if result.get("results") and result.get("count"):
        compact = {"count": result["count"], "results": {}}
        for k, v in result["results"].items():
            if isinstance(v, dict) and v.get("found"):
                compact["results"][k] = {
                    "found": True,
                    "sku": v.get("sku"),
                    "name": v.get("name", "")[:30],
                    "price": v.get("price_usd") or v.get("price_ars"),
                    "currency": v.get("currency"),
                }
            else:
                compact["results"][k] = v
        return compact

    return result


# ── RETRY CONFIG ─────────────────────────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAYS = [5, 10, 15]
MAX_ITERATIONS = 15  # Safety limit — prevent infinite tool loops


# ── AGENT SERVICE ─────────────────────────────────────────────────────────────

class AgentService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            max_retries=0,  # Disable SDK internal retry — we handle it ourselves
            default_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )

    async def stream_chat(
        self,
        quote_id: str,
        messages: list,
        user_message: str,
        plan_bytes: Optional[bytes],
        plan_filename: Optional[str],
        extra_files: Optional[list] = None,
        db: AsyncSession = None,
    ) -> AsyncGenerator[dict, None]:

        # Build system prompt per request with contextual loading
        has_plan = plan_bytes is not None and plan_filename is not None
        is_building = _detect_building(user_message)
        system_prompt = build_system_prompt(has_plan=has_plan, is_building=is_building, user_message=user_message, conversation_history=messages)

        # Build user message content
        content = []
        if plan_bytes and plan_filename:
            ext = Path(plan_filename).suffix.lower()
            if ext == ".pdf":
                content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(plan_bytes).decode(),
                    },
                })
            else:
                media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/webp" if ext == ".webp" else "image/png"
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(plan_bytes).decode(),
                    },
                })
                # Also send a 90° rotated version to catch margin text (configurable)
                if get_ai_config().get("rotate_plan_images", True):
                    try:
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(plan_bytes))
                        rotated = img.rotate(90, expand=True)
                        buf = io.BytesIO()
                        rotated.save(buf, format="JPEG", quality=85)
                        content.append({"type": "text", "text": "El siguiente es el MISMO plano rotado 90° para facilitar la lectura del texto en los márgenes laterales. Leé el texto de esta versión rotada (material, zócalo, frentín, etc.):"})
                        content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.b64encode(buf.getvalue()).decode(),
                            },
                        })
                        logging.info(f"Added 90° rotated version of plan for margin text reading")
                    except Exception as e:
                        logging.warning(f"Could not create rotated plan version: {e}")
        # Attach extra files (additional images sent by operator)
        # Each image gets a 90° rotated version to catch vertical cotas
        if extra_files:
            from PIL import Image
            import io
            for file_bytes, filename in extra_files:
                ext_f = Path(filename).suffix.lower()
                if ext_f == ".pdf":
                    content.append({
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(file_bytes).decode()},
                    })
                else:
                    mt = "image/jpeg" if ext_f in [".jpg", ".jpeg"] else "image/webp" if ext_f == ".webp" else "image/png"
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(file_bytes).decode()},
                    })
                    # Add 90° rotated version for vertical cotas
                    try:
                        img = Image.open(io.BytesIO(file_bytes))
                        rotated = img.rotate(90, expand=True)
                        buf = io.BytesIO()
                        rotated.save(buf, format="JPEG", quality=85)
                        content.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()},
                        })
                    except Exception:
                        pass
            content.append({"type": "text", "text": f"Las imágenes de arriba incluyen cada pieza en orientación original Y rotada 90°. Si una cota no se lee bien en una versión, leerla de la otra. Comparar ambas versiones para cada pieza."})
            logging.info(f"Attached {len(extra_files)} extra files + rotated versions to message")

        # Always include a text block — Anthropic rejects empty text content blocks
        text = user_message.strip() if user_message.strip() else "(adjunto plano)"
        content.append({"type": "text", "text": text})

        # Sanitize history — remove any empty text blocks from prior messages
        clean_messages = []
        for msg in messages:
            mc = msg.get("content", "")
            if isinstance(mc, list):
                filtered = [b for b in mc if not (isinstance(b, dict) and b.get("type") == "text" and not (b.get("text") or "").strip())]
                if filtered:
                    clean_messages.append({**msg, "content": filtered})
                else:
                    clean_messages.append({**msg, "content": [{"type": "text", "text": "."}]})
            elif isinstance(mc, str) and not mc.strip():
                clean_messages.append({**msg, "content": "."})
            else:
                clean_messages.append(msg)

        # Save clean content before injection
        import copy
        clean_user_content = copy.deepcopy(content)

        # Inject minimal patch mode context if quote already has a breakdown
        try:
            _ctx_q = await db.execute(select(Quote).where(Quote.id == quote_id))
            _ctx_quote = _ctx_q.scalar_one_or_none()
            if _ctx_quote and _ctx_quote.quote_breakdown:
                bd = _ctx_quote.quote_breakdown
                patch_hint = f"\n[SISTEMA — MODO PATCH ACTIVO]\nEste presupuesto YA tiene un breakdown calculado (material: {bd.get('material_name')}, total_ars: {bd.get('total_ars')}, total_usd: {bd.get('total_usd')}). Estás en MODO PATCH. Usá patch_quote_mo para cambios de MO (flete, colocación). NO volver a preguntar datos ni piezas. NO usar calculate_quote para cambios de MO."
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            block["text"] = block["text"] + patch_hint
                            break
        except Exception:
            pass

        # If SINGLE plan attached, inject instruction to request separate images when multiple pieces detected
        # If multiple files attached (2+), they ARE the separate captures — process them directly
        total_files = 1 + len(extra_files or []) if has_plan else 0
        if has_plan and total_files == 1:
            multi_hint = "\n\n[SISTEMA — INSTRUCCIÓN OBLIGATORIA SOBRE PLANOS]\n⛔ ANTES de leer medidas, contá cuántas piezas hay en cuadros/boxes separados.\n⛔ Si hay 3 o más piezas en cuadros separados: PARAR. NO leer medidas. Pedir al operador capturas individuales de cada cuadro.\n⛔ Decir EXACTAMENTE: 'Veo [N] piezas en cuadros separados. Para leer bien las medidas, necesito que me mandes una captura de cada cuadro por separado.'\n⛔ NO usar read_plan, NO intentar leer del plano general, NO calcular. Solo pedir las capturas y esperar.\n⛔ Si son 1-2 piezas, podés leerlas directo."
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["text"] = block["text"] + multi_hint
                        break
        elif has_plan and total_files > 1:
            multi_read_hint = f"\n\n[SISTEMA — CAPTURAS INDIVIDUALES RECIBIDAS]\nEl operador mandó {total_files} imágenes separadas. Cada imagen es UNA pieza/cuadro individual. Leé las medidas de CADA imagen por separado. Compará la versión original y la rotada para cada pieza. NO pidas más capturas — ya las tenés todas."
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["text"] = block["text"] + multi_read_hint
                        break

        # Append user message to history (injected for Claude, clean for DB)
        new_messages = clean_messages + [{"role": "user", "content": content}]
        db_messages = clean_messages + [{"role": "user", "content": clean_user_content}]

        # Agentic loop with tool use
        assistant_messages = []
        # OPT-05: Per-quote cost tracking
        _total_input_tokens = 0
        _total_output_tokens = 0
        _total_cache_read = 0
        _total_cache_write = 0
        _loop_iterations = 0
        yield {"type": "action", "content": "Leyendo catálogos y calculando..."}

        while True:
            if _loop_iterations >= MAX_ITERATIONS:
                logging.error(f"Agent exceeded MAX_ITERATIONS ({MAX_ITERATIONS}) for quote {quote_id}")
                yield {"type": "action", "content": f"⚠️ Se alcanzó el límite de iteraciones ({MAX_ITERATIONS}). Intentá con un enunciado más simple."}
                break

            full_text = ""
            tool_uses = []

            # Model selection:
            # - Opus: first iteration with plan (accurate measurement reading)
            # - Sonnet: everything else (prices, MO, docs)
            OPUS_MODEL = "claude-opus-4-20250514"
            ai_cfg = get_ai_config()
            use_opus = has_plan and _loop_iterations == 0 and ai_cfg.get("use_opus_for_plans", True)
            current_model = OPUS_MODEL if use_opus else settings.ANTHROPIC_MODEL
            if use_opus:
                logging.info(f"Using Opus for plan reading (iteration {_loop_iterations + 1})")

            # Strip plan images from messages after first iteration (saves ~50K tokens)
            if _loop_iterations > 0 and has_plan:
                msgs_for_api = []
                for msg in new_messages:
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        filtered = [b for b in content if not (isinstance(b, dict) and b.get("type") in ("image", "document"))]
                        if not filtered:
                            filtered = [{"type": "text", "text": "(plano ya leído en iteración 1)"}]
                        msgs_for_api.append({**msg, "content": filtered})
                    else:
                        msgs_for_api.append(msg)
            else:
                msgs_for_api = new_messages

            # Retry loop for rate limit errors
            for attempt in range(MAX_RETRIES + 1):
                try:
                    async with self.client.messages.stream(
                        model=current_model,
                        max_tokens=8096,
                        system=system_prompt,
                        messages=msgs_for_api + _compact_tool_results(assistant_messages),
                        tools=TOOLS,
                    ) as stream:
                        async for event in stream:
                            if hasattr(event, "type"):
                                if event.type == "content_block_delta":
                                    if hasattr(event.delta, "text"):
                                        full_text += event.delta.text
                                        yield {"type": "text", "content": event.delta.text}
                                elif event.type == "content_block_start":
                                    if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                                        tool_uses.append({
                                            "id": event.content_block.id,
                                            "name": event.content_block.name,
                                            "input": {},
                                        })

                        final_message = await stream.get_final_message()

                    # Log and accumulate token usage
                    _loop_iterations += 1
                    if hasattr(final_message, "usage"):
                        usage = final_message.usage
                        cache_read = getattr(usage, "cache_read_input_tokens", 0)
                        cache_create = getattr(usage, "cache_creation_input_tokens", 0)
                        _total_input_tokens += usage.input_tokens
                        _total_output_tokens += usage.output_tokens
                        _total_cache_read += cache_read
                        _total_cache_write += cache_create
                        logging.info(
                            f"Token usage [iter {_loop_iterations}] — input: {usage.input_tokens}, "
                            f"cache_read: {cache_read}, "
                            f"cache_create: {cache_create}, "
                            f"output: {usage.output_tokens}"
                        )

                    break  # Success — exit retry loop

                except anthropic.RateLimitError:
                    if attempt == MAX_RETRIES:
                        logging.error("Rate limit exceeded after all retries")
                        yield {"type": "action", "content": "⚠️ Servicio temporalmente no disponible. Intentá de nuevo en un minuto."}
                        yield {"type": "done", "content": ""}
                        return
                    delay = RETRY_DELAYS[attempt]
                    logging.warning(f"Rate limit hit, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    yield {"type": "action", "content": f"⏳ Esperando disponibilidad... ({delay}s)"}
                    for _ in range(delay):
                        await asyncio.sleep(1)
                        yield {"type": "ping", "content": ""}

                except anthropic.APIStatusError as e:
                    is_overloaded = e.status_code == 529 or "overloaded" in str(e).lower()
                    if is_overloaded:
                        if attempt == MAX_RETRIES:
                            yield {"type": "action", "content": "⚠️ Servicio sobrecargado. Intentá de nuevo en unos minutos."}
                            yield {"type": "done", "content": ""}
                            return
                        delay = RETRY_DELAYS[attempt]
                        logging.warning(f"API overloaded, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
                        yield {"type": "action", "content": f"⏳ Servicio ocupado, reintentando... ({delay}s)"}
                        for _ in range(delay):
                            await asyncio.sleep(1)
                            yield {"type": "ping", "content": ""}
                    elif "usage limits" in str(e).lower() or "reached your specified" in str(e).lower():
                        logging.error(f"API usage limit reached: {e}")
                        yield {"type": "text", "content": "⚠️ Se alcanzó el límite de uso de la API de Anthropic. Contactá al administrador para revisar los límites en console.anthropic.com."}
                        yield {"type": "done", "content": ""}
                        return
                    else:
                        logging.error(f"Anthropic API error: {e}")
                        yield {"type": "action", "content": f"⚠️ Error del servicio. Intentá de nuevo en unos segundos."}
                        yield {"type": "done", "content": ""}
                        return

            # ── Plan verification (skip — Opus reads the plan directly now) ──
            if False and has_plan and _loop_iterations == 1:
                try:
                    # Gather all text Valentina produced (from text blocks + tool inputs)
                    verify_text = full_text
                    # Also extract measurements from any tool call inputs (catalog_batch_lookup, calculate_quote)
                    for block in final_message.content:
                        if block.type == "tool_use" and block.input:
                            verify_text += f"\n{json.dumps(block.input, ensure_ascii=False)}"

                    if verify_text and len(verify_text) > 30:
                        from app.modules.agent.plan_verifier import verify_plan_reading
                        yield {"type": "action", "content": "Verificando lectura del plano..."}
                        corrections = await verify_plan_reading(plan_bytes, plan_filename, verify_text)
                        if corrections and corrections.get("discrepancias"):
                            # Discard Valentina's tool calls — she had wrong measurements
                            correction_text = "CORRECCIÓN DE MEDIDAS — un revisor encontró errores en tu lectura del plano:\n\n"
                            for d in corrections["discrepancias"]:
                                correction_text += f"- {d.get('pieza', '?')} {d.get('dimension', '?')}: leíste {d.get('valor_valentina')}, pero el plano dice {d.get('valor_plano')}. {d.get('correccion', '')}\n"
                            if corrections.get("medidas_correctas"):
                                correction_text += f"\nMedidas correctas verificadas: {json.dumps(corrections['medidas_correctas'], ensure_ascii=False)}"
                            correction_text += "\n\nCORREGÍ tus medidas con estos valores y recalculá todo desde cero. Usá SOLO las medidas del revisor."
                            # Add Valentina's response + correction as new messages
                            assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
                            # If there were tool calls, add fake results so message history is valid
                            tool_use_blocks_verify = [b for b in final_message.content if b.type == "tool_use"]
                            if tool_use_blocks_verify:
                                fake_results = [{"type": "tool_result", "tool_use_id": b.id, "content": '{"ok": false, "error": "Medidas incorrectas — revisor corrigió, recalcular"}'} for b in tool_use_blocks_verify]
                                assistant_messages.append({"role": "user", "content": fake_results})
                            assistant_messages.append({"role": "user", "content": [{"type": "text", "text": correction_text}]})
                            yield {"type": "text", "content": "\n\n_Corrección de medidas aplicada por el revisor._\n"}
                            logging.info(f"[plan-verifier] Injected {len(corrections['discrepancias'])} corrections for {quote_id}")
                            await asyncio.sleep(0.1)
                            continue  # Restart loop — Valentina recalculates with correct measurements
                        else:
                            logging.info(f"[plan-verifier] No discrepancies found for {quote_id}")
                except Exception as e:
                    logging.warning(f"[plan-verifier] Verification skipped: {e}")

            # Check if we need to handle tool calls
            tool_use_blocks = [b for b in final_message.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # No tool calls — conversation turn is done
                assistant_messages.append({
                    "role": "assistant",
                    "content": _serialize_content(final_message.content),
                })
                break

            # Process tool calls
            tool_results = []
            for tool_use in tool_use_blocks:
                yield {"type": "action", "content": f"⚙️ Ejecutando: {tool_use.name}..."}
                # Log every tool call with full inputs for debugging
                logging.info(f"🔧 TOOL CALL [{quote_id}]: {tool_use.name}")
                try:
                    import json as _dbg_json
                    logging.info(f"🔧 TOOL INPUT [{quote_id}]: {_dbg_json.dumps(tool_use.input, ensure_ascii=False, default=str)[:2000]}")
                except Exception:
                    logging.info(f"🔧 TOOL INPUT [{quote_id}]: {str(tool_use.input)[:2000]}")

                try:
                    result = await self._execute_tool(
                        tool_use.name,
                        tool_use.input,
                        quote_id=quote_id,
                        db=db,
                        conversation_history=messages,
                        current_user_message=user_message,
                    )
                except Exception as e:
                    logging.error(f"Tool execution error ({tool_use.name}): {e}", exc_info=True)
                    result = {"ok": False, "error": f"Error ejecutando {tool_use.name}: {str(e)}"}

                # Log result summary
                try:
                    if isinstance(result, dict):
                        log_keys = {k: v for k, v in result.items() if k in ("ok", "total_ars", "total_usd", "material", "material_name", "removed", "added", "error", "quote_id")}
                        logging.info(f"🔧 TOOL RESULT [{quote_id}] {tool_use.name}: {log_keys}")
                except Exception:
                    pass

                try:
                    result_json = json.dumps(result)
                except (TypeError, ValueError) as e:
                    logging.error(f"JSON serialization error for tool {tool_use.name}: {e}")
                    result_json = json.dumps({"ok": False, "error": f"Error serializando resultado de {tool_use.name}"})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_json,
                })

            assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
            assistant_messages.append({"role": "user", "content": tool_results})

            # Brief pause between loop iterations (minimal with Tier 1)
            await asyncio.sleep(0.1)

        # Save updated messages to DB
        try:
            updated_messages = db_messages + assistant_messages
            save_values = {"messages": updated_messages}

            # Try to extract client_name and material from conversation if not yet set
            # This ensures the dashboard shows useful info before PDF generation
            result = await db.execute(select(Quote).where(Quote.id == quote_id))
            current_quote = result.scalar_one_or_none()
            if current_quote:
                extracted = _extract_quote_info(user_message)
                if not current_quote.client_name and extracted.get("client_name"):
                    save_values["client_name"] = extracted["client_name"]
                if not current_quote.material and extracted.get("material"):
                    save_values["material"] = extracted["material"]
                if not current_quote.project and extracted.get("project"):
                    save_values["project"] = extracted["project"]

            await db.execute(
                update(Quote)
                .where(Quote.id == quote_id)
                .values(**save_values)
            )
            await db.commit()
        except Exception as e:
            logging.error(f"Error saving conversation to DB: {e}", exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass

        # OPT-05: Per-quote cost summary
        logging.info(
            f"QUOTE COST SUMMARY [{quote_id}] — "
            f"iterations: {_loop_iterations}, "
            f"total_input: {_total_input_tokens}, "
            f"total_output: {_total_output_tokens}, "
            f"cache_read: {_total_cache_read}, "
            f"cache_write: {_total_cache_write}, "
            f"effective_tokens: {_total_input_tokens + _total_output_tokens}"
        )

        yield {"type": "done", "content": ""}

    async def _execute_tool(self, name: str, inputs: dict, quote_id: str, db: AsyncSession, conversation_history: list | None = None, current_user_message: str = "") -> dict:
        logging.info(f"Tool call: {name} | quote: {quote_id}")
        if name == "catalog_lookup":
            return catalog_lookup(inputs["catalog"], inputs["sku"])
        elif name == "catalog_batch_lookup":
            return catalog_batch_lookup(inputs["queries"])
        elif name == "check_stock":
            return check_stock(inputs["material_sku"])
        elif name == "check_architect":
            return check_architect(inputs["client_name"])
        elif name == "read_plan":
            return await read_plan(inputs["filename"], inputs.get("crop_instructions", []))
        elif name == "generate_documents":
            import uuid as uuid_mod
            quotes_data = inputs.get("quotes", [])
            # Backward compat: if old format with quote_data, wrap it
            if not quotes_data and "quote_data" in inputs:
                quotes_data = [inputs["quote_data"]]

            logging.info(f"generate_documents: {len(quotes_data)} material(s) to generate")

            # Pre-flight checklist before generating
            all_warnings: list[str] = []
            for qdata in quotes_data:
                errors, warnings = _validate_quote_data(qdata)
                if errors:
                    error_list = "\n".join(f"❌ {e}" for e in errors)
                    return {
                        "ok": False,
                        "error": f"Pre-flight fallido para {qdata.get('material_name', '?')}:\n{error_list}\n\nCorregir estos datos antes de generar.",
                    }
                all_warnings.extend(warnings)

                # Deep deterministic validation (safety net)
                deep = validate_despiece(qdata)
                if deep.errors:
                    error_list = "\n".join(f"❌ {e}" for e in deep.errors)
                    return {
                        "ok": False,
                        "error": f"Validación profunda fallida para {qdata.get('material_name', '?')}:\n{error_list}\n\nRecalcular antes de generar.",
                    }
                all_warnings.extend(deep.warnings)

            all_results = []

            # Load current quote for context
            cur_q = await db.execute(select(Quote).where(Quote.id == quote_id))
            cur_quote = cur_q.scalar_one_or_none()

            for idx, qdata in enumerate(quotes_data):
                if idx == 0:
                    # First material always uses current quote_id
                    target_qid = quote_id
                else:
                    # Additional materials: create independent quote
                    target_qid = str(uuid_mod.uuid4())
                    new_quote = Quote(
                        id=target_qid,
                        client_name=qdata.get("client_name", ""),
                        project=qdata.get("project", ""),
                        material=qdata.get("material_name"),
                        messages=list(cur_quote.messages or []) if cur_quote else [],
                        status=QuoteStatus.DRAFT,
                    )
                    db.add(new_quote)
                    await db.flush()
                    logging.info(f"Created independent quote {target_qid} for material: {qdata.get('material_name')}")

                # Use DB breakdown if it exists and material matches (from calculate_quote)
                existing_bd_result = await db.execute(select(Quote).where(Quote.id == target_qid))
                existing_bd_quote = existing_bd_result.scalar_one_or_none()
                if existing_bd_quote and existing_bd_quote.quote_breakdown:
                    db_bd = existing_bd_quote.quote_breakdown
                    db_material = (db_bd.get("material_name") or "").strip().upper()
                    valentina_material = (qdata.get("material_name") or "").strip().upper()
                    if db_material == valentina_material:
                        logging.info(f"Using DB breakdown for {target_qid} (material: {db_material})")
                        qdata = db_bd

                # Save quote data + breakdown to DB
                save_vals = {
                    "client_name": qdata.get("client_name", ""),
                    "project": qdata.get("project", ""),
                    "material": qdata.get("material_name"),
                    "total_ars": qdata.get("total_ars"),
                    "total_usd": qdata.get("total_usd"),
                    "quote_breakdown": qdata,
                }
                logging.info(f"Saving quote data {target_qid}: {save_vals}")
                await db.execute(update(Quote).where(Quote.id == target_qid).values(**save_vals))

                # Generate PDF + Excel
                result = await generate_documents(target_qid, qdata)
                logging.info(f"generate_documents [{idx}] {qdata.get('material_name')}: ok={result.get('ok')}, error={result.get('error')}")

                drive_result: dict = {}
                if result.get("ok"):
                    # Only promote status to VALIDATED on first generation
                    # (draft/pending). On regeneration (already validated/sent),
                    # preserve current status — operator controls transitions.
                    doc_values: dict = {
                        "pdf_url": result.get("pdf_url"),
                        "excel_url": result.get("excel_url"),
                    }
                    _qr = await db.execute(select(Quote).where(Quote.id == target_qid))
                    _cur = _qr.scalar_one_or_none()
                    if not _cur or _cur.status in (
                        QuoteStatus.DRAFT, QuoteStatus.PENDING
                    ):
                        doc_values["status"] = QuoteStatus.VALIDATED.value
                    await db.execute(
                        update(Quote).where(Quote.id == target_qid).values(**doc_values)
                    )

                    # Delete old Drive file if exists (prevents duplicates)
                    from app.modules.agent.tools.drive_tool import delete_drive_file
                    old_quote = await db.execute(select(Quote).where(Quote.id == target_qid))
                    old_q = old_quote.scalar_one_or_none()
                    if old_q and old_q.drive_file_id:
                        await delete_drive_file(old_q.drive_file_id)
                        logging.info(f"Deleted old Drive file {old_q.drive_file_id} for quote {target_qid}")

                    # Upload to Drive
                    date_str = qdata.get("date", "")
                    drive_result = await upload_to_drive(
                        target_qid,
                        qdata.get("client_name", ""),
                        qdata.get("material_name", ""),
                        date_str,
                    )
                    logging.info(f"upload_to_drive [{idx}]: {drive_result.get('ok')}")
                    if drive_result.get("ok"):
                        await db.execute(
                            update(Quote).where(Quote.id == target_qid).values(
                                drive_url=drive_result.get("drive_url"),
                                drive_file_id=drive_result.get("drive_file_id"),
                            )
                        )

                # Single atomic commit per quote — all DB changes together
                try:
                    await db.commit()
                except Exception as e:
                    logging.error(f"Failed to commit quote {target_qid}: {e}", exc_info=True)
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    return {"ok": False, "error": f"Error guardando quote: {str(e)[:200]}"}

                all_results.append({
                    "quote_id": target_qid,
                    "material": qdata.get("material_name"),
                    "ok": result.get("ok", False),
                    "pdf_url": result.get("pdf_url"),
                    "excel_url": result.get("excel_url"),
                    "drive_url": drive_result.get("drive_url") if result.get("ok") else None,
                    "error": result.get("error"),
                })

            result = {"ok": True, "generated": len(all_results), "results": all_results}
            if all_warnings:
                result["warnings"] = all_warnings
                result["warnings_text"] = "⚠️ Warnings:\n" + "\n".join(f"• {w}" for w in all_warnings)
            return result

        elif name == "update_quote":
            updates = inputs.get("updates", {})
            allowed = {"client_name", "project", "material", "total_ars", "total_usd", "status"}
            clean = {k: v for k, v in updates.items() if k in allowed and v is not None}
            if not clean:
                return {"ok": False, "error": "No hay campos válidos para actualizar"}
            logging.info(f"update_quote {quote_id}: {clean}")

            # Also update client_name/project inside the breakdown JSON
            q_result = await db.execute(select(Quote).where(Quote.id == quote_id))
            q_obj = q_result.scalar_one_or_none()
            if q_obj and q_obj.quote_breakdown:
                bd = dict(q_obj.quote_breakdown)
                changed = False
                if "client_name" in clean and bd.get("client_name") != clean["client_name"]:
                    bd["client_name"] = clean["client_name"]
                    changed = True
                if "project" in clean and bd.get("project") != clean["project"]:
                    bd["project"] = clean["project"]
                    changed = True
                if changed:
                    clean["quote_breakdown"] = bd

            await db.execute(
                update(Quote)
                .where(Quote.id == quote_id)
                .values(**clean)
            )
            await db.commit()
            return {"ok": True, "updated_fields": list(clean.keys())}
        elif name == "calculate_quote":
            save_to_qid = inputs.pop("target_quote_id", None) or quote_id

            # ── Auto-create independent quote for different material ──
            # Only during INITIAL generation (no breakdown yet or first calculation).
            # In PATCH MODE (quote already validated/has docs), always overwrite
            # the existing quote — the operator is intentionally changing the material.
            try:
                check_q = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                check_quote = check_q.scalar_one_or_none()
                is_patch_mode = check_quote and check_quote.quote_breakdown and (
                    check_quote.status in ("validated", "sent") or check_quote.pdf_url
                )
                if check_quote and check_quote.quote_breakdown and not is_patch_mode:
                    existing_mat = (check_quote.quote_breakdown.get("material_name") or "").strip().upper()
                    new_mat = (inputs.get("material") or "").strip().upper()
                    same_material = (
                        existing_mat == new_mat
                        or existing_mat in new_mat
                        or new_mat in existing_mat
                    )
                    if existing_mat and new_mat and not same_material:
                        # Check if an independent quote for this material already exists
                        # (same client + project + material)
                        from sqlalchemy import and_
                        existing_result = await db.execute(
                            select(Quote).where(
                                and_(
                                    Quote.client_name == (check_quote.client_name or ""),
                                    Quote.material == inputs.get("material"),
                                )
                            )
                        )
                        existing_match = None
                        for eq in existing_result.scalars().all():
                            if eq.id != save_to_qid:
                                existing_match = eq
                                break

                        if existing_match:
                            save_to_qid = existing_match.id
                            logging.info(f"Reusing existing independent quote {save_to_qid} for material {new_mat}")
                        else:
                            import uuid as _uuid
                            new_qid = str(_uuid.uuid4())
                            # Copy messages from original quote
                            new_quote = Quote(
                                id=new_qid,
                                client_name=check_quote.client_name,
                                project=check_quote.project,
                                material=inputs.get("material"),
                                messages=list(check_quote.messages or []),
                                status=QuoteStatus.DRAFT,
                            )
                            db.add(new_quote)
                            await db.flush()
                            save_to_qid = new_qid
                            logging.info(f"Created independent quote {new_qid} for material {new_mat} (original: {quote_id})")
            except Exception as e:
                logging.warning(f"Could not check material conflict for {save_to_qid}: {e}")

            # ── Defensive: preserve params from existing breakdown ──
            # If Valentina omits pileta/anafe/etc but the existing breakdown
            # had them, auto-inject UNLESS the operator explicitly asked to remove them.
            try:
                existing_q = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                existing_quote = existing_q.scalar_one_or_none()
                if existing_quote and existing_quote.quote_breakdown:
                    ebd = existing_quote.quote_breakdown
                    msg_lower = current_user_message.lower()

                    # Detect pileta from breakdown field OR from mo_items descriptions
                    existing_pileta = ebd.get("pileta")
                    if not existing_pileta:
                        # Infer from MO items if breakdown was saved without pileta field
                        for mo in ebd.get("mo_items", []):
                            desc = (mo.get("description") or "").lower()
                            if "pegado pileta" in desc or "pegadopileta" in desc:
                                existing_pileta = "empotrada_johnson"
                                break
                            elif "pileta apoyo" in desc or "agujero apoyo" in desc:
                                existing_pileta = "apoyo"
                                break
                            elif "pileta" in desc and "agujero" in desc:
                                existing_pileta = "empotrada_cliente"
                                break

                    # Detect anafe from breakdown field OR from mo_items
                    existing_anafe = ebd.get("anafe", False)
                    if not existing_anafe:
                        for mo in ebd.get("mo_items", []):
                            if "anafe" in (mo.get("description") or "").lower():
                                existing_anafe = True
                                break

                    # Check if operator is explicitly removing something
                    removing_pileta = any(kw in msg_lower for kw in ["sin pileta", "sacar pileta", "quitar pileta", "remover pileta", "sin agujero", "sacar agujero"])
                    removing_anafe = any(kw in msg_lower for kw in ["sin anafe", "sacar anafe", "quitar anafe", "remover anafe"])

                    # Auto-inject pileta if it existed and operator didn't remove it
                    if not inputs.get("pileta") and existing_pileta and not removing_pileta:
                        inputs["pileta"] = existing_pileta
                        logging.info(f"Auto-preserved pileta={existing_pileta} from existing breakdown for {save_to_qid}")

                    # Auto-inject anafe if it existed and operator didn't remove it
                    if not inputs.get("anafe") and existing_anafe and not removing_anafe:
                        inputs["anafe"] = existing_anafe
                        logging.info(f"Auto-preserved anafe={existing_anafe} from existing breakdown for {save_to_qid}")

                    # Auto-inject frentin/pulido
                    existing_frentin = ebd.get("frentin", False)
                    if not existing_frentin:
                        for mo in ebd.get("mo_items", []):
                            if "frentin" in (mo.get("description") or "").lower() or "regrueso" in (mo.get("description") or "").lower():
                                existing_frentin = True
                                break
                    if not inputs.get("frentin") and existing_frentin:
                        inputs["frentin"] = True

                    existing_pulido = ebd.get("pulido", False)
                    if not existing_pulido:
                        for mo in ebd.get("mo_items", []):
                            if "pulido" in (mo.get("description") or "").lower():
                                existing_pulido = True
                                break
                    if not inputs.get("pulido") and existing_pulido:
                        inputs["pulido"] = True

                    # Auto-inject inglete
                    if not inputs.get("inglete") and ebd.get("inglete"):
                        inputs["inglete"] = True
            except Exception as e:
                logging.warning(f"Could not check existing breakdown for {save_to_qid}: {e}")

            # Fallback: check conversation for pileta keywords
            if not inputs.get("pileta"):
                all_text = current_user_message.lower()
                if conversation_history:
                    for msg in conversation_history:
                        if msg.get("role") == "user":
                            c = msg.get("content", "")
                            if isinstance(c, str):
                                all_text += " " + c.lower()
                            elif isinstance(c, list):
                                for blk in c:
                                    if isinstance(blk, dict) and blk.get("type") == "text":
                                        all_text += " " + blk.get("text", "").lower()
                if any(kw in all_text for kw in ["bacha", "pileta", "cotizar bacha", "con bacha"]):
                    inputs["pileta"] = "empotrada_johnson"
                    logging.warning(f"Auto-injected pileta=empotrada_johnson from conversation keywords")
            calc_result = calculate_quote(inputs)

            # ── Post-calculate deterministic validation ──
            if calc_result.get("ok"):
                validation = validate_despiece(calc_result)
                if not validation.ok:
                    calc_result["_validation_errors"] = validation.errors
                    calc_result["_validation_warnings"] = validation.warnings
                    calc_result["_validation_note"] = (
                        "⚠️ ERRORES DE VALIDACIÓN DETECTADOS. "
                        "Corregir los datos y volver a calcular con calculate_quote. "
                        "NO llamar a generate_documents hasta resolver estos errores."
                    )
                    logging.warning(f"Validation FAILED for {save_to_qid}: {validation.errors}")
                else:
                    if validation.warnings:
                        calc_result["_validation_warnings"] = validation.warnings
                    calc_result["_review_checklist"] = (
                        "ANTES de llamar a generate_documents, revisá:\n"
                        "1. ¿Las piezas coinciden con lo que pidió el operador?\n"
                        "2. ¿El material es correcto?\n"
                        "3. ¿Pileta/anafe/colocación coinciden con el pedido?\n"
                        "4. ¿Los m² tienen sentido para las medidas dadas?\n"
                        "5. ¿El flete es para la zona correcta?"
                    )

            # Persist breakdown + change history to DB
            if calc_result.get("ok"):
                try:
                    # Build change log entry
                    old_q = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                    old_quote = old_q.scalar_one_or_none()
                    change_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "action": "calculate_quote",
                        "material": calc_result.get("material_name"),
                        "total_ars_before": old_quote.total_ars if old_quote else None,
                        "total_usd_before": old_quote.total_usd if old_quote else None,
                        "total_ars_after": calc_result.get("total_ars"),
                        "total_usd_after": calc_result.get("total_usd"),
                        "user_message": current_user_message[:200],
                    }
                    # Append to existing history
                    history = list(old_quote.change_history or []) if old_quote else []
                    history.append(change_entry)

                    await db.execute(
                        update(Quote).where(Quote.id == save_to_qid).values(
                            quote_breakdown=calc_result,
                            total_ars=calc_result.get("total_ars"),
                            total_usd=calc_result.get("total_usd"),
                            material=calc_result.get("material_name"),
                            change_history=history,
                        )
                    )
                    await db.commit()
                    logging.info(f"Saved breakdown for {save_to_qid} after calculate_quote | ARS: {change_entry['total_ars_before']} → {change_entry['total_ars_after']}")
                except Exception as e:
                    logging.warning(f"Could not save breakdown for {save_to_qid}: {e}")
            calc_result["quote_id"] = save_to_qid
            return calc_result
        elif name == "patch_quote_mo":
            # ── Modify MO items directly without recalculating everything ──
            target_qid = quote_id
            remove_keywords = [kw.lower() for kw in inputs.get("remove_items", [])]
            add_colocacion = inputs.get("add_colocacion", False)
            add_flete_localidad = inputs.get("add_flete")

            try:
                q_result = await db.execute(select(Quote).where(Quote.id == target_qid))
                target_quote = q_result.scalar_one_or_none()
                if not target_quote or not target_quote.quote_breakdown:
                    return {"ok": False, "error": f"Quote {target_qid} no tiene breakdown"}

                bd = dict(target_quote.quote_breakdown)
                original_mo = list(bd.get("mo_items", []))
                new_mo = []
                removed = []

                # Remove items matching keywords
                for item in original_mo:
                    desc_lower = (item.get("description") or "").lower()
                    should_remove = any(kw in desc_lower for kw in remove_keywords)
                    if should_remove:
                        removed.append(item["description"])
                    else:
                        new_mo.append(item)

                # Add colocación if requested
                if add_colocacion:
                    # Check if already exists
                    has_col = any("colocación" in (m.get("description") or "").lower() or "colocacion" in (m.get("description") or "").lower() for m in new_mo)
                    if not has_col:
                        mat_type = bd.get("material_type", "nacional")
                        is_sint = mat_type in ("sintetico", "sintético")
                        sku = "COLOCACIONDEKTON/NEOLITH" if is_sint else "COLOCACION"
                        col_result = catalog_lookup("labor", sku)
                        if col_result.get("found"):
                            price = col_result.get("price_ars", 0)
                            base = col_result.get("price_ars_base", price)
                            qty = max(bd.get("material_m2", 1), 1.0)
                            new_mo.append({"description": "Colocación", "quantity": round(qty, 2), "unit_price": price, "base_price": base, "total": round(price * qty)})

                # Add flete if requested
                if add_flete_localidad:
                    has_flete = any("flete" in (m.get("description") or "").lower() for m in new_mo)
                    if not has_flete:
                        from app.modules.quote_engine.calculator import _find_flete
                        flete_result = _find_flete(add_flete_localidad)
                        if flete_result.get("found"):
                            price = flete_result.get("price_ars", 0)
                            base = flete_result.get("price_ars_base", price)
                            new_mo.append({"description": f"Flete + toma medidas {add_flete_localidad}", "quantity": 1, "unit_price": price, "base_price": base, "total": price})

                # Recalculate totals
                bd["mo_items"] = new_mo
                total_mo = sum(m.get("total", 0) for m in new_mo)
                total_sinks = sum(s.get("unit_price", 0) * s.get("quantity", 1) for s in bd.get("sinks", []))
                currency = bd.get("material_currency", "ARS")
                # material_total may not exist in breakdowns saved by generate_documents
                material_total = bd.get("material_total")
                if material_total is None:
                    # Reconstruct from m2 * price_unit
                    m2 = bd.get("material_m2", 0)
                    price_unit = bd.get("material_price_unit", 0)
                    material_total = round(m2 * price_unit)
                    bd["material_total"] = material_total
                    logging.info(f"Reconstructed material_total={material_total} from {m2} * {price_unit}")

                if currency == "USD":
                    bd["total_ars"] = total_mo + total_sinks
                    bd["total_usd"] = material_total
                else:
                    bd["total_ars"] = total_mo + total_sinks + material_total
                    bd["total_usd"] = 0

                # Save to DB
                history = list(target_quote.change_history or [])
                history.append({
                    "timestamp": datetime.now().isoformat(),
                    "action": "patch_quote_mo",
                    "removed": removed,
                    "total_ars_before": target_quote.total_ars,
                    "total_ars_after": bd["total_ars"],
                    "total_usd_before": target_quote.total_usd,
                    "total_usd_after": bd["total_usd"],
                    "user_message": current_user_message[:200],
                })

                await db.execute(
                    update(Quote).where(Quote.id == target_qid).values(
                        quote_breakdown=bd,
                        total_ars=bd["total_ars"],
                        total_usd=bd["total_usd"],
                        change_history=history,
                    )
                )
                await db.commit()

                added = []
                if add_colocacion: added.append("Colocación")
                if add_flete_localidad: added.append(f"Flete {add_flete_localidad}")

                logging.info(f"patch_quote_mo {target_qid}: removed={removed}, added={added}, total_ars={bd['total_ars']}, total_usd={bd['total_usd']}")

                return {
                    "ok": True,
                    "quote_id": target_qid,
                    "removed": removed,
                    "added": added,
                    "mo_items": [{"description": m["description"], "total": m["total"]} for m in new_mo],
                    "total_ars": bd["total_ars"],
                    "total_usd": bd["total_usd"],
                    "material": bd.get("material_name"),
                }
            except Exception as e:
                logging.error(f"patch_quote_mo error for {target_qid}: {e}", exc_info=True)
                return {"ok": False, "error": str(e)[:200]}
        else:
            return {"error": f"Tool desconocida: {name}"}
