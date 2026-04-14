import anthropic
import asyncio
import json
import base64
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select

from app.core.config import settings
from app.models.quote import Quote, QuoteStatus
from app.modules.agent.tools.catalog_tool import catalog_lookup, catalog_batch_lookup, check_stock, check_architect, get_ai_config
from app.modules.agent.tools.plan_tool import read_plan, save_plan_to_temp
from app.modules.agent.tools.document_tool import generate_documents
from app.modules.agent.tools.drive_tool import upload_to_drive
from app.modules.quote_engine.calculator import calculate_quote, list_pieces
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

# ── BUILDING DETECTION (unified — delegates to edificio_parser) ──────────────

def _detect_building(user_message: str) -> bool:
    """Keyword-based building detection for system prompt selection.
    Uses detect_edificio() with empty tables as single source of truth.
    """
    try:
        from app.modules.quote_engine.edificio_parser import detect_edificio
        result = detect_edificio(user_message, [])
        return result["is_edificio"]
    except Exception:
        return False


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
        # ⛔ Context filter: edificio quotes must NOT pull residential examples,
        # and vice-versa. Cross-contamination causes the agent to invent data
        # (e.g. Ventus edificio rendered as "Alejandro particular").
        if is_building and ("particular" in entry_tags or "residential" in entry_tags):
            continue
        if not is_building and ("building" in entry_tags or "edificio" in entry_tags):
            continue
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
    (["bacha", "pileta", "sink", "compra la bacha", "compra bacha", "compra pileta", "la compra en", "la pide"], "pileta", "PILETA/BACHA — el operador pidió cotizar pileta. DEBE aparecer en el presupuesto. Si no se definió tipo, presupuestar Johnson por defecto."),
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
    {"name": "list_pieces", "description": "PASO 1 OBLIGATORIO: lista piezas con formato correcto + total m². Usar SIEMPRE en Paso 1 para mostrar piezas. Zócalos salen en ml. El total incluye zócalos.", "input_schema": {"type": "object", "properties": {"pieces": {"type": "array", "items": {"type": "object", "properties": {"description": {"type": "string"}, "largo": {"type": "number"}, "prof": {"type": "number"}, "alto": {"type": "number"}}, "required": ["description", "largo"]}}}, "required": ["pieces"]}},
    {"name": "catalog_lookup", "description": "Busca precio de 1 SKU en catálogo.", "input_schema": {"type": "object", "properties": {"catalog": {"type": "string"}, "sku": {"type": "string"}}, "required": ["catalog", "sku"]}},
    {"name": "catalog_batch_lookup", "description": "Busca múltiples SKUs. Preferir sobre catalog_lookup para 2+.", "input_schema": {"type": "object", "properties": {"queries": {"type": "array", "items": {"type": "object", "properties": {"catalog": {"type": "string"}, "sku": {"type": "string"}}, "required": ["catalog", "sku"]}}}, "required": ["queries"]}},
    {"name": "check_stock", "description": "Verifica retazos en stock.", "input_schema": {"type": "object", "properties": {"material_sku": {"type": "string"}}, "required": ["material_sku"]}},
    {"name": "check_architect", "description": "Verifica si cliente es arquitecta con descuento.", "input_schema": {"type": "object", "properties": {"client_name": {"type": "string"}}, "required": ["client_name"]}},
    {"name": "read_plan", "description": "AUXILIAR — zoom táctico en zonas de un plano. NO usar para análisis inicial (usá visión nativa sobre el PDF/imagen adjunto). Solo para: cotas chicas, detalles ilegibles, subregiones específicas. LÍMITE: máximo 2 crops por llamada. Si necesitás más, analizá los primeros 2 y después llamá de nuevo.", "input_schema": {"type": "object", "properties": {"filename": {"type": "string"}, "crop_instructions": {"type": "array", "maxItems": 2, "items": {"type": "object", "properties": {"label": {"type": "string"}, "x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}}}}}, "required": ["filename"]}},
    {"name": "generate_documents", "description": "Genera PDF+Excel. 1 quote por material.", "input_schema": {"type": "object", "properties": {"quotes": {"type": "array", "items": {"type": "object", "properties": {"client_name": {"type": "string"}, "project": {"type": "string"}, "date": {"type": "string"}, "delivery_days": {"type": "string"}, "material_name": {"type": "string"}, "material_m2": {"type": "number"}, "material_price_unit": {"type": "number"}, "material_currency": {"type": "string", "enum": ["USD", "ARS"]}, "discount_pct": {"type": "number"}, "sectors": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "pieces": {"type": "array", "items": {"type": "string"}}}}}, "sinks": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "quantity": {"type": "integer"}, "unit_price": {"type": "number"}}}}, "mo_items": {"type": "array", "items": {"type": "object", "properties": {"description": {"type": "string"}, "quantity": {"type": "number"}, "unit_price": {"type": "number"}, "total": {"type": "number"}}}}, "total_ars": {"type": "number"}, "total_usd": {"type": "number"}}, "required": ["client_name", "material_name"]}}}, "required": ["quotes"]}},
    {"name": "update_quote", "description": "Actualiza client_name/project/status en DB.", "input_schema": {"type": "object", "properties": {"quote_id": {"type": "string"}, "updates": {"type": "object", "properties": {"client_name": {"type": "string"}, "project": {"type": "string"}, "material": {"type": "string"}, "total_ars": {"type": "number"}, "total_usd": {"type": "number"}, "status": {"type": "string", "enum": ["draft", "validated", "sent"]}}}}, "required": ["quote_id", "updates"]}},
    {"name": "calculate_quote", "description": "Calcula m², MO, totales. SIEMPRE usar para cálculos.", "input_schema": {"type": "object", "properties": {"client_name": {"type": "string"}, "project": {"type": "string"}, "material": {"type": "string"}, "pieces": {"type": "array", "items": {"type": "object", "properties": {"description": {"type": "string"}, "largo": {"type": "number"}, "prof": {"type": "number"}, "alto": {"type": "number"}}, "required": ["description", "largo"]}}, "localidad": {"type": "string"}, "colocacion": {"type": "boolean"}, "is_edificio": {"type": "boolean"}, "pileta": {"type": "string", "enum": ["empotrada_cliente", "empotrada_johnson", "apoyo"]}, "pileta_qty": {"type": "integer"}, "pileta_sku": {"type": "string"}, "anafe": {"type": "boolean"}, "frentin": {"type": "boolean"}, "frentin_ml": {"type": "number"}, "inglete": {"type": "boolean"}, "pulido": {"type": "boolean"}, "skip_flete": {"type": "boolean", "description": "true SOLO si el cliente retira en fábrica. Default false — siempre cobrar flete."}, "plazo": {"type": "string"}, "discount_pct": {"type": "number"}}, "required": ["client_name", "material", "pieces", "localidad", "plazo"]}},
    {"name": "patch_quote_mo", "description": "Modifica MO sin recalcular. Para agregar/quitar flete, colocación.", "input_schema": {"type": "object", "properties": {"remove_items": {"type": "array", "items": {"type": "string"}}, "add_colocacion": {"type": "boolean"}, "add_flete": {"type": "string"}}, "required": []}},
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

