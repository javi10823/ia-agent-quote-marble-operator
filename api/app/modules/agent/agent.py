import anthropic
import asyncio
import json
import base64
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from app.core.config import settings
from app.models.quote import Quote
from app.modules.agent.tools.catalog_tool import catalog_lookup, check_stock
from app.modules.agent.tools.plan_tool import read_plan
from app.modules.agent.tools.document_tool import generate_documents
from app.modules.agent.tools.drive_tool import upload_to_drive

BASE_DIR = Path(__file__).parent.parent.parent.parent

# ── BUILDING DETECTION ───────────────────────────────────────────────────────

BUILDING_KEYWORDS = [
    "edificio", "edificios", "departamento", "departamentos",
    "unidades", "torre", "torres", "constructora", "consorcio",
    "cantidad:", "cantidad :", "pisos", "obra nueva",
]


def _detect_building(user_message: str) -> bool:
    text = user_message.lower()
    return any(kw in text for kw in BUILDING_KEYWORDS)


# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────

def build_system_prompt(has_plan: bool = False, is_building: bool = False) -> list:
    """
    Build system prompt as a list of content blocks with cache_control.
    Stable core content is cached (5 min TTL). Conditional content is not cached.
    Cached tokens don't count toward the rate limit on subsequent requests.
    """
    context = (BASE_DIR / "CONTEXT.md").read_text(encoding="utf-8")
    rules_dir = BASE_DIR / "rules"

    # Stable core — always loaded, forms the cached block
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

    stable_text = "\n\n---\n\n".join([context] + core_rules)

    # Conditional content — loaded based on context
    conditional_parts = []

    if is_building:
        bldg_path = rules_dir / "quote-process-buildings.md"
        if bldg_path.exists():
            conditional_parts.append(f"## {bldg_path.stem}\n\n{bldg_path.read_text(encoding='utf-8')}")

    if has_plan:
        plan_path = rules_dir / "plan-reading.md"
        if plan_path.exists():
            conditional_parts.append(f"## {plan_path.stem}\n\n{plan_path.read_text(encoding='utf-8')}")

    # Examples — 1 by default, add building example if needed
    examples_dir = BASE_DIR / "examples"
    example_names = ["quote-030"]
    if is_building:
        example_names.append("quote-019")

    for name in example_names:
        for f in examples_dir.glob(f"{name}*.md"):
            conditional_parts.append(f.read_text(encoding="utf-8"))

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
        "name": "read_plan",
        "description": "Rasteriza un plano (PDF o imagen) a 300 DPI y hace crop individual de cada mesada para lectura precisa. SIEMPRE usar antes de interpretar cualquier plano.",
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
        "description": "Genera el PDF y Excel del presupuesto una vez confirmado por el operador.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quote_id": {"type": "string"},
                "quote_data": {
                    "type": "object",
                    "description": "Datos completos del presupuesto estructurado",
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
                                    "pieces": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    },
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
                                },
                            },
                        },
                        "total_ars": {"type": "number"},
                        "total_usd": {"type": "number"},
                    },
                    "required": ["client_name", "project", "material_name"],
                },
            },
            "required": ["quote_id", "quote_data"],
        },
    },
    {
        "name": "upload_to_drive",
        "description": "Sube el PDF y Excel generados a Google Drive en la carpeta correspondiente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quote_id": {"type": "string"},
                "client_name": {"type": "string"},
                "material": {"type": "string"},
                "date": {"type": "string"},
            },
            "required": ["quote_id", "client_name", "material", "date"],
        },
    },
]


# ── HELPERS ───────────────────────────────────────────────────────────────────

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


# ── RETRY CONFIG ─────────────────────────────────────────────────────────────

MAX_RETRIES = 5
RETRY_DELAYS = [30, 40, 50, 60, 60]


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
        system_prompt = build_system_prompt(has_plan=has_plan, is_building=is_building)

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
                media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(plan_bytes).decode(),
                    },
                })
        content.append({"type": "text", "text": user_message})

        # Append user message to history
        new_messages = messages + [{"role": "user", "content": content}]

        # Agentic loop with tool use
        assistant_messages = []
        yield {"type": "action", "content": "Leyendo catálogos y calculando..."}

        while True:
            full_text = ""
            tool_uses = []

            # Retry loop for rate limit errors
            for attempt in range(MAX_RETRIES + 1):
                try:
                    async with self.client.messages.stream(
                        model=settings.ANTHROPIC_MODEL,
                        max_tokens=8096,
                        system=system_prompt,
                        messages=new_messages + assistant_messages,
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

                    # Log cache usage if available
                    if hasattr(final_message, "usage"):
                        usage = final_message.usage
                        cache_read = getattr(usage, "cache_read_input_tokens", 0)
                        cache_create = getattr(usage, "cache_creation_input_tokens", 0)
                        logging.info(
                            f"Token usage — input: {usage.input_tokens}, "
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

                result = await self._execute_tool(
                    tool_use.name,
                    tool_use.input,
                    quote_id=quote_id,
                    db=db,
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result),
                })

            assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
            assistant_messages.append({"role": "user", "content": tool_results})

            # Cooldown between loop iterations to avoid hitting rate limit
            # on the next API call (cached tokens help, but need time window)
            yield {"type": "action", "content": "Procesando resultados..."}
            await asyncio.sleep(2)

        # Save updated messages to DB
        updated_messages = new_messages + assistant_messages
        await db.execute(
            update(Quote)
            .where(Quote.id == quote_id)
            .values(messages=updated_messages)
        )
        await db.commit()

        yield {"type": "done", "content": ""}

    async def _execute_tool(self, name: str, inputs: dict, quote_id: str, db: AsyncSession) -> dict:
        if name == "catalog_lookup":
            return catalog_lookup(inputs["catalog"], inputs["sku"])
        elif name == "check_stock":
            return check_stock(inputs["material_sku"])
        elif name == "read_plan":
            return await read_plan(inputs["filename"], inputs.get("crop_instructions", []))
        elif name == "generate_documents":
            result = await generate_documents(quote_id, inputs["quote_data"])
            if result.get("ok"):
                await db.execute(
                    update(Quote)
                    .where(Quote.id == quote_id)
                    .values(
                        client_name=inputs["quote_data"]["client_name"],
                        project=inputs["quote_data"]["project"],
                        material=inputs["quote_data"].get("material_name"),
                        total_ars=inputs["quote_data"].get("total_ars"),
                        total_usd=inputs["quote_data"].get("total_usd"),
                        pdf_url=result.get("pdf_url"),
                        excel_url=result.get("excel_url"),
                    )
                )
                await db.commit()
            return result
        elif name == "upload_to_drive":
            result = await upload_to_drive(
                quote_id,
                inputs["client_name"],
                inputs["material"],
                inputs["date"],
            )
            if result.get("ok"):
                await db.execute(
                    update(Quote)
                    .where(Quote.id == quote_id)
                    .values(drive_url=result.get("drive_url"))
                )
                await db.commit()
            return result
        else:
            return {"error": f"Tool desconocida: {name}"}
