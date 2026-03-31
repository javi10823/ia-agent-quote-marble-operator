import anthropic
import json
import base64
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

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    context = (BASE_DIR / "CONTEXT.md").read_text(encoding="utf-8")
    rules = []
    rules_dir = BASE_DIR / "rules"
    for f in sorted(rules_dir.glob("*.md")):
        rules.append(f"## {f.stem}\n\n{f.read_text(encoding='utf-8')}")

    # Load a selection of key examples
    examples = []
    examples_dir = BASE_DIR / "examples"
    key_examples = ["quote-028", "quote-030", "quote-032", "quote-033", "quote-034"]
    for name in key_examples:
        for f in examples_dir.glob(f"{name}*.md"):
            examples.append(f.read_text(encoding="utf-8"))

    return "\n\n---\n\n".join([context] + rules + examples)


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


# ── AGENT SERVICE ─────────────────────────────────────────────────────────────

class AgentService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.system_prompt = build_system_prompt()

    async def stream_chat(
        self,
        quote_id: str,
        messages: list,
        user_message: str,
        plan_bytes: Optional[bytes],
        plan_filename: Optional[str],
        db: AsyncSession,
    ) -> AsyncGenerator[dict, None]:

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
        while True:
            full_text = ""
            tool_uses = []

            async with self.client.messages.stream(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=8096,
                system=self.system_prompt,
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
                        elif event.type == "content_block_delta":
                            if hasattr(event.delta, "partial_json") and tool_uses:
                                # Accumulate tool input JSON
                                pass

                final_message = await stream.get_final_message()

            # Check if we need to handle tool calls
            tool_use_blocks = [b for b in final_message.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # No tool calls — conversation turn is done
                assistant_messages.append({
                    "role": "assistant",
                    "content": final_message.content,
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

            assistant_messages.append({"role": "assistant", "content": final_message.content})
            assistant_messages.append({"role": "user", "content": tool_results})

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