MAX_RETRIES = 5
RETRY_DELAYS = [5, 10, 15, 20, 30]
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

        # ── Building detection: DB flag (sticky) > history > current message ──
        # Once a quote enters building mode, it stays there for all turns.
        is_building = False
        _auto_advance_visual = False  # Set to True when page confirmed → skip to while loop
        try:
            _bq = await db.execute(select(Quote).where(Quote.id == quote_id))
            _bquote = _bq.scalar_one_or_none()
            if _bquote and _bquote.is_building:
                is_building = True
        except Exception:
            pass
        # If not in DB, detect from current message
        if not is_building:
            is_building = _detect_building(user_message)
        # If not in current message, scan conversation history
        if not is_building and messages:
            for msg in messages:
                if msg.get("role") == "user":
                    c = msg.get("content", "")
                    text_parts = []
                    if isinstance(c, str):
                        text_parts.append(c)
                    elif isinstance(c, list):
                        for blk in c:
                            if isinstance(blk, dict) and blk.get("type") == "text":
                                text_parts.append(blk.get("text", ""))
                    for part in text_parts:
                        if _detect_building(part) or "EDIFICIO PRE-CALCULADO" in part or "EDIFICIO — PASO 1" in part:
                            is_building = True
                            break
                if is_building:
                    break
        # Persist to DB so future turns don't need to re-scan
        if is_building:
            try:
                await db.execute(update(Quote).where(Quote.id == quote_id).values(is_building=True))
                await db.commit()
            except Exception:
                pass

        system_prompt = build_system_prompt(has_plan=has_plan, is_building=is_building, user_message=user_message, conversation_history=messages)

        # ── Inject verified measurements if available ──
        try:
            _qr_vm = await db.execute(select(Quote).where(Quote.id == quote_id))
            _q_vm = _qr_vm.scalar_one_or_none()
            if _q_vm and _q_vm.quote_breakdown and _q_vm.quote_breakdown.get("verified_context"):
                _vc = _q_vm.quote_breakdown["verified_context"]
                # Append to system prompt as additional context block
                system_prompt.append({"type": "text", "text": _vc, "cache_control": {"type": "ephemeral"}})
                logging.info(f"[dual-read] Injected verified measurements into system prompt ({len(_vc)} chars)")
        except Exception:
            pass

        # ── EDIFICIO STATE MACHINE: Paso 2, 3 — all server-side ──
        # "step1_review" → confirm → render Paso 2 → "step2_quote"
        # "step2_quote"  → confirm → generate documents → "step3_done"
        if is_building and not has_plan:
            try:
                _p2q = await db.execute(select(Quote).where(Quote.id == quote_id))
                _p2quote = _p2q.scalar_one_or_none()
                _bd = _p2quote.quote_breakdown if _p2quote else None
                _building_step = _bd.get("building_step") if isinstance(_bd, dict) else None
                _is_confirmation = len(user_message.strip()) < 200

                # ── Awaiting client name: capture and resume ──
                if _building_step == "awaiting_client_name" and user_message.strip():
                    new_name = user_message.strip()
                    try:
                        _bd["building_step"] = "step2_quote"  # Resume to Paso 3
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                client_name=new_name,
                                quote_breakdown=_bd,
                                messages=list(_p2quote.messages or []) + [
                                    {"role": "user", "content": [{"type": "text", "text": new_name}]},
                                    {"role": "assistant", "content": [{"type": "text", "text": f"Cliente: {new_name}. Generando presupuestos..."}]},
                                ],
                            )
                        )
                        await db.commit()
                        # Re-read quote with updated client_name
                        _p2q = await db.execute(select(Quote).where(Quote.id == quote_id))
                        _p2quote = _p2q.scalar_one_or_none()
                        _bd = _p2quote.quote_breakdown
                        _building_step = "step2_quote"
                        # Fall through to Paso 3 below
                    except Exception as e:
                        logging.error(f"Failed to save client name: {e}")
                        yield {"type": "text", "content": "Error al guardar el nombre del cliente."}
                        yield {"type": "done", "content": ""}
                        return

                # ── VISUAL EDIFICIO: Awaiting material choice or failed page confirmation ──
                if _building_step == "awaiting_material_choice" and user_message.strip():
                    from app.modules.quote_engine.edificio_parser import (
                        compute_edificio_aggregates, validate_edificio,
                    )
                    from app.modules.quote_engine.visual_edificio_parser import (
                        validate_material_choice, resolve_material_choice,
                        build_normalized_from_visual,
                        render_visual_edificio_paso1, render_visual_edificio_choices,
                        dismiss_failed_pages,
                    )

                    pages_data = _bd.get("visual_pages_raw", [])
                    pending_actions = _bd.get("pending_actions", [])
                    msg_lower = user_message.strip().lower()

                    # ── Action: operator confirms to proceed without failed pages ──
                    if any(kw in msg_lower for kw in ["continuar sin fallidas", "seguir sin fallidas", "ignorar fallidas"]):
                        dismissed = [p.get("_page_number") for p in pages_data if p.get("_extraction_failed")]
                        pages_data = dismiss_failed_pages(pages_data)
                        _bd["visual_pages_raw"] = pages_data
                        _bd["dismissed_failed_pages"] = dismissed
                        _bd["operator_accepted_partial_extraction"] = True
                        if "failed_pages_confirmation" in pending_actions:
                            pending_actions.remove("failed_pages_confirmation")

                    # ── Action: operator chooses material ──
                    has_material_blocker = any("Material ambiguo" in b for b in _bd.get("blockers", []))
                    if has_material_blocker and not any(kw in msg_lower for kw in ["continuar sin", "seguir sin", "ignorar"]):
                        # Validate material choice against detected options
                        ok, normalized_choice, available_options = validate_material_choice(pages_data, user_message.strip())
                        if not ok:
                            opts_str = " / ".join(f"({i+1}) {o}" for i, o in enumerate(available_options))
                            response = (
                                f"No pude mapear \"{user_message.strip()}\" a un material válido.\n\n"
                                f"Las opciones detectadas son:\n{opts_str}\n\n"
                                f"Indicá el material exacto o el número de opción."
                            )
                            try:
                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(
                                        quote_breakdown=_bd,
                                        messages=list(_p2quote.messages or []) + [
                                            {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                            {"role": "assistant", "content": [{"type": "text", "text": response}]},
                                        ],
                                    )
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"Failed to save invalid material choice: {e}")
                            yield {"type": "text", "content": response}
                            yield {"type": "done", "content": ""}
                            return
                        # Valid choice — resolve
                        pages_data = resolve_material_choice(pages_data, normalized_choice)
                        _bd["material_choice"] = normalized_choice
                        if "material_choice" in pending_actions:
                            pending_actions.remove("material_choice")

                    _bd["pending_actions"] = pending_actions

                    # Re-normalize and check remaining blockers
                    norm_data, visual_warnings, visual_blockers = build_normalized_from_visual(pages_data)

                    if visual_blockers:
                        # Still blockers
                        response = render_visual_edificio_choices(pages_data, visual_warnings, visual_blockers)
                        _bd["visual_pages_raw"] = pages_data
                        _bd["warnings"] = visual_warnings
                        _bd["blockers"] = visual_blockers
                    else:
                        # All clear → proceed to Paso 1 review
                        edif_summary = compute_edificio_aggregates(norm_data)
                        edif_validation = validate_edificio(norm_data, edif_summary)
                        material_choice = _bd.get("material_choice")
                        response = render_visual_edificio_paso1(
                            pages_data, norm_data, edif_summary, visual_warnings,
                            material_choice=material_choice,
                        )
                        response += "\n\n¿Confirmás las piezas y medidas?"

                        _bd["building_step"] = "step1_review"
                        _bd["summary"] = edif_summary
                        _bd["validation"] = dict(edif_validation)
                        _bd["normalized_pieces_flat"] = [dict(p) for s in norm_data.get("sections", []) for p in s.get("pieces", [])]
                        _bd["visual_pages_raw"] = pages_data
                        _bd["warnings"] = visual_warnings

                    try:
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                quote_breakdown=_bd,
                                messages=list(_p2quote.messages or []) + [
                                    {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                    {"role": "assistant", "content": [{"type": "text", "text": response}]},
                                ],
                            )
                        )
                        await db.commit()
                    except Exception as e:
                        logging.error(f"Failed to save material choice state: {e}")

                    yield {"type": "text", "content": response}
                    yield {"type": "done", "content": ""}
                    return

                # ── VISUAL PAGES: Operator drew zone rectangle (Fix G) ──
                if _building_step and _building_step.endswith("_zone_selector"):
                    # Zone was already set by POST /zone-select endpoint
                    # This message is the system_trigger from frontend
                    # Just continue to extraction — zone is in quote_breakdown
                    logging.info(f"[visual-pages] Zone selector confirmed, continuing extraction")
                    # Don't return — fall through to while loop for extraction

                # ── VISUAL PAGES: Operator confirming a page ──
                elif _building_step and _building_step.startswith("visual_page_") and _building_step.endswith("_confirm"):
                    from app.modules.quote_engine.visual_quote_builder import (
                        parse_page_confirmation,
                        apply_corrections,
                        compute_visual_geometry,
                        compute_field_confidence,
                        infer_visual_services,
                        build_visual_pending_questions,
                        render_page_confirmation,
                        render_final_paso1,
                        resolve_visual_materials,
                        MaterialResolution,
                        TipologiaGeometry,
                    )
                    import re as _re_page

                    _page_match = _re_page.search(r"visual_page_(\d+)_confirm", _building_step)
                    _conf_page = int(_page_match.group(1)) if _page_match else 1
                    _page_key = str(_conf_page)
                    _page_data = _bd.get("page_data", {})
                    _pd = _page_data.get(_page_key, {})
                    _tips = _pd.get("tipologias", [])
                    _zones = _pd.get("detected_zones", [])
                    _total_pages = _bd.get("total_pages", 1)

                    action_result = parse_page_confirmation(user_message, _tips, _zones)
                    action = action_result.get("action", "unclear")

                    if action == "confirm" or action == "value_correction":
                        if action == "value_correction":
                            _tips = apply_corrections(_tips, action_result["corrections"])
                            # Recalculate geometry
                            mat_res_d = _bd.get("material_resolution", {})
                            mat_res = MaterialResolution(**mat_res_d) if mat_res_d else resolve_visual_materials("")
                            geo = compute_visual_geometry(_tips, mat_res)
                            _pd["tipologias"] = _tips
                            _pd["geometries"] = [
                                {"id": g.id, "m2_unit": g.m2_unit, "m2_total": g.m2_total,
                                 "backsplash_ml_unit": g.backsplash_ml_unit,
                                 "backsplash_m2_total": g.backsplash_m2_total,
                                 "physical_pieces_total": g.physical_pieces_total}
                                for g in geo.tipologias
                            ]

                        _pd["confirmed"] = True
                        # Learn zone_default from first confirmed page
                        if not _bd.get("zone_default") and _pd.get("selected_zone"):
                            _bd["zone_default"] = _pd["selected_zone"]["name"]

                        _pages_completed = _bd.get("pages_completed", [])
                        if _conf_page not in _pages_completed:
                            _pages_completed.append(_conf_page)
                        _bd["pages_completed"] = _pages_completed
                        _page_data[_page_key] = _pd
                        _bd["page_data"] = _page_data

                        next_page = _conf_page + 1
                        if next_page <= _total_pages:
                            _bd["current_page"] = next_page
                            _bd["building_step"] = f"visual_page_{next_page}"
                            try:
                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"[visual-pages] Failed to persist: {e}")
                            yield {"type": "action", "content": f"✅ Página {_conf_page} confirmada. Procesando página {next_page}..."}
                            yield {"type": "action", "content": f"📐 Analizando página {next_page}/{_total_pages}..."}

                            # Auto-advance: directly process next page without waiting for operator
                            # Inject system instruction as user message → while loop calls Claude for zone detection
                            assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                                f"[SISTEMA] Página {_conf_page} confirmada. "
                                f"Analizar página {next_page}/{_total_pages} del PDF. "
                                f"Detectar zonas nombradas (PLANTA, CORTE, etc). Solo JSON de zones."
                            )}]})
                            _auto_advance_visual = True
                        else:
                            # ── ALL PAGES CONFIRMED → render final PASO 1 ──
                            # Build confirmed_tipologias from page_data (NOT by append)
                            all_tips = []
                            for pg in sorted(_page_data.keys(), key=lambda x: int(x)):
                                pd = _page_data[pg]
                                if pd.get("confirmed") and not pd.get("skipped"):
                                    all_tips.extend(pd.get("tipologias", []))

                            mat_res_d = _bd.get("material_resolution", {})
                            mat_res = MaterialResolution(**mat_res_d) if mat_res_d else resolve_visual_materials("")
                            geometry = compute_visual_geometry(all_tips, mat_res)
                            services = infer_visual_services(all_tips, geometry)
                            pending = build_visual_pending_questions(mat_res, services, all_tips)
                            final_text = render_final_paso1(geometry.tipologias, services, mat_res, pending)

                            _bd["building_step"] = "visual_all_confirmed"
                            _bd["confirmed_tipologias"] = all_tips
                            try:
                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"[visual-pages] Failed to persist final: {e}")

                            yield {"type": "text", "content": final_text}
                            yield {"type": "done", "content": ""}
                            return

                    elif action == "zone_correction":
                        new_zone = action_result["zone"]
                        _pd["selected_zone"] = new_zone
                        _pd["zone_was_auto"] = False
                        _bd["zone_default"] = new_zone["name"]
                        # Clear tipologias to force re-extraction with new zone
                        _pd.pop("tipologias", None)
                        _pd.pop("geometries", None)
                        _page_data[_page_key] = _pd
                        _bd["page_data"] = _page_data
                        _bd["building_step"] = f"visual_page_{_conf_page}"
                        try:
                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"[visual-pages] Failed to persist zone correction: {e}")
                        yield {"type": "text", "content": f"Zona cambiada a '{new_zone['name']}'. Re-analizando..."}
                        yield {"type": "done", "content": ""}
                        return

                    elif action == "skip":
                        _pd["confirmed"] = True
                        _pd["skipped"] = True
                        _pages_completed = _bd.get("pages_completed", [])
                        if _conf_page not in _pages_completed:
                            _pages_completed.append(_conf_page)
                        _bd["pages_completed"] = _pages_completed
                        _page_data[_page_key] = _pd
                        _bd["page_data"] = _page_data

                        next_page = _conf_page + 1
                        if next_page <= _total_pages:
                            _bd["current_page"] = next_page
                            _bd["building_step"] = f"visual_page_{next_page}"
                        else:
                            _bd["building_step"] = "visual_all_confirmed"

                        try:
                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"[visual-pages] Failed to persist skip: {e}")

                        if next_page <= _total_pages:
                            yield {"type": "action", "content": f"Página {_conf_page} salteada. Procesando página {next_page}..."}
                            assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                                f"[SISTEMA] Página {_conf_page} salteada. "
                                f"Analizar página {next_page}/{_total_pages}. Solo JSON de zones."
                            )}]})
                            _auto_advance_visual = True
                        # Fall through to render final if last page
                    else:
                        yield {"type": "text", "content": (
                            "No entendí la respuesta. Opciones:\n"
                            "- **Confirmar**: sí / ok / dale\n"
                            "- **Corregir medida**: `DC-02 profundidad = 0.65`\n"
                            "- **Cambiar zona**: `zona = CORTE 1-1`\n"
                            "- **Sin marmolería**: skip"
                        )}
                        yield {"type": "done", "content": ""}
                        return

                # ── Skip remaining pre-loop handlers if auto-advancing visual pages ──
                if _auto_advance_visual:
                    _visual_builder_done = False  # Reset for next page processing in while loop
                    logging.info(f"[visual-pages] Auto-advance: PDF in context = {plan_bytes is not None}, strip_disabled = True")
                    # Fall through to while True loop with injected system message

                # ── PASO 3: Generate documents ──
                elif _building_step == "step2_quote" and _bd.get("paso2_calc"):
                    # Validate client_name before generating
                    if not (_p2quote.client_name or "").strip():
                        # Save state and ask for client name
                        try:
                            _bd["building_step"] = "awaiting_client_name"
                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(
                                    quote_breakdown=_bd,
                                    messages=list(_p2quote.messages or []) + [
                                        {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                        {"role": "assistant", "content": [{"type": "text", "text": "Para generar los presupuestos necesito el nombre del cliente. Escribilo y continúo."}]},
                                    ],
                                )
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"Failed to save awaiting_client_name state: {e}")
                        yield {"type": "text", "content": "Para generar los presupuestos necesito el nombre del cliente. Escribilo y continúo."}
                        yield {"type": "done", "content": ""}
                        return

                    from app.modules.agent.tools.document_tool import generate_edificio_documents
                    yield {"type": "action", "content": "Generando presupuestos..."}

                    paso2_calc = _bd["paso2_calc"]
                    edif_summary = _bd.get("summary", {})

                    try:
                        doc_result = await generate_edificio_documents(
                            quote_id=quote_id,
                            paso2_calc=paso2_calc,
                            summary=edif_summary,
                            client_name=_p2quote.client_name or "",
                            project=_p2quote.project or f"Proyecto Edificio {_p2quote.client_name or ''}".strip(),
                            localidad=_p2quote.localidad or "Rosario",
                        )
                    except Exception as e:
                        logging.error(f"[edificio-paso3] generate_edificio_documents crashed: {e}", exc_info=True)
                        yield {"type": "text", "content": f"Error al generar documentos: {str(e)[:300]}"}
                        yield {"type": "done", "content": ""}
                        return

                    if doc_result.get("ok"):
                        from app.modules.agent.tools.drive_tool import upload_single_file_to_drive
                        from app.core.static import OUTPUT_DIR as _OUT

                        # ── Upload each file to Drive individually + build files_v2 ──
                        files_v2_items = []
                        subfolder = f"{_p2quote.client_name or 'Edificio'}"

                        for gen in doc_result["generated"]:
                            mat = gen.get("material", "")
                            is_resumen = "RESUMEN" in mat.upper()
                            mat_key = "resumen" if is_resumen else mat.replace(" ", "_").lower()[:30]

                            for kind, url_key in [("pdf", "pdf_url"), ("excel", "excel_url")]:
                                local_url = gen.get(url_key)
                                if not local_url:
                                    continue
                                # Derive local path from URL: /files/{qid}/filename → OUTPUT_DIR/{qid}/filename
                                local_path = str(_OUT / local_url.replace("/files/", "", 1)) if local_url.startswith("/files/") else ""
                                filename = local_url.split("/")[-1] if local_url else ""

                                # Upload to Drive
                                drive_info = {}
                                if local_path:
                                    try:
                                        dr = await upload_single_file_to_drive(local_path, subfolder)
                                        if dr.get("ok"):
                                            drive_info = {
                                                "file_id": dr["file_id"],
                                                "drive_url": dr["drive_url"],
                                                "drive_download_url": dr["drive_download_url"],
                                            }
                                            gen[f"drive_{kind}_url"] = dr["drive_url"]
                                    except Exception as e:
                                        logging.warning(f"Drive upload failed for {filename}: {e}")

                                scope = "parent" if is_resumen else "child"
                                file_key = f"parent:summary_{kind}" if is_resumen else f"{mat_key}:{kind}"

                                files_v2_items.append({
                                    "kind": f"summary_{kind}" if is_resumen else kind,
                                    "scope": scope,
                                    "file_key": file_key,
                                    "owner_quote_id": quote_id if is_resumen else None,  # filled per-child below
                                    "filename": filename,
                                    "local_path": local_path,
                                    "local_url": local_url or "",
                                    **({f"drive_{k}": v for k, v in drive_info.items()} if drive_info else {}),
                                })

                            # Set drive_url on gen (legacy compat — use first Drive URL found)
                            gen["drive_url"] = gen.get("drive_pdf_url") or gen.get("drive_excel_url") or ""

                        # ── Build response ──
                        lines = ["Documentos generados:\n"]
                        for gen in doc_result["generated"]:
                            lines.append(f"📄 **{gen['material']}**")
                            if gen.get("drive_pdf_url"):
                                lines.append(f"  - [PDF en Drive]({gen['drive_pdf_url']})")
                            elif gen.get("pdf_url"):
                                lines.append(f"  - [Descargar PDF]({gen['pdf_url']})")
                            if gen.get("drive_excel_url"):
                                lines.append(f"  - [Excel en Drive]({gen['drive_excel_url']})")
                            elif gen.get("excel_url"):
                                lines.append(f"  - [Descargar Excel]({gen['excel_url']})")
                        lines.append("")
                        lines.append(f"**Total ARS: ${doc_result['grand_total_ars']:,.0f}".replace(",", ".") + "**")
                        if doc_result["grand_total_usd"]:
                            lines.append(f"**Total USD: USD {doc_result['grand_total_usd']:,.0f}".replace(",", ".") + "**")
                        paso3_response = "\n".join(lines)

                        # ── Persist to DB ──
                        try:
                            _bd["building_step"] = "step3_done"
                            _bd["files_v2"] = {"items": files_v2_items}

                            # Match generated docs to children
                            children_result = await db.execute(
                                select(Quote).where(
                                    Quote.parent_quote_id == quote_id,
                                    Quote.quote_kind == "building_child_material",
                                )
                            )
                            children = {(c.material or "").upper(): c for c in children_result.scalars().all()}

                            resumen_gen = None
                            for gen in doc_result["generated"]:
                                mat_upper = (gen.get("material") or "").upper()
                                if "RESUMEN" in mat_upper:
                                    resumen_gen = gen
                                    continue
                                child = children.get(mat_upper)
                                if not child:
                                    for cmat, cq in children.items():
                                        if mat_upper in cmat or cmat in mat_upper:
                                            child = cq
                                            break
                                if child:
                                    # Build child's own files_v2
                                    child_files = [
                                        {**item, "owner_quote_id": child.id}
                                        for item in files_v2_items
                                        if item["scope"] == "child" and item.get("filename", "").startswith(gen.get("material", "XXX")[:15])
                                    ]
                                    # Simpler match: just grab items for this material
                                    mat_key = mat_upper.replace(" ", "_").lower()[:30]
                                    child_files = [item for item in files_v2_items if item.get("file_key", "").startswith(mat_key)]
                                    for cf in child_files:
                                        cf["owner_quote_id"] = child.id

                                    child_bd = child.quote_breakdown or {}
                                    child_bd["files_v2"] = {"items": child_files}

                                    await db.execute(
                                        update(Quote).where(Quote.id == child.id).values(
                                            pdf_url=gen.get("pdf_url"),
                                            excel_url=gen.get("excel_url"),
                                            drive_url=gen.get("drive_url"),
                                            drive_pdf_url=gen.get("drive_pdf_url"),
                                            drive_excel_url=gen.get("drive_excel_url"),
                                            quote_breakdown=child_bd,
                                            status=QuoteStatus.VALIDATED,
                                        )
                                    )

                            # Update parent
                            updated_msgs = list(_p2quote.messages or []) + [
                                {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                {"role": "assistant", "content": [{"type": "text", "text": paso3_response}]},
                            ]
                            parent_update = {
                                "quote_breakdown": _bd,
                                "messages": updated_msgs,
                                "status": QuoteStatus.VALIDATED,
                            }
                            if resumen_gen:
                                parent_update["pdf_url"] = resumen_gen.get("pdf_url")
                                parent_update["excel_url"] = resumen_gen.get("excel_url")
                                parent_update["drive_url"] = resumen_gen.get("drive_url")

                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(**parent_update)
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"Failed to save edificio Paso 3: {e}", exc_info=True)

                        yield {"type": "text", "content": paso3_response}
                        yield {"type": "done", "content": ""}
                        return  # ← EXIT: edificio Paso 3 done
                    else:
                        yield {"type": "text", "content": f"Error al generar documentos: {doc_result.get('error', 'desconocido')}"}
                        yield {"type": "done", "content": ""}
                        return

                # ── PASO 2: Pricing ──
                if _building_step == "step1_review" and _is_confirmation:
                    from app.modules.quote_engine.edificio_parser import render_edificio_paso2
                    yield {"type": "action", "content": "Calculando precios por material..."}

                    edif_summary = _bd["summary"]
                    edif_localidad = _p2quote.localidad or "Rosario"

                    paso2_data = render_edificio_paso2(edif_summary, edif_localidad)
                    paso2_response = paso2_data["rendered"] + "\n¿Confirmás para generar los presupuestos?"

                    # Save calc results + advance state machine
                    try:
                        _bd["building_step"] = "step2_quote"  # Next confirmation → Paso 3 (generate)
                        _bd["paso2_calc"] = {
                            "calc_results": paso2_data["calc_results"],
                            "mo_items": paso2_data["mo_items"],
                            "mo_total": paso2_data["mo_total"],
                            "grand_total_ars": paso2_data["grand_total_ars"],
                            "grand_total_usd": paso2_data["grand_total_usd"],
                        }
                        updated_msgs = list(_p2quote.messages or []) + [
                            {"role": "user", "content": [{"type": "text", "text": user_message}]},
                            {"role": "assistant", "content": [{"type": "text", "text": paso2_response}]},
                        ]
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                quote_breakdown=_bd,
                                messages=updated_msgs,
                                total_ars=paso2_data["grand_total_ars"],
                                total_usd=paso2_data["grand_total_usd"],
                            )
                        )
                        await db.commit()

                        # ── Create building_child_material quotes ──
                        from app.modules.quote_engine.edificio_parser import build_edificio_doc_context
                        import uuid as _uuid_mod
                        child_contexts = build_edificio_doc_context(
                            edif_summary, _bd["paso2_calc"],
                            _p2quote.client_name or "", _p2quote.project or "",
                        )
                        child_ids = []
                        for ctx in child_contexts:
                            child_id = str(_uuid_mod.uuid4())
                            mat_raw = ctx.get("_mat_name_raw", "")
                            child_quote = Quote(
                                id=child_id,
                                quote_kind="building_child_material",
                                parent_quote_id=quote_id,
                                client_name=_p2quote.client_name,
                                project=_p2quote.project or f"Proyecto Edificio {_p2quote.client_name or ''}".strip(),
                                material=ctx.get("material_name", mat_raw),
                                localidad=_p2quote.localidad,
                                is_building=True,
                                status=QuoteStatus.DRAFT,
                                source=_p2quote.source,
                                is_read=True,
                                total_ars=ctx.get("total_ars", 0),
                                total_usd=ctx.get("total_usd", 0),
                                quote_breakdown={
                                    k: v for k, v in ctx.items()
                                    if not k.startswith("_")
                                },
                            )
                            db.add(child_quote)
                            child_ids.append(child_id)
                            logging.info(f"[edificio] Created child {child_id} for {mat_raw}")
                        await db.commit()
                        logging.info(f"[edificio] Created {len(child_ids)} children for parent {quote_id}")

                    except Exception as e:
                        logging.error(f"Failed to save edificio Paso 2: {e}", exc_info=True)

                    yield {"type": "text", "content": paso2_response}
                    yield {"type": "done", "content": ""}
                    return  # ← EXIT: no Claude for edificio Paso 2
            except Exception as e:
                logging.warning(f"Edificio Paso 2 bypass failed, falling back to Claude: {e}")

        # Build user message content
        content = []
        pdf_has_images = False  # Track if PDF has drawings (needs vision pass)
        _expected_m2 = None  # Surface area from planilla (if found) for validation
        is_visual_building = False  # Track if this is a multipágina CAD building (Ventus-type)
        if plan_bytes and plan_filename:
            # Persist plan file to temp so read_plan tool can access it later
            save_plan_to_temp(plan_filename, plan_bytes)
            ext = Path(plan_filename).suffix.lower()
            if ext == ".pdf":
                # Pasada 1: Extract text/tables from PDF with pdfplumber (exact, no hallucination)
                extracted_text = ""
                tables_all = []  # Collect all tables for summary
                num_pages = 0
                try:
                    import pdfplumber
                    import io as _io
                    _planilla_data = None  # Will hold parsed planilla if detected
                    with pdfplumber.open(_io.BytesIO(plan_bytes)) as pdf:
                        num_pages = len(pdf.pages)
                        for i, page in enumerate(pdf.pages):
                            # Extract tables first (structured data)
                            tables = page.extract_tables()
                            tables_all.extend(tables)

                            # Try to detect planilla layout (table on right side)
                            if not _planilla_data and tables:
                                try:
                                    from app.modules.quote_engine.planilla_parser import parse_planilla_table, detect_table_x_from_words
                                    table_objects = page.find_tables()
                                    _planilla_data = parse_planilla_table(
                                        tables, page_width=page.width, page_height=page.height,
                                        table_bboxes=table_objects
                                    )
                                    if _planilla_data:
                                        # Use word positions for accurate table x (bbox is unreliable)
                                        _word_x = detect_table_x_from_words(page)
                                        if _word_x > 0:
                                            _planilla_data.table_x0 = _word_x
                                        logging.info(f"[planilla] Detected: material={_planilla_data.material}, "
                                                     f"m2={_planilla_data.m2}, table_x0={_planilla_data.table_x0:.0f}")
                                        if _planilla_data.m2:
                                            _expected_m2 = _planilla_data.m2
                                except Exception as e:
                                    logging.warning(f"[planilla] Detection failed: {e}")

                            if tables:
                                for t_idx, table in enumerate(tables):
                                    extracted_text += f"\n--- Tabla {t_idx+1} (página {i+1}) ---\n"
                                    for row in table:
                                        cells = [str(c).strip() if c else "" for c in row]
                                        extracted_text += " | ".join(cells) + "\n"
                            # Also extract plain text (headers, notes, etc.)
                            page_text = page.extract_text()
                            if page_text:
                                extracted_text += f"\n--- Texto página {i+1} ---\n{page_text}\n"

                            # ── Vision detection: 3-condition heuristic ──
                            # Condition 1: Raster images > 200x200px
                            for img in (page.images or []):
                                w = img.get("width", 0) or img.get("x1", 0) - img.get("x0", 0)
                                h = img.get("height", 0) or img.get("top", 0) - img.get("bottom", 0)
                                if abs(w) > 200 and abs(h) > 200:
                                    pdf_has_images = True
                                    logging.info(f"Vision trigger: raster image {abs(w)}x{abs(h)} on page {i+1}")

                            # Condition 2: High vector density (CAD/architectural drawings)
                            VECTOR_LINES_THRESHOLD = 20
                            VECTOR_RECTS_THRESHOLD = 10
                            VECTOR_CURVES_THRESHOLD = 20
                            n_lines = len(page.lines or [])
                            n_rects = len(page.rects or [])
                            n_curves = len(page.curves or [])
                            if n_lines > VECTOR_LINES_THRESHOLD or n_rects > VECTOR_RECTS_THRESHOLD or n_curves > VECTOR_CURVES_THRESHOLD:
                                pdf_has_images = True
                                logging.info(f"Vision trigger: vector density on page {i+1} (lines={n_lines}, rects={n_rects}, curves={n_curves})")

                    # Condition 3: Low useful text + domain context (plano/obra keywords)
                    if not pdf_has_images and num_pages > 0:
                        avg_chars = len(extracted_text.strip()) / num_pages
                        PLAN_KEYWORDS = {"plano", "lámina", "lamina", "cocina", "obra", "escala", "corte", "planta", "tipología", "tipologia", "desarrollo", "mesada"}
                        text_lower = extracted_text.lower()
                        has_plan_context = any(kw in text_lower for kw in PLAN_KEYWORDS)
                        if avg_chars < 200 and has_plan_context:
                            pdf_has_images = True
                            logging.info(f"Vision trigger: low text ({avg_chars:.0f} chars/page avg) + plan keywords detected")
                    if extracted_text.strip():
                        # ── Extract M2 from planilla text (deterministic surface validator) ──
                        _expected_m2 = None
                        import re as _re_m2
                        # Match patterns like "M2  2,50 m2", "M2: 2.50m2", "2,50 m2 - Con zócalos"
                        _m2_patterns = [
                            r'(?:M2|m2|SUPERFICIE|superficie)\s*[:\|]?\s*(\d+[.,]\d+)\s*m2',
                            r'(\d+[.,]\d+)\s*m2\s*[-–—]\s*[Cc]on\s+z[oó]calos',
                            r'(\d+[.,]\d+)\s*m2',
                        ]
                        for _pat in _m2_patterns:
                            _m2_match = _re_m2.search(_pat, extracted_text)
                            if _m2_match:
                                _expected_m2 = float(_m2_match.group(1).replace(",", "."))
                                logging.info(f"[m2-validator] Extracted expected M2 from planilla: {_expected_m2}")
                                break

                        # Check if this is an edificio — use deterministic parser
                        from app.modules.quote_engine.edificio_parser import (
                            detect_edificio, parse_edificio_tables,
                            normalize_edificio_data, compute_edificio_aggregates,
                            validate_edificio, render_edificio_paso1,
                        )
                        detection = detect_edificio(user_message, tables_all)

                        if detection["is_edificio"]:
                            # ── EDIFICIO DETECTED ──
                            detection_mode = detection.get("detection_mode", "keyword")
                            logging.info(f"Edificio detected (confidence={detection['confidence']:.2f}, mode={detection_mode}): {detection['reasons']}")

                            # Try tabular path first
                            raw_data = parse_edificio_tables(tables_all)
                            has_tabular_data = bool(raw_data.get("sections"))

                            if has_tabular_data:
                                # ── PATH A: TABULAR EDIFICIO (existing, 100% server-side) ──
                                detection_mode = "tabular"
                                norm_data = normalize_edificio_data(raw_data)
                                edif_summary = compute_edificio_aggregates(norm_data)
                                edif_validation = validate_edificio(norm_data, edif_summary)
                                rendered_paso1 = render_edificio_paso1(norm_data, edif_summary)

                                logging.info(f"Edificio tabular path: {edif_summary.get('totals', {})}")
                                if not edif_validation["is_valid"]:
                                    logging.error(f"Edificio validation FAILED: {edif_validation['errors']}")

                                paso1_response = rendered_paso1 + "\n\n¿Confirmás las piezas y medidas?"
                                all_warns = edif_validation.get("warnings", [])
                                errors = edif_validation.get("errors", [])
                                if errors:
                                    err_list = "\n".join(f"❌ {e}" for e in errors)
                                    paso1_response = rendered_paso1 + f"\n\n**Errores a corregir:**\n{err_list}\n\n⛔ Corregir antes de confirmar."
                                elif all_warns:
                                    ubic_warns = [w for w in all_warns if "sin ubicación" in w.lower()]
                                    m2_warns = [w for w in all_warns if "m2" in w.lower() or "m²" in w.lower()]
                                    qty_warns = [w for w in all_warns if "cantidad" in w.lower()]
                                    other_warns = [w for w in all_warns if w not in ubic_warns + m2_warns + qty_warns]
                                    parts = []
                                    if ubic_warns:
                                        parts.append(f"{len(ubic_warns)} piezas sin ubicación en planilla")
                                    if m2_warns:
                                        parts.append(f"{len(m2_warns)} diferencias de m² entre planilla y cálculo")
                                    if qty_warns:
                                        parts.append(f"{len(qty_warns)} piezas con cantidad > 1")
                                    for w in other_warns:
                                        parts.append(w)
                                    summary_text = " · ".join(parts) if parts else f"{len(all_warns)} advertencias"
                                    paso1_response = rendered_paso1 + f"\n\n*Advertencias no bloqueantes ({len(all_warns)}): {summary_text}.*\n\n¿Confirmás las piezas y medidas?"

                                import json as _json
                                pre_calc = {
                                    "building_step": "step1_review",
                                    "building_detection_mode": detection_mode,
                                    "summary": edif_summary,
                                    "validation": dict(edif_validation),
                                    "normalized_pieces": [dict(p) for s in norm_data.get("sections", []) for p in s.get("pieces", [])],
                                }

                            elif pdf_has_images:
                                # ── PATH B: VISUAL CAD EDIFICIO (new, uses Claude vision) ──
                                detection_mode = "visual_auto" if detection_mode != "manual_override" else "manual_override"
                                logging.info(f"Edificio visual CAD path (mode={detection_mode}): no tabular data, PDF has images")
                                from app.modules.quote_engine.visual_edificio_parser import (
                                    extract_visual_edificio, build_normalized_from_visual,
                                    render_visual_edificio_paso1, render_visual_edificio_choices,
                                )

                                yield {"type": "text", "content": "Analizando planos CAD con visión artificial... (puede tomar 15-30 segundos)"}

                                pages_data = await extract_visual_edificio(self.client, plan_bytes)

                                if not pages_data:
                                    yield {"type": "text", "content": "No se pudieron extraer datos del PDF. ¿Podés enviar la planilla con las medidas?"}
                                    yield {"type": "done", "content": ""}
                                    return

                                norm_data, visual_warnings, visual_blockers = build_normalized_from_visual(pages_data)

                                import json as _json
                                if visual_blockers:
                                    # Blockers (material ambiguo / failed pages) → stop and ask
                                    paso1_response = render_visual_edificio_choices(pages_data, visual_warnings, visual_blockers)

                                    # Track what the operator needs to resolve
                                    pending_actions = []
                                    if any("Material ambiguo" in b for b in visual_blockers):
                                        pending_actions.append("material_choice")
                                    if any("fallaron" in b for b in visual_blockers):
                                        pending_actions.append("failed_pages_confirmation")

                                    pre_calc = {
                                        "building_step": "awaiting_material_choice",
                                        "building_detection_mode": detection_mode,
                                        "visual_pages_raw": pages_data,
                                        "warnings": visual_warnings,
                                        "blockers": visual_blockers,
                                        "pending_actions": pending_actions,
                                        "source": "visual_cad",
                                    }
                                else:
                                    # No blockers → proceed to Paso 1 review
                                    edif_summary = compute_edificio_aggregates(norm_data)
                                    edif_validation = validate_edificio(norm_data, edif_summary)
                                    paso1_response = render_visual_edificio_paso1(
                                        pages_data, norm_data, edif_summary, visual_warnings,
                                    )
                                    paso1_response += "\n\n¿Confirmás las piezas y medidas?"

                                    pre_calc = {
                                        "building_step": "step1_review",
                                        "building_detection_mode": detection_mode,
                                        "summary": edif_summary,
                                        "validation": dict(edif_validation),
                                        "normalized_pieces_flat": [dict(p) for s in norm_data.get("sections", []) for p in s.get("pieces", [])],
                                        "visual_pages_raw": pages_data,
                                        "warnings": visual_warnings,
                                        "source": "visual_cad",
                                    }
                            else:
                                # No tables, no images — ask for planilla
                                yield {"type": "text", "content": "Detecté que es un edificio, pero el PDF no tiene tablas ni planos visibles. ¿Podés enviar la planilla con las medidas en formato tabla (Excel o CSV)?"}
                                yield {"type": "done", "content": ""}
                                return

                            # ── Common save & emit for both tabular and visual paths ──
                            try:
                                # Extract client/project from message if quote doesn't have them yet
                                _update_vals = {
                                    "is_building": True,
                                    "quote_kind": "building_parent",
                                    "quote_breakdown": pre_calc,
                                }
                                _cur_q = await db.execute(select(Quote).where(Quote.id == quote_id))
                                _cur_quote = _cur_q.scalar_one_or_none()
                                if _cur_quote:
                                    extracted = _extract_quote_info(user_message)
                                    if not (_cur_quote.client_name or "").strip() and extracted.get("client_name"):
                                        _update_vals["client_name"] = extracted["client_name"]
                                    if not (_cur_quote.project or "").strip() and extracted.get("project"):
                                        _update_vals["project"] = extracted["project"]

                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(**_update_vals)
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"Failed to save edificio pre-calc: {e}")

                            clean_user_content = [{"type": "text", "text": user_message}]
                            if plan_bytes:
                                clean_user_content.insert(0, {"type": "text", "text": "(adjunto planos edificio)"})
                            assistant_msg = {"role": "assistant", "content": [{"type": "text", "text": paso1_response}]}
                            try:
                                updated_messages = list(messages) + [
                                    {"role": "user", "content": clean_user_content},
                                    assistant_msg,
                                ]
                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(messages=updated_messages)
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"Failed to save edificio conversation: {e}")

                            yield {"type": "text", "content": paso1_response}
                            yield {"type": "done", "content": ""}
                            return  # ← EXIT: no Claude loop for edificio Paso 1
                        else:
                            # Non-edificio PDF
                            if _planilla_data:
                                # Planilla detected — send structured context instead of raw table
                                from app.modules.quote_engine.planilla_parser import build_planilla_context
                                planilla_ctx = build_planilla_context(_planilla_data)
                                content.append({"type": "text", "text": planilla_ctx})
                                logging.info(f"[planilla] Sending structured context ({len(planilla_ctx)} chars) instead of raw table")
                            else:
                                # Regular PDF — send extracted text with safety instructions
                                content.append({"type": "text", "text": f"[TEXTO EXTRAÍDO DEL PDF — DATOS EXACTOS]\n⛔ Extraído con precisión 100%. USAR TAL CUAL. Celda \"-\" o vacía = NO APLICA. NUNCA inferir ni inventar.\n\n{extracted_text.strip()}"})

                        logging.info(f"Extracted {len(extracted_text)} chars of text from PDF ({len(plan_bytes)} bytes)")
                except Exception as e:
                    logging.warning(f"pdfplumber extraction failed: {e}")

                # Pasada 2: If PDF has drawings/images, also send as document for vision
                if pdf_has_images or not extracted_text.strip():
                    if _planilla_data and _planilla_data.table_x0 > 0:
                        # Planilla: send ONLY the drawing (left side), not the full PDF
                        try:
                            from pdf2image import convert_from_bytes as _cfb
                            from app.modules.quote_engine.planilla_parser import crop_drawing_from_page
                            _plan_dpi = (ai_cfg if 'ai_cfg' in dir() else get_ai_config()).get("plan_rasterization_dpi", 300)
                            _raster_pages = _cfb(plan_bytes, dpi=_plan_dpi, first_page=1, last_page=1)
                            if _raster_pages:
                                _drawing_img = crop_drawing_from_page(_raster_pages[0], _planilla_data, dpi=_plan_dpi)
                                # Convert to JPEG bytes
                                _draw_buf = _io.BytesIO()
                                _drawing_img.save(_draw_buf, format="JPEG", quality=85)
                                _draw_bytes = _draw_buf.getvalue()
                                content.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": base64.b64encode(_draw_bytes).decode(),
                                    },
                                })
                                logging.info(f"[planilla] Sending cropped drawing only ({_drawing_img.width}x{_drawing_img.height}, {len(_draw_bytes)} bytes)")

                                # ── COTAS: extract dimensional text positionally from PDF ──
                                _cotas_text = None
                                try:
                                    from app.modules.quote_engine.cotas_extractor import (
                                        extract_cotas_from_drawing, format_cotas_for_prompt
                                    )
                                    _cotas = extract_cotas_from_drawing(
                                        page,
                                        table_x0=_planilla_data.table_x0,
                                        dpi=_plan_dpi,
                                    )
                                    if _cotas:
                                        _cotas_text = format_cotas_for_prompt(_cotas)
                                        logging.info(f"[cotas] Injecting {len(_cotas)} pre-extracted cotas into dual read")
                                    else:
                                        logging.info("[cotas] No cotas extractable from PDF text → fallback to vision-only")
                                except Exception as e:
                                    logging.warning(f"[cotas] Extraction failed, falling back to vision-only: {e}")

                                # ── DUAL READ: send crop to Sonnet (+ Opus if unsure) ──
                                try:
                                    from app.modules.quote_engine.dual_reader import dual_read_crop
                                    _dual_enabled = ai_cfg.get("dual_read_enabled", True) if 'ai_cfg' in dir() else get_ai_config().get("dual_read_enabled", True)
                                    yield {"type": "action", "content": "📐 Leyendo medidas del plano..."}
                                    _dual_result = await dual_read_crop(
                                        _draw_bytes,
                                        crop_label=_planilla_data.ubicacion or "cocina",
                                        planilla_m2=_planilla_data.m2,
                                        dual_enabled=_dual_enabled,
                                        cotas_text=_cotas_text,
                                    )
                                    if not _dual_result.get("error"):
                                        # Save crop to disk for potential Opus retry
                                        try:
                                            from app.core.static import OUTPUT_DIR as _OUT
                                            _crop_dir = _OUT / quote_id
                                            _crop_dir.mkdir(parents=True, exist_ok=True)
                                            _crop_path = _crop_dir / "dual_read_crop.jpg"
                                            _crop_path.write_bytes(_draw_bytes)
                                            _dual_result["_crop_path"] = str(_crop_path)
                                        except Exception as e:
                                            logging.warning(f"[dual-read] Failed to save crop: {e}")
                                        # Send to frontend
                                        yield {"type": "dual_read_result", "content": json.dumps(_dual_result, ensure_ascii=False)}
                                        # Store in quote breakdown
                                        try:
                                            _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
                                            _q = _qr.scalar_one_or_none()
                                            if _q:
                                                _bd = dict(_q.quote_breakdown or {})
                                                _bd["dual_read_result"] = _dual_result
                                                _bd["dual_read_planilla_m2"] = _planilla_data.m2
                                                _bd["dual_read_crop_label"] = _planilla_data.ubicacion or "cocina"
                                                await db.execute(update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd))
                                                await db.commit()
                                        except Exception as e:
                                            logging.warning(f"[dual-read] Failed to save result: {e}")
                                        logging.info(f"[dual-read] Result sent: source={_dual_result.get('source')}, review={_dual_result.get('requires_human_review')}")
                                        # ── STOP: agent terminates turn, waits for operator confirmation ──
                                        yield {"type": "done", "content": ""}
                                        return
                                    else:
                                        logging.warning(f"[dual-read] Error: {_dual_result.get('error')}")
                                        # Error → fall through to normal Claude flow
                                except Exception as e:
                                    logging.error(f"[dual-read] Exception: {e}", exc_info=True)
                                    # Non-fatal — fall through to normal Claude flow

                        except Exception as e:
                            logging.warning(f"[planilla] Drawing crop failed, falling back to full PDF: {e}")
                            content.append({
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": base64.b64encode(plan_bytes).decode(),
                                },
                            })
                    else:
                        content.append({
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.b64encode(plan_bytes).decode(),
                            },
                        })
                        logging.info(f"PDF has images/drawings — sending as document for vision pass")

                    # Detect visual building: multipágina CAD with building keywords
                    # Search in: extracted text + filename + user message (operator often says "edificio X")
                    _building_keywords = ["tipolog", "cantidad", "unidad", "piso", "fideicomiso",
                                          "edificio", "obra", "cocina", "desarrollo", "lamina", "lámina",
                                          "departamento", "depto", "dpto", "ventus", "montevideo"]
                    _all_searchable = (extracted_text + " " + plan_filename + " " + user_message).lower()
                    _keyword_hits = sum(1 for kw in _building_keywords if kw in _all_searchable)
                    if num_pages >= 3 and pdf_has_images and _keyword_hits >= 2:
                        is_visual_building = True
                        logging.info(f"Visual building detected: {num_pages} pages, {_keyword_hits} keyword hits in text+filename+message")
                    elif num_pages >= 5 and pdf_has_images:
                        # 5+ pages with vector density = almost certainly a building project
                        is_visual_building = True
                        logging.info(f"Visual building detected by page count: {num_pages} pages (keywords={_keyword_hits})")
                else:
                    logging.info(f"PDF is text-only (no images) — skipping vision pass, using extracted text only")
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

        # Inject context hint based on quote state
        try:
            _ctx_q = await db.execute(select(Quote).where(Quote.id == quote_id))
            _ctx_quote = _ctx_q.scalar_one_or_none()
            if _ctx_quote and _ctx_quote.quote_breakdown:
                bd = _ctx_quote.quote_breakdown
                is_validated = _ctx_quote.pdf_url or _ctx_quote.status in (QuoteStatus.VALIDATED, QuoteStatus.SENT)
                if is_validated:
                    # Strict patch mode — only MO changes via patch_quote_mo
                    ctx_hint = (
                        f"\n[SISTEMA — MODO PATCH ACTIVO]\n"
                        f"Este presupuesto YA tiene documentos generados (material: {bd.get('material_name')}, "
                        f"total_ars: {bd.get('total_ars')}, total_usd: {bd.get('total_usd')}). "
                        f"Estás en MODO PATCH. Usá patch_quote_mo para cambios de MO (flete, colocación). "
                        f"NO volver a preguntar datos ni piezas. NO usar calculate_quote para cambios de MO."
                    )
                else:
                    # Draft with breakdown but no docs — free edit mode
                    ctx_hint = (
                        f"\n[SISTEMA — EDICIÓN LIBRE]\n"
                        f"Este presupuesto tiene un cálculo previo (material: {bd.get('material_name')}, "
                        f"total_ars: {bd.get('total_ars')}, total_usd: {bd.get('total_usd')}) pero AÚN NO tiene documentos generados.\n"
                        f"- Cambios de MO (flete, colocación) → usá patch_quote_mo\n"
                        f"- Cambios de material, piezas, medidas → usá calculate_quote (recálculo completo)\n"
                        f"NO volver a preguntar datos que ya tenés. Aplicar el cambio directo."
                    )
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            block["text"] = block["text"] + ctx_hint
                            break
        except Exception:
            pass

        # Detect multiple materials in user message → inject hint
        _msg_lower = user_message.lower() if isinstance(user_message, str) else ""
        _multi_mat_patterns = [" y ", " o ", "opción 1", "opcion 1", "alternativa", "también en ", "tambien en "]
        _material_keywords = ["silestone", "dekton", "neolith", "puraprima", "purastone", "laminatto",
                              "granito", "mármol", "marmol", "negro brasil", "carrara"]
        _mat_count = sum(1 for mk in _material_keywords if mk in _msg_lower)
        if _mat_count >= 2 and any(p in _msg_lower for p in _multi_mat_patterns):
            multi_mat_hint = (
                "\n\n[SISTEMA — MÚLTIPLES MATERIALES DETECTADOS]\n"
                "El operador pidió presupuestar más de un material en este mensaje. "
                "Llamar calculate_quote UNA VEZ POR MATERIAL, con las mismas piezas y medidas para cada uno. "
                "Cada material genera un presupuesto independiente."
            )
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["text"] = block["text"] + multi_mat_hint
                        break

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
        # System triggers are internal — don't pass them to Claude or save as user message
        _is_system_trigger = user_message.startswith("[SYSTEM_TRIGGER:")

        # ── Handle DUAL_READ_CONFIRMED: inject verified measurements ──
        if user_message.startswith("[DUAL_READ_CONFIRMED]"):
            try:
                _confirmed_json = json.loads(user_message[len("[DUAL_READ_CONFIRMED]"):])
                from app.modules.quote_engine.dual_reader import build_verified_context
                _verified_ctx = build_verified_context(_confirmed_json)
                # Save to breakdown
                _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
                _q = _qr.scalar_one_or_none()
                if _q:
                    _bd = dict(_q.quote_breakdown or {})
                    _bd["verified_measurements"] = _confirmed_json
                    _bd["verified_context"] = _verified_ctx
                    await db.execute(update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd))
                    await db.commit()
                logging.info(f"[dual-read] Verified measurements saved for {quote_id}")
                yield {"type": "text", "content": "✅ Medidas verificadas guardadas en contexto."}
                yield {"type": "done", "content": ""}
                return
            except Exception as e:
                logging.error(f"[dual-read] Confirmation failed: {e}")
                # Fall through to normal processing

        if _is_system_trigger:
            new_messages = clean_messages  # No user message for Claude
            db_messages = clean_messages   # No user message in DB
            logging.info(f"[system-trigger] {user_message} — not added to message history")
        else:
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
        # Notify operator about processing mode
        # Detect edificio for action message
        _is_edificio_mode = False
        if has_plan and not pdf_has_images:
            # Check if edificio was detected
            try:
                from app.modules.quote_engine.edificio_parser import detect_edificio as _det
                _det_result = _det(user_message, tables_all if 'tables_all' in dir() else [])
                _is_edificio_mode = _det_result.get("is_edificio", False)
            except Exception:
                pass
            if _is_edificio_mode:
                yield {"type": "action", "content": "🏗️ Modo edificio — datos extraídos y calculados por el sistema"}
            else:
                yield {"type": "action", "content": "📄 Modo texto — planilla detectada, extracción exacta (sin Opus)"}
        elif has_plan and pdf_has_images:
            yield {"type": "action", "content": "📐 Modo plano — dibujo detectado, usando Opus para lectura visual"}
        else:
            yield {"type": "action", "content": "Leyendo catálogos y calculando..."}

        _list_pieces_called = False  # Track if list_pieces was called (guardrail for Paso 1)
        _list_pieces_retry_done = False  # Prevent infinite retry
        _last_had_visual_tool = False  # Track if previous iteration used a visual tool (read_plan)
        _suppress_text = False        # Suppress streaming text during visual tool loops
        _read_plan_calls = 0          # Count read_plan calls to enforce limit
        MAX_READ_PLAN_CALLS = 3       # Hard limit: max 3 read_plan calls per conversation
        _visual_builder_done = False  # Track if visual builder already processed

        while True:
            if _loop_iterations >= MAX_ITERATIONS:
                logging.error(f"Agent exceeded MAX_ITERATIONS ({MAX_ITERATIONS}) for quote {quote_id}")
                yield {"type": "action", "content": f"⚠️ Se alcanzó el límite de iteraciones ({MAX_ITERATIONS}). Intentá con un enunciado más simple."}
                break

            full_text = ""
            tool_uses = []

            # Model selection:
            # - Opus: first iteration with plan, OR iteration after visual tool call
            # - Sonnet: everything else (prices, MO, docs)
            OPUS_MODEL = "claude-opus-4-6"
            VISUAL_TOOLS = {"read_plan"}  # Tools that need visual context preserved
            ai_cfg = get_ai_config()
            needs_vision = has_plan and pdf_has_images

            # Show a brief status for visual PDF processing (operator sees blank otherwise)
            if needs_vision and pdf_has_images and _loop_iterations == 0:
                yield {"type": "action", "content": "📐 Analizando plano..."}
            # Use Opus on first iteration OR when previous iteration used a visual tool
            use_opus = needs_vision and (_loop_iterations == 0 or _last_had_visual_tool) and ai_cfg.get("use_opus_for_plans", True)
            current_model = OPUS_MODEL if use_opus else settings.ANTHROPIC_MODEL
            if use_opus:
                logging.info(f"Using Opus for plan reading (iteration {_loop_iterations + 1}, visual_tool_prev={_last_had_visual_tool})")
            elif has_plan and _loop_iterations == 0 and not pdf_has_images:
                logging.info(f"PDF is text-only — using Sonnet (no Opus needed)")

            # Strip plan images from messages — BUT preserve if:
            # - previous iteration used a visual tool (read_plan)
            # - auto-advancing to next page (needs PDF for zone detection)
            _should_strip = _loop_iterations > 0 and has_plan and not _last_had_visual_tool and not _auto_advance_visual
            if _should_strip:
                msgs_for_api = []
                for msg in new_messages:
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        filtered = [b for b in content if not (isinstance(b, dict) and b.get("type") in ("image", "document"))]
                        if not filtered:
                            filtered = [{"type": "text", "text": "(plano ya leído en iteración anterior)"}]
                        msgs_for_api.append({**msg, "content": filtered})
                    else:
                        msgs_for_api.append(msg)
                logging.info(f"Stripped visual content from messages (iteration {_loop_iterations + 1})")
            else:
                msgs_for_api = new_messages
                if _loop_iterations > 0 and _last_had_visual_tool:
                    logging.info(f"Preserving visual content (iteration {_loop_iterations + 1} — previous used visual tool)")

            # Retry loop for rate limit errors
            for attempt in range(MAX_RETRIES + 1):
                try:
                    # Edificio: remove list_pieces from available tools —
                    # data comes from deterministic pipeline, not list_pieces
                    active_tools = [t for t in TOOLS if t["name"] != "list_pieces"] if is_building else TOOLS

                    # Visual building: remove read_plan on first iteration to force JSON extraction
                    # Claude must use native vision on the PDF document, not call read_plan
                    # read_plan comes back in later iterations if needed for corrections/zoom
                    if is_visual_building and not _visual_builder_done:
                        active_tools = [t for t in active_tools if t["name"] != "read_plan"]

                    # Dynamic max_tokens: higher for visual PDFs (7+ láminas need space for analysis + tool_use)
                    _max_tokens = 16384 if (needs_vision and pdf_has_images) else 8096

                    async with self.client.messages.stream(
                        model=current_model,
                        max_tokens=_max_tokens,
                        system=system_prompt,
                        messages=msgs_for_api + _compact_tool_results(assistant_messages),
                        tools=active_tools,
                    ) as stream:
                        async for event in stream:
                            if hasattr(event, "type"):
                                if event.type == "content_block_delta":
                                    if hasattr(event.delta, "text"):
                                        full_text += event.delta.text
                                        # For visual PDFs: buffer ALL text until we know if this
                                        # iteration has tool calls. If it does, text is monologue
                                        # and gets suppressed. If not, it's the final response
                                        # and gets flushed in the no-tool-calls branch below.
                                        if not (needs_vision and pdf_has_images):
                                            yield {"type": "text", "content": event.delta.text}
                                        # For non-visual flows, stream text normally
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
                            logging.error(f"API overloaded after all {MAX_RETRIES} retries for quote {quote_id}. Giving up.")
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

            # ── Handle max_tokens truncation ──
            # If response was cut off by token limit, the agent may have been mid-analysis
            # or about to emit a tool_use. Continue the loop so Claude can finish.
            if getattr(final_message, "stop_reason", None) == "max_tokens":
                logging.warning(f"[max_tokens] Response truncated at iteration {_loop_iterations} — continuing loop")
                assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
                assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                    "[SISTEMA] Tu respuesta se cortó por límite de tokens. "
                    "Continuá EXACTAMENTE donde quedaste. NO repitas lo que ya dijiste. "
                    "Si ibas a ejecutar una herramienta, ejecutala ahora."
                )}]})
                await asyncio.sleep(0.1)
                continue

            # Check if we need to handle tool calls
            tool_use_blocks = [b for b in final_message.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # No tool calls — this is the final response.

                # ── Visual building pipeline: page-by-page zone detection + extraction ──
                # Only for multipágina CAD buildings (Ventus-type), NOT simple images
                if is_visual_building and full_text and not _visual_builder_done:
                    from app.modules.quote_engine.visual_quote_builder import (
                        parse_visual_extraction,
                        parse_zone_detection,
                        auto_select_zone,
                        parse_page_confirmation,
                        resolve_visual_materials,
                        validate_visual_extraction,
                        compute_visual_geometry,
                        compute_field_confidence,
                        infer_visual_services,
                        build_visual_pending_questions,
                        get_tipologias_needing_second_pass,
                        merge_second_pass,
                        parse_focused_response,
                        render_page_confirmation,
                        render_final_paso1,
                        MaterialResolution,
                        TipologiaGeometry,
                    )
                    from app.modules.agent.tools.plan_tool import read_plan as _read_plan_fn
                    import copy as _copy

                    # Load or init page-by-page state from quote_breakdown
                    try:
                        _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
                        _qt = _qr.scalar_one_or_none()
                        _bd = (_qt.quote_breakdown if _qt and _qt.quote_breakdown else {}) or {}
                    except Exception:
                        _bd = {}

                    _step = _bd.get("building_step", "")
                    _current_page = _bd.get("current_page", 1)
                    _total_pages = _bd.get("total_pages", num_pages if 'num_pages' in dir() else 1)
                    _page_data = _bd.get("page_data", {})
                    _zone_default = _bd.get("zone_default")
                    _pages_completed = _bd.get("pages_completed", [])

                    # ── Init on first entry ──
                    if not _step or _step in ("awaiting_visual_confirmation", "visual_step1_shown"):
                        # First time or re-entry: detect material + init state
                        # Try to get material from the first extraction
                        _mat_text = ""
                        _parsed_init = parse_visual_extraction(full_text)
                        if _parsed_init:
                            _mat_text = _parsed_init.get("material_text", "")
                        mat_res = resolve_visual_materials(_mat_text)
                        _bd["material_resolution"] = mat_res.to_dict()
                        _bd["total_pages"] = _total_pages
                        _bd["current_page"] = 1
                        _bd["page_data"] = {}
                        _bd["pages_completed"] = []
                        _bd["pdf_filename"] = plan_filename if plan_filename else ""
                        _current_page = 1
                        _page_data = {}
                        _pages_completed = []
                        _step = f"visual_page_{_current_page}"
                        _bd["building_step"] = _step
                        logging.info(f"[visual-pages] Init: {_total_pages} pages, material={mat_res.mode} → {mat_res.resolved}")

                    # ── Process current page state ──
                    _page_key = str(_current_page)
                    _pd = _page_data.get(_page_key, {})

                    # STEP 0A: Text extraction from full page (page 1 only)
                    # Extract material, artefactos, zócalos, quantity from the text panel
                    # This info is the same on all láminas — only need it once
                    if _current_page == 1 and "page_text_info" not in _bd:
                        try:
                            _text_crop = await _read_plan_fn(
                                _bd.get("pdf_filename", plan_filename or ""), [], page=1
                            )
                            _text_content = list(_text_crop) if isinstance(_text_crop, list) else []
                            _text_content.append({
                                "type": "text",
                                "text": (
                                    "Extraer SOLO datos de MARMOLERÍA de esta lámina. "
                                    "Responder SOLO JSON compacto con este schema exacto:\n"
                                    '{"material_text": "texto exacto de material y espesor de la sección MESADAS", '
                                    '"pileta_codes": ["sa-01", "sa-02"], '
                                    '"griferia_codes": ["gr-01"], '
                                    '"zocalo_height_cm": 7.5, '
                                    '"cantidad_unidades": 2, '
                                    '"notas": ["movemos pileta", "lateral con mármol?"]}\n'
                                    "Solo códigos de artefactos, NO descripciones largas. "
                                    "Ignorar: muebles, carpintería, herrería, instalaciones."
                                ),
                            })
                            _text_resp = await self.client.messages.create(
                                model="claude-opus-4-6",
                                max_tokens=500,  # Compact schema — only codes, no descriptions
                                system="Extraer información textual de una lámina de plano CAD. Solo JSON.",
                                messages=[{"role": "user", "content": _text_content}],
                            )
                            _text_raw = _text_resp.content[0].text if _text_resp.content else ""
                            logging.info(f"[visual-pages] Page text extraction: {_text_raw[:300]}")

                            # Parse and persist — extract material_text even if JSON truncated
                            try:
                                _page_text_info = None
                                _text_json_match = re.search(r"```json\s*(.*?)```", _text_raw, re.DOTALL)
                                _raw_json_str = _text_json_match.group(1).strip() if _text_json_match else _text_raw
                                try:
                                    _page_text_info = json.loads(_raw_json_str)
                                except json.JSONDecodeError:
                                    # JSON truncated — try to find outermost object
                                    _text_brace_match = re.search(r"\{[\s\S]*\}", _raw_json_str)
                                    if _text_brace_match:
                                        try:
                                            _page_text_info = json.loads(_text_brace_match.group(0))
                                        except json.JSONDecodeError:
                                            pass

                                # Fallback: extract material_text by regex even from truncated JSON
                                _mat_text_extracted = None
                                if _page_text_info and _page_text_info.get("material_text"):
                                    _mat_text_extracted = _page_text_info["material_text"]
                                elif not _page_text_info:
                                    _mat_match = re.search(r'"material_text"\s*:\s*"([^"]+)"', _text_raw)
                                    if _mat_match:
                                        _mat_text_extracted = _mat_match.group(1)
                                        _page_text_info = {"material_text": _mat_text_extracted}
                                        logging.info(f"[visual-pages] Extracted material_text from truncated JSON: {_mat_text_extracted}")

                                if _page_text_info:
                                    _bd["page_text_info"] = _page_text_info
                                    # Use material_text for resolution if not already set
                                    if _mat_text_extracted and not _bd.get("material_resolution"):
                                        mat_res = resolve_visual_materials(_page_text_info["material_text"])
                                        _bd["material_resolution"] = mat_res.to_dict()
                                        logging.info(f"[visual-pages] Material from text panel: {mat_res.mode} → {mat_res.resolved}")
                            except (json.JSONDecodeError, Exception) as e:
                                logging.warning(f"[visual-pages] Text extraction parse failed: {e}")
                        except Exception as e:
                            logging.error(f"[visual-pages] Text extraction failed: {e}")

                    # STEP 0B: Zone detection (pasada 0) — separate Claude call
                    if _step == f"visual_page_{_current_page}" and "detected_zones" not in _pd:
                        # Get a crop of the full page for zone detection
                        from app.modules.agent.tools.plan_tool import read_plan as _read_plan_fn
                        _pdf_fn = _bd.get("pdf_filename", plan_filename or "")
                        try:
                            page_crop = await _read_plan_fn(_pdf_fn, [], page=_current_page)
                        except Exception as e:
                            logging.error(f"[visual-pages] Page {_current_page} crop failed: {e}")
                            page_crop = []

                        zone_content = list(page_crop) if isinstance(page_crop, list) else []
                        zone_content.append({
                            "type": "text",
                            "text": "Detectar todas las zonas nombradas de esta página. Solo JSON de zones.",
                        })

                        try:
                            zone_resp = await self.client.messages.create(
                                model="claude-opus-4-6",
                                max_tokens=1500,  # 500 was too low for 4-5 zones with bbox+view_type
                                system=(
                                    "Sos un detector de zonas de planos CAD. "
                                    "Detectar TODAS las zonas nombradas de esta página: PLANTA, CORTE 1-1, CORTE 2-2, DETALLE, etc. "
                                    "Para cada zona: name, bbox [x1,y1,x2,y2] en píxeles, view_type (top_view/section/detail/unknown), confidence (0-1). "
                                    "Si no tiene nombre → ZONA-N. "
                                    "Responder ÚNICAMENTE con JSON: {\"zones\": [...]}"
                                ),
                                messages=[{"role": "user", "content": zone_content}],
                            )
                            resp_text = zone_resp.content[0].text if zone_resp.content else ""
                            logging.info(f"[visual-pages] Zone detection response: {resp_text[:200]}")
                            zones = parse_zone_detection(resp_text)
                        except Exception as e:
                            logging.error(f"[visual-pages] Zone detection call failed: {e}")
                            zones = []

                        if not zones:
                            zones = [{"name": "PÁGINA COMPLETA", "bbox": [0, 0, 700, 700], "view_type": "unknown", "confidence": 0.5}]
                        _pd["detected_zones"] = zones
                        _page_data[_page_key] = _pd
                        _bd["page_data"] = _page_data
                        logging.info(f"[visual-pages] Page {_current_page}: {len(zones)} zones detected")

                    # STEP B: Select zone (auto or operator rectangle)
                    if "detected_zones" in _pd and "selected_zone" not in _pd:
                        zones = _pd["detected_zones"]
                        _zone_default_bbox = _bd.get("zone_default_bbox")

                        # Fix G: Check if operator rectangle needed (page 1 only, ambiguous zones)
                        _needs_selector = (
                            _total_pages >= 2
                            and _current_page == 1
                            and len(zones) >= 2
                            and not any(z.get("view_type") == "top_view" and z.get("confidence", 0) >= 0.85 for z in zones)
                            and not _bd.get("zone_default")
                            and not _zone_default_bbox
                        )

                        if _needs_selector:
                            # Save page image for frontend
                            import base64 as _b64_mod
                            from app.core.static import OUTPUT_DIR
                            _img_saved = False
                            try:
                                _page_crop_for_selector = await _read_plan_fn(
                                    _bd.get("pdf_filename", plan_filename or ""), [], page=_current_page
                                )
                                for _block in (_page_crop_for_selector or []):
                                    if _block.get("type") == "image":
                                        _img_bytes = _b64_mod.b64decode(_block["source"]["data"])
                                        _img_dir = OUTPUT_DIR / quote_id
                                        _img_dir.mkdir(parents=True, exist_ok=True)
                                        _img_file = _img_dir / f"page_{_current_page}.jpg"
                                        _img_file.write_bytes(_img_bytes)
                                        _img_saved = True
                                        break
                            except Exception as e:
                                logging.error(f"[visual-pages] Failed to save page image: {e}")

                            if _img_saved:
                                _bd["building_step"] = f"visual_page_{_current_page}_zone_selector"
                                try:
                                    await db.execute(
                                        update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                                    )
                                    await db.commit()
                                except Exception as e:
                                    logging.error(f"[visual-pages] Failed to persist zone_selector state: {e}")

                                yield {"type": "zone_selector", "content": json.dumps({
                                    "image_url": f"/files/{quote_id}/page_{_current_page}.jpg",
                                    "page_num": _current_page,
                                    "instruction": "Dibujá un rectángulo sobre la zona de la mesada de mármol",
                                })}
                                yield {"type": "done", "content": ""}
                                logging.info(f"[visual-pages] Page {_current_page}: showing zone selector to operator")
                                return
                            # If image save failed, fall through to auto-select

                        selected = auto_select_zone(zones, _zone_default, _zone_default_bbox)
                        if selected:
                            _pd["selected_zone"] = selected
                            _pd["zone_was_auto"] = True
                            _page_data[_page_key] = _pd
                            _bd["page_data"] = _page_data
                            logging.info(f"[visual-pages] Page {_current_page}: auto-selected zone '{selected['name']}'")

                    # STEP C: Extract tipología from zone crop
                    if "selected_zone" in _pd and "tipologias" not in _pd:
                        zone = _pd["selected_zone"]
                        bbox = zone.get("bbox", [0, 0, 700, 700])
                        logging.info(f"[visual-pages] Cropping zone '{zone['name']}' bbox={bbox} page={_current_page}")

                        # If bbox covers less than 30% of full page → use full page instead
                        bbox_area = abs(bbox[2] - bbox[0]) * abs(bbox[3] - bbox[1])
                        page_area = 700 * 700  # Approximate full page at 200 DPI
                        if bbox_area / max(page_area, 1) < 0.30:
                            logging.warning(f"[visual-pages] bbox covers only {bbox_area/page_area*100:.0f}% — using full page crop instead")
                            crop_instructions = []  # Empty = full page thumbnail
                        else:
                            crop_instructions = [{"label": zone["name"],
                                                  "x1": bbox[0], "y1": bbox[1],
                                                  "x2": bbox[2], "y2": bbox[3]}]

                        try:
                            crop_result = await _read_plan_fn(
                                _bd.get("pdf_filename", plan_filename or ""),
                                crop_instructions,
                                page=_current_page,
                            )
                        except Exception as e:
                            logging.error(f"[visual-pages] Crop failed page {_current_page}: {e}")
                            crop_result = []

                        # Claude extracts tipología from crop
                        if crop_result:
                            extraction_content = list(crop_result) if isinstance(crop_result, list) else []
                            extraction_content.append({
                                "type": "text",
                                "text": (
                                    f"Extraer tipología de esta zona (página {_current_page}). "
                                    f"Solo JSON con tipologias. No calcular m². "
                                    f"Filtrar SOLO sección MESADAS."
                                ),
                            })

                            # Load cotas guide from disk
                            _cotas_guide = ""
                            try:
                                _cotas_path = Path(__file__).parent.parent.parent.parent / "rules" / "plan-reading-cotas.md"
                                if _cotas_path.exists():
                                    _cotas_guide = _cotas_path.read_text(encoding="utf-8")
                                    logging.info(f"[visual-pages] Cotas guide loaded: True | length={len(_cotas_guide)}")
                                else:
                                    logging.warning(f"[visual-pages] Cotas guide NOT FOUND at {_cotas_path}")
                            except Exception as e:
                                logging.warning(f"[visual-pages] Cotas guide load error: {e}")

                            _extraction_system = (
                                "Estás analizando una vista cenital (desde arriba) de una cocina.\n"
                                "En esta vista las mesadas aparecen como rectángulos sombreados pegados a las paredes.\n"
                                "Vas a ver piletas (rectángulos con óvalo), anafes (círculos sobre mesada), y cotas numéricas.\n\n"
                                "FOCALIZATE ÚNICAMENTE en la geometría de la piedra (mesada):\n"
                                "- Medir los rectángulos sombreados que representan la mesada\n"
                                "- Leer cotas que estén sobre o junto a esos rectángulos\n"
                                "- Contar piletas y anafes que estén SOBRE la mesada\n\n"
                                "NO usar medidas de:\n"
                                "- Vistas de perfil lateral (cortes) — esas muestran el mueble, no la piedra desde arriba\n"
                                "- Objetos que no son piedra: heladera, microondas, lavarropas, horno\n"
                                "- Muebles bajo mesada (melamina/carpintería)\n"
                                "- Ancho total del ambiente\n\n"
                                "Si una medida no se puede leer con claridad → marcar como ambigua.\n\n"
                                "Responder ÚNICAMENTE con JSON usando EXACTAMENTE este schema:\n"
                                '{"material_text": "...", "tipologias": [{"id": "DC-02", "qty": 2, '
                                '"shape": "L", "depth_m": 0.62, "segments_m": [2.35, 1.15], '
                                '"backsplash_ml": 4.12, "embedded_sink_count": 1, "hob_count": 1, '
                                '"notes": [], "extraction_method": "direct_read", "page": 1}]}\n\n'
                                "Reglas de campos:\n"
                                "- shape: 'L' si tiene retorno con cota visible, 'linear' si es recta, 'U' si cubre 3 paredes, 'unknown' si ambiguo\n"
                                "- segments_m: en METROS (no cm). Para L: [tramo principal, retorno]. Para linear: [largo total]. "
                                "Para U: [tramo_izq, tramo_fondo_neto, tramo_der] — fondo ya con esquinas restadas\n"
                                "- depth_m: profundidad en METROS (no cm). Típico: 0.55-0.65\n"
                                "- embedded_sink_count: piletas empotradas por unidad (leer de simbología sa-01, etc)\n"
                                "- hob_count: anafes por unidad. Mesada continua + anafe empotrado = 1\n"
                                "- extraction_method: 'direct_read' si la cota es visible, 'inferred' si se dedujo\n"
                                "- NO calcular m² — el código lo hace\n\n"
                            )
                            if _cotas_guide:
                                _extraction_system += f"GUÍA COMPLETA DE LECTURA DE COTAS:\n{_cotas_guide}\n"

                            logging.info(f"[visual-pages] Crop content blocks: {len(extraction_content)}")
                            logging.info(f"[visual-pages] Extraction system prompt length: {len(_extraction_system)}")

                            try:
                                extraction_resp = await self.client.messages.create(
                                    model="claude-opus-4-6",
                                    max_tokens=1000,
                                    system=_extraction_system,
                                    messages=[{"role": "user", "content": extraction_content}],
                                )
                                resp_text = extraction_resp.content[0].text if extraction_resp.content else ""
                                logging.info(f"[visual-pages] Extraction response raw: {resp_text[:1000]}")
                                page_parsed = parse_visual_extraction(resp_text)
                                logging.info(f"[visual-pages] parse_visual_extraction result: {page_parsed is not None}, tipologias: {len(page_parsed.get('tipologias', [])) if page_parsed else 0}")
                            except Exception as e:
                                logging.error(f"[visual-pages] Extraction failed page {_current_page}: {e}")
                                page_parsed = None

                            if page_parsed and page_parsed.get("tipologias"):
                                tips = page_parsed["tipologias"]
                                # Compute confidence + Fix C second pass within zone bbox
                                for t in tips:
                                    conf = compute_field_confidence(t)
                                    t["_confidence"] = conf.to_dict()

                                # Second pass for doubtful tipologías (within same zone crop)
                                _field_confs = {t.get("id", ""): t.get("_confidence", {}) for t in tips}
                                ids_needing = get_tipologias_needing_second_pass(tips, _field_confs)
                                for tid in ids_needing[:3]:
                                    try:
                                        existing = _copy.deepcopy(next((t for t in tips if t.get("id") == tid), {}))
                                        existing.pop("_confidence", None)
                                        focused_resp = await self.client.messages.create(
                                            model="claude-opus-4-6",
                                            max_tokens=300,
                                            system=(
                                                f"Verificar tipología {tid}. "
                                                f"Extracción anterior: {json.dumps(existing, ensure_ascii=False)}. "
                                                f"Corregir shape/segments_m/depth_m. Solo JSON."
                                            ),
                                            messages=[{"role": "user", "content": extraction_content}],
                                        )
                                        sp_text = focused_resp.content[0].text if focused_resp.content else ""
                                        sp_data = parse_focused_response(sp_text)
                                        if sp_data:
                                            tips = merge_second_pass(tips, sp_data, tid)
                                            logging.info(f"[visual-pages] Second pass {tid}: {sp_data.get('second_pass_notes', 'updated')}")
                                    except Exception as e:
                                        logging.error(f"[visual-pages] Second pass {tid} failed: {e}")

                                # Compute geometry for this page's tipologías
                                mat_res_dict = _bd.get("material_resolution", {})
                                mat_res = MaterialResolution(**mat_res_dict) if mat_res_dict else resolve_visual_materials("")
                                geo = compute_visual_geometry(tips, mat_res)

                                _pd["tipologias"] = tips
                                _pd["geometries"] = [
                                    {"id": g.id, "m2_unit": g.m2_unit, "m2_total": g.m2_total,
                                     "backsplash_ml_unit": g.backsplash_ml_unit,
                                     "backsplash_m2_total": g.backsplash_m2_total,
                                     "physical_pieces_total": g.physical_pieces_total}
                                    for g in geo.tipologias
                                ]
                            else:
                                # No tipologías extracted
                                # If using zone_default_bbox and it failed → retry or skip
                                _retries = _pd.get("zone_selector_retries", 0)
                                if _bd.get("zone_default_bbox") and _current_page > 1 and _retries < 2:
                                    logging.warning(f"[visual-pages] zone_default_bbox produced no tipologías on page {_current_page} (retry {_retries + 1}/2)")
                                    _pd["zone_default_failed"] = True
                                    _pd["zone_selector_retries"] = _retries + 1
                                    # Remove selected_zone to trigger re-selection with full page
                                    _pd.pop("selected_zone", None)
                                    _page_data[_page_key] = _pd
                                    _bd["page_data"] = _page_data
                                elif _bd.get("zone_default_bbox") and _current_page > 1 and _retries >= 2:
                                    logging.warning(f"[visual-pages] zone_default_bbox failed {_retries} times on page {_current_page} — auto-skipping")
                                    _pd["tipologias"] = []
                                    _pd["geometries"] = []
                                    _pd["confirmed"] = True
                                    _pd["skipped"] = True
                                    _page_data[_page_key] = _pd
                                    _bd["page_data"] = _page_data
                                else:
                                    _pd["tipologias"] = []
                                    _pd["geometries"] = []

                            _page_data[_page_key] = _pd
                            _bd["page_data"] = _page_data

                    # STEP D: Show page confirmation to operator
                    if "tipologias" in _pd and not _pd.get("confirmed"):
                        try:
                            tips = _pd.get("tipologias", [])
                            zone = _pd.get("selected_zone", {"name": "?"})
                            zone_auto = _pd.get("zone_was_auto", False)

                            # Build TipologiaGeometry objects for render
                            mat_res_dict = _bd.get("material_resolution", {})
                            try:
                                mat_res = MaterialResolution(**mat_res_dict) if mat_res_dict else resolve_visual_materials("")
                            except Exception as e:
                                logging.error(f"[visual-pages] MaterialResolution init failed: {e}, dict={mat_res_dict}")
                                mat_res = resolve_visual_materials("")
                            geo_full = compute_visual_geometry(tips, mat_res) if tips else None
                            geo_list = geo_full.tipologias if geo_full else []

                            confirmation_text = render_page_confirmation(
                                _current_page, _total_pages, zone, tips, geo_list, zone_auto
                            )
                            yield {"type": "text", "content": confirmation_text}
                        except Exception as e:
                            logging.error(f"[visual-pages] STEP D failed: {e}", exc_info=True)
                            yield {"type": "text", "content": f"Error procesando página {_current_page}: {str(e)}"}

                        _bd["building_step"] = f"visual_page_{_current_page}_confirm"
                        _bd["page_data"] = _page_data
                        try:
                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"[visual-pages] Failed to persist page {_current_page}: {e}")

                        _visual_builder_done = True
                        assistant_messages.append({
                            "role": "assistant",
                            "content": _serialize_content(final_message.content),
                        })
                        break

                    # Shouldn't reach here — fallback
                    logging.warning(f"[visual-pages] Unexpected state: step={_step}, page={_current_page}")
                    yield {"type": "text", "content": full_text}

                elif needs_vision and pdf_has_images and full_text and not is_visual_building:
                    # Non-building visual PDF (simple plan, single page) — flush text
                    yield {"type": "text", "content": full_text}
                    logging.info(f"[visual-pdf] Flushed {len(full_text)} chars (non-building visual)")

                _suppress_text = False

                # ── Guardrail: Paso 1 must use list_pieces ──
                # If this is likely Paso 1 (no breakdown yet, no calculate_quote called),
                # and list_pieces was never called, force a retry with explicit instruction.
                if not _list_pieces_called and not _list_pieces_retry_done and not is_building:
                    # Skip guardrail for edificio — data comes from deterministic pipeline, not list_pieces
                    try:
                        _gq = await db.execute(select(Quote).where(Quote.id == quote_id))
                        _gquote = _gq.scalar_one_or_none()
                        _has_breakdown = _gquote and _gquote.quote_breakdown
                    except Exception:
                        _has_breakdown = True  # On error, don't block
                    # Check if any text mentions pieces/m² (Paso 1 content)
                    _resp_text = "".join(b.text for b in final_message.content if hasattr(b, "text") and b.text)
                    _looks_like_paso1 = any(kw in _resp_text.lower() for kw in ["m²", "m2", "pieza", "mesada", "confirma"])
                    if not _has_breakdown and _looks_like_paso1:
                        _list_pieces_retry_done = True
                        logging.warning(f"[guardrail] Paso 1 without list_pieces for {quote_id} — forcing retry")
                        # Inject correction and continue the loop
                        assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
                        assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                            "[SISTEMA — ERROR PASO 1] ⛔ Mostraste piezas/m² SIN llamar a list_pieces. "
                            "DEBÉS llamar list_pieces con las piezas y usar sus valores EXACTOS (labels + total_m2). "
                            "Volvé a mostrar la tabla usando list_pieces. NO calcular m² manualmente."
                        )}]})
                        _loop_iterations += 1
                        continue

                assistant_messages.append({
                    "role": "assistant",
                    "content": _serialize_content(final_message.content),
                })
                break

            # Process tool calls
            tool_results = []
            for tool_use in tool_use_blocks:
                if tool_use.name == "list_pieces":
                    _list_pieces_called = True
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
                    elif isinstance(result, list):
                        logging.info(f"🔧 TOOL RESULT [{quote_id}] {tool_use.name}: {len(result)} content blocks")
                except Exception:
                    pass

                # ── M2 surface validator: compare list_pieces total vs planilla ──
                if tool_use.name == "list_pieces" and isinstance(result, dict) and result.get("ok"):
                    _lp_m2 = result.get("total_m2", 0)
                    if _expected_m2 is not None and _expected_m2 > 0:
                        _m2_diff = abs(_lp_m2 - _expected_m2)
                        if _m2_diff > 0.1:
                            result["_m2_validation_error"] = (
                                f"⛔ SUPERFICIE NO COINCIDE: tus piezas suman {_lp_m2:.2f} m² "
                                f"pero la planilla dice {_expected_m2:.2f} m². "
                                f"Revisá las cotas del plano y corregí las medidas."
                            )
                            logging.warning(f"[m2-validator] MISMATCH: pieces={_lp_m2:.2f} vs planilla={_expected_m2:.2f} (diff={_m2_diff:.2f})")
                        else:
                            logging.info(f"[m2-validator] OK: pieces={_lp_m2:.2f} vs planilla={_expected_m2:.2f} (diff={_m2_diff:.2f})")

                # read_plan returns native content blocks (list of image/text dicts)
                # to avoid inflating context with base64 inside JSON strings.
                # All other tools return dicts that get JSON-serialized.
                if isinstance(result, list):
                    # Native content blocks (image + text) — pass directly
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result,
                    })
                else:
                    try:
                        result_json = json.dumps(result, ensure_ascii=False)
                    except (TypeError, ValueError) as e:
                        logging.error(f"JSON serialization error for tool {tool_use.name}: {e}")
                        result_json = json.dumps({"ok": False, "error": f"Error serializando resultado de {tool_use.name}"}, ensure_ascii=False)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_json,
                    })

            assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
            assistant_messages.append({"role": "user", "content": tool_results})

            # Track if this iteration used visual tools (preserve context for next iteration)
            _last_had_visual_tool = any(t.name in VISUAL_TOOLS for t in tool_use_blocks)

            # Suppress text streaming during visual tool loops (hide monologue from operator)
            if _last_had_visual_tool:
                _suppress_text = True
                # Count read_plan calls and enforce limit
                for t in tool_use_blocks:
                    if t.name == "read_plan":
                        _read_plan_calls += 1
                if _read_plan_calls >= MAX_READ_PLAN_CALLS:
                    logging.warning(f"[read_plan limit] Hit {MAX_READ_PLAN_CALLS} calls — forcing analysis with what we have")
                    assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
                    assistant_messages.append({"role": "user", "content": tool_results})
                    assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                        f"[SISTEMA] Alcanzaste el límite de {MAX_READ_PLAN_CALLS} llamadas a read_plan. "
                        "DEJÁ de hacer crops. Usá TODA la información que ya extrajiste de las páginas "
                        "y del PDF inline para dar tu análisis consolidado. Presentá: tipologías, cantidades, "
                        "medidas extraídas, material, notas, y preguntas comerciales faltantes. NO hagas más crops."
                    )}]})
                    await asyncio.sleep(0.1)
                    continue

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

        # OPT-05: Per-quote cost summary + save to DB
        # Pricing: Sonnet input=$3/1M, output=$15/1M, cache_read=$0.30/1M, cache_write=$3.75/1M
        #          Opus input=$15/1M, output=$75/1M
        used_opus = has_plan  # First iteration used Opus if plan was attached
        # Approximate: treat all tokens as Sonnet pricing (Opus is only iter 0)
        cost_input = _total_input_tokens * 3.0 / 1_000_000
        cost_output = _total_output_tokens * 15.0 / 1_000_000
        cost_cache_read = _total_cache_read * 0.30 / 1_000_000
        cost_cache_write = _total_cache_write * 3.75 / 1_000_000
        total_cost = cost_input + cost_output + cost_cache_read + cost_cache_write
        # Opus surcharge for first iteration (~5x input, ~5x output)
        if used_opus and _loop_iterations > 0:
            # Rough estimate: first iteration was ~1/N of total tokens at Opus pricing
            opus_fraction = 1.0 / max(_loop_iterations, 1)
            total_cost += opus_fraction * (cost_input * 4 + cost_output * 4)  # 5x - 1x already counted

        logging.info(
            f"QUOTE COST SUMMARY [{quote_id}] — "
            f"iterations: {_loop_iterations}, "
            f"total_input: {_total_input_tokens}, "
            f"total_output: {_total_output_tokens}, "
            f"cache_read: {_total_cache_read}, "
            f"cache_write: {_total_cache_write}, "
            f"cost_usd: ${total_cost:.4f}"
        )

        # Save usage to DB
        try:
            from app.models.usage import TokenUsage
            usage_record = TokenUsage(
                quote_id=quote_id,
                input_tokens=_total_input_tokens,
                output_tokens=_total_output_tokens,
                cache_read_tokens=_total_cache_read,
                cache_write_tokens=_total_cache_write,
                model="opus+sonnet" if used_opus else "sonnet",
                cost_usd=round(total_cost, 6),
                iterations=_loop_iterations,
            )
            db.add(usage_record)
            await db.commit()
        except Exception as e:
            logging.warning(f"Could not save usage record: {e}")

        logging.info(f"[stream_chat] Yielding done for quote {quote_id}")
        yield {"type": "done", "content": ""}

    async def _execute_tool(self, name: str, inputs: dict, quote_id: str, db: AsyncSession, conversation_history: list | None = None, current_user_message: str = "") -> dict:
        logging.info(f"Tool call: {name} | quote: {quote_id}")
        if name == "list_pieces":
            # Detect is_edificio from the breakdown if persisted
            _is_edif = False
            try:
                _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
                _q = _qr.scalar_one_or_none()
                if _q:
                    _bd = _q.quote_breakdown or {}
                    _is_edif = bool(_bd.get("is_edificio") or _bd.get("building_step"))
            except Exception:
                pass
            result = list_pieces(inputs["pieces"], is_edificio=_is_edif)
            # ── Persist Paso 1 pieces for Paso 2 consistency guardrail ──
            try:
                _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
                _q = _qr.scalar_one_or_none()
                if _q:
                    _bd = dict(_q.quote_breakdown or {})
                    _bd["paso1_pieces"] = inputs["pieces"]
                    _bd["paso1_total_m2"] = result.get("total_m2")
                    await db.execute(update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd))
                    await db.commit()
                    logging.info(f"[paso1] Persisted {len(inputs['pieces'])} pieces, total_m2={result.get('total_m2')}")
            except Exception as e:
                logging.warning(f"[paso1] Failed to persist pieces: {e}")
            return result
        elif name == "catalog_lookup":
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
                mat_name = (qdata.get("material_name") or "").strip().upper()
                if idx == 0:
                    target_qid = quote_id
                else:
                    # Check if calculate_quote already created a quote for this material
                    from sqlalchemy import and_
                    target_qid = None
                    try:
                        client = qdata.get("client_name", cur_quote.client_name if cur_quote else "")
                        existing = await db.execute(select(Quote).where(Quote.client_name == client))
                        for eq in existing.scalars().all():
                            eq_mat = (eq.material or "").strip().upper()
                            if eq.id != quote_id and (eq_mat == mat_name or mat_name in eq_mat or eq_mat in mat_name):
                                target_qid = eq.id
                                logging.info(f"Reusing quote {target_qid} for material: {mat_name}")
                                break
                    except Exception as e:
                        logging.warning(f"Could not search for existing quote: {e}")

                    if not target_qid:
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
                # Read existing drive_url before overwriting (preserve if new upload fails)
                _qr = await db.execute(select(Quote).where(Quote.id == target_qid))
                _cur = _qr.scalar_one_or_none()
                existing_drive_url = _cur.drive_url if _cur else None

                first_drive_url = None
                first_drive_file_id = None
                _drive_pdf_url = None
                _drive_excel_url = None
                if result.get("ok"):
                    # Only promote status to VALIDATED on first generation
                    # (draft/pending). On regeneration (already validated/sent),
                    # preserve current status — operator controls transitions.
                    doc_values: dict = {
                        "pdf_url": result.get("pdf_url"),
                        "excel_url": result.get("excel_url"),
                    }
                    if not _cur or _cur.status in (
                        QuoteStatus.DRAFT, QuoteStatus.PENDING
                    ):
                        doc_values["status"] = QuoteStatus.VALIDATED.value
                    await db.execute(
                        update(Quote).where(Quote.id == target_qid).values(**doc_values)
                    )

                    # Upload PDF + Excel to Drive individually + build files_v2
                    # NOTE: old Drive files are deleted AFTER successful upload (not before)
                    from app.modules.agent.tools.drive_tool import upload_single_file_to_drive, delete_drive_file
                    from app.core.static import OUTPUT_DIR as _FOUT
                    old_drive_file_id = _cur.drive_file_id if _cur else None
                    files_v2_items = []
                    first_drive_url = None
                    first_drive_file_id = None
                    _drive_pdf_url = None
                    _drive_excel_url = None
                    mat_label = (qdata.get("material_name") or "").replace(" ", "_").lower()[:30]
                    subfolder = qdata.get("client_name", "")

                    for kind, url_key in [("pdf", "pdf_url"), ("excel", "excel_url")]:
                        local_url = result.get(url_key)
                        if not local_url:
                            continue
                        local_path = str(_FOUT / local_url.replace("/files/", "", 1)) if local_url.startswith("/files/") else ""
                        filename = local_url.split("/")[-1] if local_url else ""

                        drive_info = {}
                        if local_path:
                            try:
                                import os as _os_drive
                                _file_size = _os_drive.path.getsize(local_path) if _os_drive.path.exists(local_path) else -1
                                logging.info(f"Drive upload starting: {kind} | path={local_path} | size={_file_size} bytes | subfolder={subfolder}")
                                dr = await upload_single_file_to_drive(local_path, subfolder)
                                if dr.get("ok"):
                                    drive_info = {
                                        "drive_file_id": dr["file_id"],
                                        "drive_url": dr["drive_url"],
                                        "drive_download_url": dr["drive_download_url"],
                                    }
                                    if not first_drive_url:
                                        first_drive_url = dr["drive_url"]
                                        first_drive_file_id = dr["file_id"]
                                    if kind == "pdf":
                                        _drive_pdf_url = dr["drive_url"]
                                    elif kind == "excel":
                                        _drive_excel_url = dr["drive_url"]
                                    logging.info(f"Drive upload OK: {kind} | file_id={dr['file_id']} | url={dr['drive_url']}")
                                else:
                                    logging.error(f"Drive upload returned error: {kind} | {dr.get('error', 'unknown')}")
                            except Exception as e:
                                logging.error(f"Drive upload EXCEPTION for {filename}: {e}", exc_info=True)

                        files_v2_items.append({
                            "kind": kind,
                            "scope": "self",
                            "owner_quote_id": target_qid,
                            "file_key": f"{mat_label}:{kind}",
                            "filename": filename,
                            "local_path": local_path,
                            "local_url": local_url,
                            **({f"drive_{k}": v for k, v in drive_info.items()} if drive_info else {}),
                        })

                    # Delete old Drive file ONLY after new upload succeeded
                    if first_drive_url and old_drive_file_id:
                        try:
                            await delete_drive_file(old_drive_file_id)
                            logging.info(f"Deleted old Drive file {old_drive_file_id} for quote {target_qid}")
                        except Exception as e:
                            logging.warning(f"Could not delete old Drive file {old_drive_file_id}: {e}")

                    # Persist files_v2 + legacy drive_url
                    try:
                        # Re-read quote for fresh breakdown (previous commit expired _cur)
                        _fresh_r = await db.execute(select(Quote).where(Quote.id == target_qid))
                        _fresh_q = _fresh_r.scalar_one_or_none()
                        _cur_bd = dict(_fresh_q.quote_breakdown) if _fresh_q and _fresh_q.quote_breakdown else {}
                        _cur_bd["files_v2"] = {"items": files_v2_items}
                        drive_update = {"quote_breakdown": _cur_bd}
                        if first_drive_url:
                            drive_update["drive_url"] = first_drive_url
                            drive_update["drive_file_id"] = first_drive_file_id
                        if _drive_pdf_url:
                            drive_update["drive_pdf_url"] = _drive_pdf_url
                        if _drive_excel_url:
                            drive_update["drive_excel_url"] = _drive_excel_url
                        await db.execute(
                            update(Quote).where(Quote.id == target_qid).values(**drive_update)
                        )
                    except Exception as e:
                        logging.warning(f"files_v2 persist failed for {target_qid}: {e}")

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

                # Use new drive_url if upload succeeded, else preserve existing
                final_drive_url = first_drive_url or existing_drive_url
                all_results.append({
                    "quote_id": target_qid,
                    "material": qdata.get("material_name"),
                    "ok": result.get("ok", False),
                    "pdf_url": result.get("pdf_url"),
                    "excel_url": result.get("excel_url"),
                    "drive_url": final_drive_url if result.get("ok") else None,
                    "drive_pdf_url": _drive_pdf_url,
                    "drive_excel_url": _drive_excel_url,
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
            # Create a NEW quote only when operator explicitly wants alternatives
            # (quote already has docs/validated). In DRAFT without docs, overwrite
            # the same quote — operator is editing, not adding alternatives.
            try:
                check_q = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                check_quote = check_q.scalar_one_or_none()
                has_docs = check_quote and (check_quote.pdf_url or check_quote.status in ("validated", "sent"))
                if check_quote and check_quote.quote_breakdown and has_docs:
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

            # ── Pileta signal: structured field first, keywords fallback ──
            if not inputs.get("pileta"):
                # 1. Structured signal: read pileta field from Quote model (set by chatbot)
                try:
                    _pq = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                    _pileta_quote = _pq.scalar_one_or_none()
                    if _pileta_quote and _pileta_quote.pileta:
                        inputs["pileta"] = _pileta_quote.pileta
                        logging.info(f"Pileta from quote field: {_pileta_quote.pileta} for {save_to_qid}")
                except Exception as e:
                    logging.warning(f"Could not read pileta field from quote {save_to_qid}: {e}")

            if not inputs.get("pileta"):
                # 2. Keyword fallback: scan conversation for pileta/bacha mentions
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
                if any(kw in all_text for kw in ["bacha", "pileta", "cotizar bacha", "con bacha",
                                                  "compra la bacha", "compra bacha", "compra pileta",
                                                  "la compra en", "la pide"]):
                    inputs["pileta"] = "empotrada_johnson"
                    logging.warning(f"Auto-injected pileta=empotrada_johnson from conversation keywords for {save_to_qid}")

            # ── skip_flete: detect "retiro en fábrica" / "lo busco yo" ──
            if not inputs.get("skip_flete"):
                _all_user_text = current_user_message.lower()
                if conversation_history:
                    for msg in conversation_history:
                        if msg.get("role") == "user":
                            c = msg.get("content", "")
                            if isinstance(c, str):
                                _all_user_text += " " + c.lower()
                            elif isinstance(c, list):
                                for blk in c:
                                    if isinstance(blk, dict) and blk.get("type") == "text":
                                        _all_user_text += " " + blk.get("text", "").lower()
                _skip_phrases = ["lo retiro", "retiro yo", "retiro en", "voy a buscar", "lo busco",
                                 "retira en fábrica", "retira en fabrica", "sin flete", "no necesita flete"]
                if any(phrase in _all_user_text for phrase in _skip_phrases):
                    inputs["skip_flete"] = True
                    logging.info(f"Auto-set skip_flete=True from conversation keywords for {save_to_qid}")

            # ── Paso 1 ↔ Paso 2 consistency guardrail ──
            # Two layers:
            #   A) paso1_pieces persisted by list_pieces (residencial — list_pieces siempre se llama)
            #   B) operator_declared_m2 parseado del texto del operador (edificios — list_pieces deshabilitado)
            try:
                _gq = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                _gquote = _gq.scalar_one_or_none()
                if _gquote:
                    _gbd = _gquote.quote_breakdown or {}

                    # Calculate m2 of what Claude is trying to pass now
                    _current_m2 = 0
                    for _p in inputs.get("pieces", []):
                        _pl = _p.get("largo", 0) or 0
                        _pp = _p.get("prof", 0) or _p.get("dim2", 0) or _p.get("alto", 0) or 0
                        _pq = _p.get("quantity", 1) or 1
                        _current_m2 += _pl * _pp * _pq

                    # Layer A: residencial (list_pieces persisted)
                    _paso1_pieces = _gbd.get("paso1_pieces")
                    _paso1_m2 = _gbd.get("paso1_total_m2") or 0
                    if _paso1_pieces:
                        _diff_m2 = abs(_current_m2 - _paso1_m2)
                        _diff_count = abs(len(inputs.get("pieces", [])) - len(_paso1_pieces))
                        if _diff_m2 > 0.5 or _diff_count > 0:
                            logging.error(
                                f"[guardrail-A] PASO1↔PASO2 mismatch for {save_to_qid}: "
                                f"paso1={len(_paso1_pieces)}p/{_paso1_m2:.2f}m² "
                                f"vs paso2={len(inputs.get('pieces', []))}p/{_current_m2:.2f}m². "
                                "OVERRIDING with paso1 pieces."
                            )
                            inputs["pieces"] = _paso1_pieces

                    # Layer B: edificios — parse operator text for declared m²
                    # Examples: "TOTAL MATERIAL: 66.57 m²", "Total: 74.10 m²", "Subtotal: 58.66 m²"
                    import re as _re_m2op
                    _op_text = ""
                    if conversation_history:
                        for _m in conversation_history:
                            if _m.get("role") == "user":
                                _c = _m.get("content", "")
                                if isinstance(_c, str):
                                    _op_text += " " + _c
                                elif isinstance(_c, list):
                                    for _b in _c:
                                        if isinstance(_b, dict) and _b.get("type") == "text":
                                            _op_text += " " + _b.get("text", "")
                    _op_text += " " + (current_user_message or "")

                    _total_patterns = [
                        r'total\s+material[:\s]+([\d.,]+)\s*m[²2]',
                        r'material\s+total[:\s]+([\d.,]+)\s*m[²2]',
                        r'total[:\s]+([\d.,]+)\s*m[²2]',
                    ]
                    _declared_m2 = None
                    for _pat in _total_patterns:
                        _m = _re_m2op.search(_pat, _op_text, _re_m2op.IGNORECASE)
                        if _m:
                            try:
                                _declared_m2 = float(_m.group(1).replace(".", "").replace(",", ".")
                                                     if _m.group(1).count(",") == 1 and _m.group(1).count(".") > 1
                                                     else _m.group(1).replace(",", "."))
                                break
                            except ValueError:
                                continue

                    if _declared_m2 and _declared_m2 > 1:
                        _diff_op = abs(_current_m2 - _declared_m2)
                        _diff_pct = _diff_op / _declared_m2
                        # Abort only on significant mismatch (>10% or >2m²)
                        if _diff_pct > 0.10 and _diff_op > 2.0:
                            logging.error(
                                f"[guardrail-B] Operator declared {_declared_m2:.2f} m² but agent is "
                                f"passing {_current_m2:.2f} m² ({_diff_pct*100:.0f}% diff). ABORTING calculate_quote."
                            )
                            # Return error to agent so it re-reads the message
                            return {
                                "ok": False,
                                "error": (
                                    f"⛔ El despiece que pasaste a calculate_quote ({_current_m2:.2f} m²) "
                                    f"NO coincide con el total declarado por el operador ({_declared_m2:.2f} m²). "
                                    "Re-leer el mensaje ORIGINAL del operador (NO los ejemplos) y pasar "
                                    "EXACTAMENTE las piezas listadas ahí. En edificio son múltiples tipologías "
                                    "(DC-02 × 2, DC-03 × 6, etc.), NO inventes datos residenciales."
                                ),
                                "_guardrail_aborted": True,
                                "_current_m2": _current_m2,
                                "_declared_m2": _declared_m2,
                            }
            except Exception as e:
                logging.warning(f"[guardrail] paso1↔paso2 check failed: {e}")

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

                # Build deterministic Paso 2 text — Claude must use this verbatim
                from app.modules.quote_engine.calculator import build_deterministic_paso2
                calc_result["_paso2_rendered"] = build_deterministic_paso2(calc_result)
                logging.info(f"Deterministic Paso 2 built for {save_to_qid} ({len(calc_result['_paso2_rendered'])} chars)")

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
