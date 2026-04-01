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
]


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _extract_quote_info(user_message: str) -> dict:
    """Extract client name and material from user message for early DB update."""
    import re
    info = {}

    # Try to find client name after "cliente" keyword (case insensitive)
    match = re.search(r"(?:cliente|clienta)\s+(.+?)(?:\s*,|\s+con\s|\s+en\s|\s+lleva|\s+sin\s|$)", user_message, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        # Title case the name
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


# ── RETRY CONFIG ─────────────────────────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAYS = [5, 10, 15]


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
                media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/webp" if ext == ".webp" else "image/png"
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

            # Brief pause between loop iterations (minimal with Tier 1)
            await asyncio.sleep(0.1)

        # Save updated messages to DB
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

        yield {"type": "done", "content": ""}

    async def _execute_tool(self, name: str, inputs: dict, quote_id: str, db: AsyncSession) -> dict:
        logging.info(f"Tool call: {name} | quote: {quote_id}")
        if name == "catalog_lookup":
            return catalog_lookup(inputs["catalog"], inputs["sku"])
        elif name == "check_stock":
            return check_stock(inputs["material_sku"])
        elif name == "read_plan":
            return await read_plan(inputs["filename"], inputs.get("crop_instructions", []))
        elif name == "generate_documents":
            import uuid as uuid_mod
            quotes_data = inputs.get("quotes", [])
            # Backward compat: if old format with quote_data, wrap it
            if not quotes_data and "quote_data" in inputs:
                quotes_data = [inputs["quote_data"]]

            logging.info(f"generate_documents: {len(quotes_data)} material(s) to generate")

            # Validate required fields before generating
            for qdata in quotes_data:
                missing = []
                if not qdata.get("client_name"):
                    missing.append("client_name (nombre del cliente)")
                if not qdata.get("delivery_days"):
                    missing.append("delivery_days (plazo de entrega)")
                if not qdata.get("material_name"):
                    missing.append("material_name (material)")
                if missing:
                    return {
                        "ok": False,
                        "error": f"Faltan datos requeridos: {', '.join(missing)}. Pedírselos al operador antes de generar.",
                    }

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
                    await db.commit()
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
                await db.commit()

                # Generate PDF + Excel
                result = await generate_documents(target_qid, qdata)
                logging.info(f"generate_documents [{idx}] {qdata.get('material_name')}: ok={result.get('ok')}, error={result.get('error')}")

                if result.get("ok"):
                    await db.execute(
                        update(Quote).where(Quote.id == target_qid).values(
                            pdf_url=result.get("pdf_url"),
                            excel_url=result.get("excel_url"),
                            status="validated",
                        )
                    )
                    await db.commit()

                    # Delete old Drive file if exists (prevents duplicates)
                    from app.modules.agent.tools.drive_tool import delete_drive_file
                    old_quote = await db.execute(select(Quote).where(Quote.id == target_qid))
                    old_q = old_quote.scalar_one_or_none()
                    if old_q and old_q.drive_file_id:
                        delete_drive_file(old_q.drive_file_id)
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
                        await db.commit()

                all_results.append({
                    "quote_id": target_qid,
                    "material": qdata.get("material_name"),
                    "ok": result.get("ok", False),
                    "pdf_url": result.get("pdf_url"),
                    "excel_url": result.get("excel_url"),
                    "drive_url": drive_result.get("drive_url") if result.get("ok") else None,
                    "error": result.get("error"),
                })

            return {"ok": True, "generated": len(all_results), "results": all_results}

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
        else:
            return {"error": f"Tool desconocida: {name}"}
