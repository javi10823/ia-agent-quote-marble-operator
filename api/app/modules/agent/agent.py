import anthropic
import asyncio
import json
import base64
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select

from app.core.config import settings
from app.models.quote import Quote, QuoteStatus
from app.modules.agent.tools.catalog_tool import catalog_lookup, catalog_batch_lookup, check_stock, check_architect
from app.modules.agent.tools.plan_tool import read_plan
from app.modules.agent.tools.document_tool import generate_documents
from app.modules.agent.tools.drive_tool import upload_to_drive
from app.modules.quote_engine.calculator import calculate_quote

BASE_DIR = Path(__file__).parent.parent.parent.parent

# Materials that MUST have merma
_SYNTHETIC_MATERIALS = ["silestone", "dekton", "neolith", "puraprima", "purastone", "laminatto"]


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


def select_examples(user_message: str, is_building: bool, max_examples: int = 2) -> list:
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
    _CACHED_EXAMPLES = ["quote-013", "quote-003", "quote-004", "quote-010", "quote-030"]
    examples_dir = BASE_DIR / "examples"
    for eid in _CACHED_EXAMPLES:
        matches = list(examples_dir.glob(f"{eid}*.md"))
        if matches:
            core_rules.append(f"## Ejemplo: {matches[0].stem}\n\n{matches[0].read_text(encoding='utf-8')}")

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
        "description": "Rasteriza un plano a 300 DPI con crop por mesada. SOLO usar si necesitás un crop específico de una zona del plano. Si el plano ya fue adjuntado como PDF/imagen en el mensaje del operador, ya lo podés ver directamente SIN llamar esta tool — leerlo del mensaje directamente es más rápido.",
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
                "colocacion": {"type": "boolean", "description": "Si lleva colocación (default: true)"},
                "pileta": {
                    "type": "string",
                    "enum": ["empotrada_cliente", "empotrada_johnson", "apoyo"],
                    "description": "Tipo de pileta. empotrada_johnson = incluir producto Johnson + MO de instalación. empotrada_cliente = solo MO (el cliente trae la pileta). Omitir si no hay pileta.",
                },
                "pileta_sku": {
                    "type": "string",
                    "description": "SKU del modelo de pileta en sinks.json (ej: QUADRAQ71A). Solo para empotrada_johnson. Si no se conoce el modelo, omitir y se usará Johnson default.",
                },
                "anafe": {"type": "boolean", "description": "SOLO true si hay evidencia de anafe en plano o enunciado. Cocina ≠ anafe automático."},
                "frentin": {"type": "boolean", "description": "Si lleva frentin/regrueso"},
                "pulido": {"type": "boolean", "description": "Si lleva pulido de cantos"},
                "plazo": {"type": "string", "description": "Plazo de entrega"},
                "discount_pct": {"type": "number", "description": "Porcentaje de descuento (0-100)"},
            },
            "required": ["client_name", "material", "pieces", "localidad", "plazo"],
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
        rf"(?:cliente|clienta)\s+(.+?)(?:{_DELIMITERS}|$)",
        user_message, re.IGNORECASE,
    )
    if match:
        name = match.group(1).strip()
        info["client_name"] = name.title()

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
MAX_ITERATIONS = 25  # Safety limit — prevent infinite tool loops


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
        db: AsyncSession,
    ) -> AsyncGenerator[dict, None]:

        # Build system prompt per request with contextual loading
        has_plan = plan_bytes is not None and plan_filename is not None
        is_building = _detect_building(user_message)
        system_prompt = build_system_prompt(has_plan=has_plan, is_building=is_building, user_message=user_message, conversation_history=messages)

        # Build user message content
        content = []
        if plan_bytes and plan_filename:
            # Attach plan as image or document
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

        # Append user message to history
        new_messages = clean_messages + [{"role": "user", "content": content}]

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

            # Retry loop for rate limit errors
            for attempt in range(MAX_RETRIES + 1):
                try:
                    async with self.client.messages.stream(
                        model=settings.ANTHROPIC_MODEL,
                        max_tokens=8096,
                        system=system_prompt,
                        messages=new_messages + _compact_tool_results(assistant_messages),
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
                    await asyncio.sleep(delay)

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
                        await asyncio.sleep(delay)
                    else:
                        logging.error(f"Anthropic API error: {e}")
                        yield {"type": "action", "content": f"⚠️ Error del servicio. Intentá de nuevo en unos segundos."}
                        yield {"type": "done", "content": ""}
                        return

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
            updated_messages = new_messages + assistant_messages
            save_values = {"messages": updated_messages}

            # Try to extract client_name and material from conversation if not yet set
            # This ensures the dashboard shows useful info before PDF generation
            result = await db.execute(select(Quote).where(Quote.id == quote_id))
            current_quote = result.scalar_one_or_none()
            if current_quote and not current_quote.client_name:
                extracted = _extract_quote_info(user_message)
                if extracted.get("client_name"):
                    save_values["client_name"] = extracted["client_name"]
                if extracted.get("material"):
                    save_values["material"] = extracted["material"]

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

            all_results = []

            for idx, qdata in enumerate(quotes_data):
                # First material uses current quote_id, rest get new ones
                if idx == 0:
                    target_qid = quote_id
                else:
                    target_qid = str(uuid_mod.uuid4())
                    new_quote = Quote(
                        id=target_qid,
                        client_name=qdata.get("client_name", ""),
                        project=qdata.get("project", ""),
                        material=qdata.get("material_name"),
                        parent_quote_id=quote_id,
                        messages=[],
                        status=QuoteStatus.DRAFT,
                    )
                    db.add(new_quote)
                    await db.flush()  # get ID without committing
                    logging.info(f"Created additional quote {target_qid} for material: {qdata.get('material_name')}")

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
            # Only allow known fields
            allowed = {"client_name", "project", "material", "total_ars", "total_usd", "status"}
            clean = {k: v for k, v in updates.items() if k in allowed and v is not None}
            if not clean:
                return {"ok": False, "error": "No hay campos válidos para actualizar"}
            logging.info(f"update_quote {quote_id}: {clean}")
            await db.execute(
                update(Quote)
                .where(Quote.id == quote_id)
                .values(**clean)
            )
            await db.commit()
            return {"ok": True, "updated_fields": list(clean.keys())}
        elif name == "calculate_quote":
            # ── Defensive injection: if conversation mentions bacha/pileta
            # but the agent didn't include it, auto-inject it ──
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
                    logging.warning(f"Auto-injected pileta=empotrada_johnson — detected in conversation but missing from calculate_quote call")
            calc_result = calculate_quote(inputs)
            # Persist breakdown to DB immediately (don't wait for generate_documents)
            if calc_result.get("ok"):
                try:
                    await db.execute(
                        update(Quote).where(Quote.id == quote_id).values(
                            quote_breakdown=calc_result,
                            total_ars=calc_result.get("total_ars"),
                            total_usd=calc_result.get("total_usd"),
                            material=calc_result.get("material_name"),
                        )
                    )
                    await db.commit()
                    logging.info(f"Saved breakdown for {quote_id} after calculate_quote")
                except Exception as e:
                    logging.warning(f"Could not save breakdown for {quote_id}: {e}")
            return calc_result
        else:
            return {"error": f"Tool desconocida: {name}"}
