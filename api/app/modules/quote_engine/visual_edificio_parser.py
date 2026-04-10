"""Visual edificio parser — extracts building data from CAD floor plan PDFs.

When an edificio PDF contains architectural drawings (not tabular data),
this module:
1. Rasterizes each page to an image
2. Calls Claude vision to extract structured data per page (lámina)
3. Normalizes to the same NormalizedEdificioData format used by the tabular parser
4. Detects warnings (PRELIMINAR, confirmar) and blockers (material ambiguo, failed pages)

The output feeds directly into compute_edificio_aggregates() → validate → render.

Detection mode tracing:
- building_detection_mode = "manual_override" | "tabular" | "visual_auto"
  persisted in quote_breakdown for auditability.
"""

import asyncio
import base64
import io
import json
import logging
import re
from typing import Optional

from .edificio_parser import (
    NormalizedPiece,
    NormalizedEdificioData,
)

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

EXTRACTION_MODEL = "claude-sonnet-4-20250514"
MAX_CONCURRENCY = 3
MAX_TOKENS_PER_PAGE = 4000
DPI = 200  # Balance quality vs token cost
RETRY_ATTEMPTS = 2

EXTRACTION_SYSTEM_PROMPT = """\
Sos un extractor de datos de planos arquitectónicos de mesadas de mármol/cuarzo/granito para edificios.
Extraés medidas exactas, materiales, cantidades y notas de cada lámina CAD.
Respondé SOLO con JSON válido, sin texto adicional, sin markdown, sin ```."""

EXTRACTION_USER_PROMPT = """\
Extraé los datos de esta lámina de plano CAD de cocina/mesada.

Buscá estos datos:

1. CAJETÍN (cuadro de título, generalmente abajo-derecha):
   - obra: nombre del proyecto/obra
   - lamina_id: código de lámina (ej: DC-02, DC-03)
   - titulo: título completo de la lámina
   - tipologia: tipo de unidad (ej: "Cocina 1P+8P A01")
   - pisos: qué pisos aplica (ej: "1° y 8° piso", "2° a 7° piso")
   - cantidad: número en "CANTIDAD: N" (número entero)
   - fecha: fecha del plano si visible

2. MESADAS Y PIEZAS DE PIEDRA (de las cotas en los dibujos de planta y cortes):
   Para cada pieza de mesada/encimera visible, extraé:
   - id: identificador secuencial (M01, M02, etc.)
   - tipo: "mesada" | "zocalo" | "alzada"
   - largo_cm: largo en centímetros (de las cotas del plano)
   - ancho_cm: ancho/profundidad en centímetros
   - notas: cualquier aclaración específica de esta pieza

3. MATERIAL (generalmente en sección "MESADAS" de las notas):
   - material_text: texto completo que indica material
   - Si dice "A o B" o "A ó B", marcá material_ambiguo=true y listá las opciones

4. PILETAS/BACHAS:
   - Contá cuántas se ven en el plano de esta lámina
   - Determiná tipo: si dice "PEGADOPILETA" o se ve empotrada → "empotrada"; si se apoya → "apoyo"
   - Indicá el modelo si está en la lista de artefactos (ej: "Johnson Acero Modelo LUXOR")

5. ZÓCALOS:
   - Buscá si hay zócalos marcados (generalmente h=5cm o h=7.5cm o h=10cm)
   - Extraé los largos de cada tramo de zócalo visible

6. SELLOS Y ESTADO:
   - ¿Dice "PRELIMINAR"? → es_preliminar=true
   - ¿Dice "DOCUMENTO NO VALIDO PARA CONSTRUCCION"? → es_preliminar=true
   - ¿Dice "PARA COMENTARIOS"? → es_preliminar=true

7. NOTAS MANUSCRITAS O DE DISEÑO:
   - Cualquier texto escrito a mano o anotación tipo "confirmar", "mover pileta", "definir", pregunta

Respondé con este JSON exacto (sin markdown, sin ```):
{
  "lamina_id": "string",
  "titulo": "string",
  "obra": "string",
  "tipologia": "string",
  "pisos": "string",
  "cantidad": 1,
  "fecha": "string o null",
  "material_text": "string",
  "material_ambiguo": false,
  "materiales_opciones": [],
  "es_preliminar": false,
  "piezas": [
    {
      "id": "string",
      "tipo": "mesada",
      "largo_cm": 0,
      "ancho_cm": 0,
      "espesor_cm": null,
      "pileta_count": 0,
      "pileta_tipo": null,
      "pileta_modelo": null,
      "notas": null
    }
  ],
  "zocalos": [
    {
      "id": "string",
      "largo_cm": 0,
      "alto_cm": 5,
      "notas": null
    }
  ],
  "notas_manuscritas": [],
  "notas_generales": null
}"""


# ── PDF Rasterization ───────────────────────────────────────────────────────

def rasterize_pdf_pages(plan_bytes: bytes) -> list[bytes]:
    """Convert each PDF page to a JPEG image at target DPI.

    Returns list of JPEG bytes, one per page.
    """
    from pdf2image import convert_from_bytes

    images = convert_from_bytes(plan_bytes, dpi=DPI, fmt="jpeg")
    result = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        result.append(buf.getvalue())
    logger.info(f"[visual_edificio] Rasterized {len(result)} pages at {DPI} DPI")
    return result


# ── Per-Page Claude Vision Extraction ───────────────────────────────────────

def _build_extraction_request(page_image: bytes) -> dict:
    """Build the messages.create kwargs for a single page extraction.

    Separated so asyncio.to_thread can call client.messages.create with these args.
    """
    return {
        "model": EXTRACTION_MODEL,
        "max_tokens": MAX_TOKENS_PER_PAGE,
        "system": EXTRACTION_SYSTEM_PROMPT,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(page_image).decode(),
                    },
                },
                {
                    "type": "text",
                    "text": EXTRACTION_USER_PROMPT,
                },
            ],
        }],
    }


async def _extract_single_page(
    client,
    page_image: bytes,
    page_number: int,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Extract structured data from a single PDF page using Claude vision.

    Uses asyncio.to_thread to avoid blocking the event loop with the
    synchronous Anthropic client. This ensures asyncio.gather + Semaphore
    provides real parallelism across pages.

    Returns the parsed JSON dict, or a dict with _extraction_failed=True on error.
    """
    async with semaphore:
        raw_text = ""
        request_kwargs = _build_extraction_request(page_image)
        for attempt in range(RETRY_ATTEMPTS):
            try:
                # Run sync client call in a thread to not block the event loop
                response = await asyncio.to_thread(
                    client.messages.create,
                    **request_kwargs,
                )

                raw_text = response.content[0].text.strip()
                # Strip markdown fences if present
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                    raw_text = re.sub(r"\s*```$", "", raw_text)

                parsed = json.loads(raw_text)
                parsed["_page_number"] = page_number
                parsed["_extraction_failed"] = False
                logger.info(
                    f"[visual_edificio] Page {page_number}: extracted "
                    f"lamina={parsed.get('lamina_id')}, "
                    f"cantidad={parsed.get('cantidad')}, "
                    f"{len(parsed.get('piezas', []))} piezas"
                )
                return parsed

            except json.JSONDecodeError as e:
                logger.warning(
                    f"[visual_edificio] Page {page_number} attempt {attempt+1}: "
                    f"JSON parse error: {e}"
                )
                if attempt == RETRY_ATTEMPTS - 1:
                    return {
                        "_page_number": page_number,
                        "_extraction_failed": True,
                        "_error": f"JSON parse error after {RETRY_ATTEMPTS} attempts: {str(e)[:200]}",
                        "_raw_text": raw_text[:500] if raw_text else "",
                    }
            except Exception as e:
                logger.error(
                    f"[visual_edificio] Page {page_number} attempt {attempt+1}: "
                    f"API error: {e}"
                )
                if attempt == RETRY_ATTEMPTS - 1:
                    return {
                        "_page_number": page_number,
                        "_extraction_failed": True,
                        "_error": f"API error: {str(e)[:200]}",
                    }

    # Safety fallback
    return {"_page_number": page_number, "_extraction_failed": True, "_error": "Unknown error"}


async def extract_visual_edificio(client, plan_bytes: bytes) -> list[dict]:
    """Extract structured data from all pages of a visual edificio PDF.

    Returns list of dicts, one per page. Failed pages have _extraction_failed=True.
    """
    page_images = rasterize_pdf_pages(plan_bytes)
    if not page_images:
        return []

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    # Run extractions in parallel
    tasks = [
        _extract_single_page(client, img, i + 1, semaphore)
        for i, img in enumerate(page_images)
    ]
    results = await asyncio.gather(*tasks)

    ok_count = sum(1 for r in results if not r.get("_extraction_failed"))
    fail_count = len(results) - ok_count
    logger.info(f"[visual_edificio] Extraction complete: {ok_count} OK, {fail_count} failed out of {len(results)} pages")

    return list(results)


# ── Normalization to NormalizedEdificioData ──────────────────────────────────

def build_normalized_from_visual(
    pages_data: list[dict],
) -> tuple[NormalizedEdificioData, list[str], list[str]]:
    """Convert visual extraction results to NormalizedEdificioData.

    Returns: (normalized_data, warnings, blockers)
    - warnings: non-blocking issues (PRELIMINAR, confirmar, etc.)
    - blockers: issues that PREVENT pricing (material ambiguo, failed pages)

    Policy for failed pages:
    - If ANY page fails extraction, it becomes a BLOCKER (not just a warning)
    - The operator must explicitly confirm to proceed without failed pages
    - This prevents silent partial quoting on a 25-unit building
    """
    warnings = []
    blockers = []
    all_pieces = []
    failed_pages = []

    for page in pages_data:
        page_num = page.get("_page_number", "?")

        # Handle failed pages
        if page.get("_extraction_failed"):
            failed_pages.append(page)
            continue

        lamina_id = page.get("lamina_id", f"PG-{page_num}")
        titulo = page.get("titulo", "")
        cantidad = max(int(page.get("cantidad") or 1), 1)
        material_text = page.get("material_text", "")

        # ── Warnings (non-blocking, shown before Paso 1) ──
        if page.get("es_preliminar"):
            warnings.append(
                f"Lámina {lamina_id}: PRELIMINAR / documento no válido para construcción"
            )

        for nota in page.get("notas_manuscritas", []):
            nota_str = str(nota).strip()
            if not nota_str:
                continue
            if any(kw in nota_str.lower() for kw in ["confirmar", "definir", "verificar", "?"]):
                warnings.append(f"Lámina {lamina_id}: REQUIERE CONFIRMACIÓN: \"{nota_str}\"")
            else:
                warnings.append(f"Lámina {lamina_id}: nota: \"{nota_str}\"")

        if page.get("notas_generales"):
            warnings.append(f"Lámina {lamina_id}: {page['notas_generales']}")

        # ── Blockers (prevent pricing) ──
        if page.get("material_ambiguo"):
            opciones = page.get("materiales_opciones", [])
            blocker_msg = (
                f"Material ambiguo — \"{material_text}\". "
                f"Opciones: {', '.join(opciones) if opciones else 'no detectadas'}. "
                f"El operador debe elegir antes de cotizar."
            )
            # Only add once (all pages likely have same material)
            if not any("Material ambiguo" in b for b in blockers):
                blockers.append(blocker_msg)

        # ── Pieces ──
        for pieza in page.get("piezas", []):
            pieza_id = pieza.get("id", "M01")
            largo_cm = pieza.get("largo_cm") or 0
            ancho_cm = pieza.get("ancho_cm") or 0
            largo_m = round(largo_cm / 100, 4)
            ancho_m = round(ancho_cm / 100, 4)
            m2_unit = round(largo_m * ancho_m, 4)
            m2_total = round(m2_unit * cantidad, 4)

            piece = NormalizedPiece(
                id=f"{lamina_id}-{pieza_id}",
                ubicacion=titulo,
                material=material_text,
                material_raw=material_text,
                terminacion=None,
                perforaciones_text=(
                    f"{pieza['pileta_count']} pileta {'apoyo' if pieza.get('pileta_tipo') == 'apoyo' else 'empotrada'}"
                    if pieza.get("pileta_count") else None
                ),
                aclaraciones_text=pieza.get("notas"),
                largo=largo_m,
                ancho=ancho_m,
                espesor_cm=pieza.get("espesor_cm") or 20,
                cantidad=cantidad,
                m2_calc_unit=m2_unit,
                m2_calc_total=m2_total,
                m2_pdf=None,
                pileta_count=pieza.get("pileta_count") or 0,
                pileta_type="empotrada" if pieza.get("pileta_tipo") in ("empotrada", None) and pieza.get("pileta_count") else pieza.get("pileta_tipo"),
                faldon_cm=None,
                faldon_ml_unit=None,
                faldon_ml_total=None,
                # Visual-specific metadata
                _lamina_id=lamina_id,
                _tipologia=page.get("tipologia", ""),
                _pisos=page.get("pisos", ""),
                _cantidad_lamina=cantidad,
            )
            all_pieces.append(piece)

        # ── Zócalos as pieces ──
        for zocalo in page.get("zocalos", []):
            z_id = zocalo.get("id", "Z01")
            z_largo_cm = zocalo.get("largo_cm") or 0
            z_alto_cm = zocalo.get("alto_cm") or 5
            z_largo_m = round(z_largo_cm / 100, 4)
            z_alto_m = round(z_alto_cm / 100, 4)
            z_m2_unit = round(z_largo_m * z_alto_m, 4)
            z_m2_total = round(z_m2_unit * cantidad, 4)

            piece = NormalizedPiece(
                id=f"{lamina_id}-{z_id}",
                ubicacion=titulo,
                material=material_text,
                material_raw=material_text,
                terminacion=None,
                perforaciones_text=None,
                aclaraciones_text=zocalo.get("notas"),
                largo=z_largo_m,
                ancho=z_alto_m,
                espesor_cm=20,
                cantidad=cantidad,
                m2_calc_unit=z_m2_unit,
                m2_calc_total=z_m2_total,
                m2_pdf=None,
                pileta_count=0,
                pileta_type=None,
                faldon_cm=None,
                faldon_ml_unit=None,
                faldon_ml_total=None,
                _lamina_id=lamina_id,
                _tipologia=page.get("tipologia", ""),
                _pisos=page.get("pisos", ""),
                _cantidad_lamina=cantidad,
                _is_zocalo=True,
            )
            all_pieces.append(piece)

    # ── Failed pages = BLOCKER (not just warning) ──
    # Policy: if any page fails, do NOT proceed silently.
    # Show OK vs failed, operator must confirm to continue without them.
    if failed_pages:
        page_nums = ", ".join(str(p.get("_page_number", "?")) for p in failed_pages)
        errors_detail = "; ".join(
            f"pág {p.get('_page_number', '?')}: {p.get('_error', 'error desconocido')[:100]}"
            for p in failed_pages
        )
        blockers.append(
            f"{len(failed_pages)} lámina(s) fallaron en la extracción (páginas: {page_nums}). "
            f"Detalle: {errors_detail}. "
            f"No se puede cotizar parcialmente sin confirmación explícita del operador."
        )
        # Also add as warning for visibility
        for p in failed_pages:
            warnings.append(
                f"Lámina página {p.get('_page_number', '?')}: extracción fallida — "
                f"{p.get('_error', 'error desconocido')[:150]}"
            )

    # Build NormalizedEdificioData (single "marmoleria" section with all pieces)
    norm_data = NormalizedEdificioData(
        sections=[{
            "type": "marmoleria",
            "header_row": ["ID", "Ubicación", "Largo", "Ancho", "m²", "Cant", "Material"],
            "pieces": all_pieces,
        }],
        source="visual_cad",
    )

    return norm_data, warnings, blockers


# ── Material Resolution ─────────────────────────────────────────────────────

def validate_material_choice(
    pages_data: list[dict],
    user_input: str,
) -> tuple[bool, Optional[str], list[str]]:
    """Validate operator's material choice against detected options.

    Returns: (ok, normalized_choice, available_options)
    - ok: True if the input matches one of the detected options
    - normalized_choice: the canonical option name (properly cased)
    - available_options: all options detected across pages (for error message)

    Matching rules:
    - Case-insensitive exact match
    - Case-insensitive substring match (e.g., "cuarzo" matches "Cuarzo Blanco Norte")
    - Numeric choice (e.g., "1" matches first option, "2" matches second)
    """
    # Collect all unique options across pages
    all_options: list[str] = []
    seen = set()
    for page in pages_data:
        if page.get("_extraction_failed") or not page.get("material_ambiguo"):
            continue
        for opt in page.get("materiales_opciones", []):
            opt_key = opt.strip().lower()
            if opt_key not in seen:
                seen.add(opt_key)
                all_options.append(opt.strip())

    if not all_options:
        return False, None, []

    input_clean = user_input.strip()
    input_lower = input_clean.lower()

    # Try numeric choice first ("1", "2", etc.)
    try:
        idx = int(input_clean) - 1
        if 0 <= idx < len(all_options):
            return True, all_options[idx], all_options
    except ValueError:
        pass

    # Exact case-insensitive match
    for opt in all_options:
        if opt.lower() == input_lower:
            return True, opt, all_options

    # Substring match (e.g., "cuarzo" matches "Cuarzo Blanco Norte")
    matches = [opt for opt in all_options if input_lower in opt.lower()]
    if len(matches) == 1:
        return True, matches[0], all_options

    # No match
    return False, None, all_options


def resolve_material_choice(pages_data: list[dict], chosen_material: str) -> list[dict]:
    """Update all pages with the validated material choice.

    IMPORTANT: Call validate_material_choice() first to ensure the choice is valid.
    The choice is persisted in quote_breakdown.material_choice by the caller.
    """
    for page in pages_data:
        if page.get("_extraction_failed"):
            continue
        if page.get("material_ambiguo"):
            page["material_text"] = chosen_material
            page["material_ambiguo"] = False
            page["materiales_opciones"] = []
    return pages_data


def dismiss_failed_pages(pages_data: list[dict]) -> list[dict]:
    """Remove failed pages from the dataset after operator confirms to proceed without them.

    Returns only the successfully extracted pages.
    """
    return [p for p in pages_data if not p.get("_extraction_failed")]


# ── Rendering ───────────────────────────────────────────────────────────────

def render_visual_edificio_choices(
    pages_data: list[dict],
    warnings: list[str],
    blockers: list[str],
) -> str:
    """Render the intermediate output when there are blockers (material ambiguo, failed pages).

    Shows summary of tipologías, warnings, and pending decisions.
    """
    ok_pages = [p for p in pages_data if not p.get("_extraction_failed")]
    failed_pages = [p for p in pages_data if p.get("_extraction_failed")]

    obra = ok_pages[0].get("obra", "—") if ok_pages else "—"
    total_units = sum(max(int(p.get("cantidad") or 1), 1) for p in ok_pages)

    lines = []
    lines.append("## VERIFICACIÓN EDIFICIO (Planos CAD)\n")
    lines.append(f"**Obra:** {obra}")
    lines.append(f"**Láminas procesadas:** {len(ok_pages)} de {len(pages_data)}")
    lines.append(f"**Total unidades:** {total_units}")
    lines.append("")

    # Tipologías table
    lines.append("### Tipologías detectadas\n")
    lines.append("| Lámina | Tipología | Pisos | Cantidad | Piezas | Material |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for p in ok_pages:
        lamina = p.get("lamina_id", "?")
        tipo = p.get("tipologia") or p.get("titulo", "?")
        pisos = p.get("pisos", "—")
        cant = p.get("cantidad", 1)
        n_piezas = len(p.get("piezas", []))
        mat = p.get("material_text", "—")
        if len(mat) > 40:
            mat = mat[:37] + "..."
        lines.append(f"| {lamina} | {tipo} | {pisos} | {cant} | {n_piezas} | {mat} |")
    lines.append("")

    # Failed pages — prominent section
    if failed_pages:
        lines.append("### ❌ Láminas con error de extracción\n")
        for p in failed_pages:
            lines.append(f"- Página {p.get('_page_number', '?')}: {p.get('_error', 'error desconocido')[:150]}")
        lines.append("")
        lines.append("*Para continuar sin estas láminas, respondé \"continuar sin fallidas\". Para reintentar, volvé a subir el PDF.*")
        lines.append("")

    # Warnings
    if warnings:
        lines.append("### ⚠️ Advertencias\n")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    # Blockers — material ambiguity
    mat_blockers = [b for b in blockers if "Material ambiguo" in b]
    other_blockers = [b for b in blockers if "Material ambiguo" not in b]

    if mat_blockers:
        lines.append("### ⛔ Material pendiente de definición\n")
        # Find material options from pages
        opciones = []
        mat_text = ""
        for p in ok_pages:
            if p.get("material_ambiguo") and p.get("materiales_opciones"):
                opciones = p["materiales_opciones"]
                mat_text = p.get("material_text", "")
                break
        lines.append(f"El plano indica: **\"{mat_text}\"**\n")
        if opciones:
            lines.append("Opciones:")
            for i, op in enumerate(opciones, 1):
                lines.append(f"  ({i}) {op}")
        lines.append(f"\n**→ Indicá cuál material usar para poder cotizar.**")
        lines.append("")

    if other_blockers:
        lines.append("### ⛔ Otros bloqueantes\n")
        for b in other_blockers:
            lines.append(f"- {b}")
        lines.append("")

    return "\n".join(lines)


def render_visual_edificio_paso1(
    pages_data: list[dict],
    norm_data: NormalizedEdificioData,
    summary: dict,
    warnings: list[str],
    material_choice: Optional[str] = None,
) -> str:
    """Render Paso 1 review for visual edificio — tipología-oriented.

    Shows the extracted data organized by lámina/tipología for operator confirmation.
    material_choice is shown prominently if it was resolved from an ambiguous state.
    """
    ok_pages = [p for p in pages_data if not p.get("_extraction_failed")]
    obra = ok_pages[0].get("obra", "—") if ok_pages else "—"
    total_units = sum(max(int(p.get("cantidad") or 1), 1) for p in ok_pages)
    material = material_choice or (ok_pages[0].get("material_text", "—") if ok_pages else "—")

    # Calculate grand total m²
    grand_m2 = sum(
        p.get("m2_calc_total", 0)
        for s in norm_data.get("sections", [])
        for p in s.get("pieces", [])
    )

    lines = []
    lines.append("## EDIFICIO — PASO 1 (Planos CAD)\n")
    lines.append(f"**Obra:** {obra}")
    lines.append(f"**Material:** {material}")
    if material_choice:
        lines.append(f"*(elegido por operador)*")
    lines.append(f"**Total unidades:** {total_units}")
    lines.append(f"**Total m²:** {grand_m2:.2f}")
    lines.append("")

    # Per-lamina detail
    lines.append("### Detalle por tipología\n")
    for p in ok_pages:
        lamina = p.get("lamina_id", "?")
        tipo = p.get("tipologia") or p.get("titulo", "?")
        pisos = p.get("pisos", "—")
        cant = p.get("cantidad", 1)
        piezas = p.get("piezas", [])

        lines.append(f"**{lamina} — {tipo}** (pisos: {pisos}, cantidad: {cant})")
        if piezas:
            lines.append("")
            lines.append("| Pieza | Largo | Ancho | m² unit | m² total | Pileta |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            lamina_m2_total = 0
            for pz in piezas:
                largo = pz.get("largo_cm", 0)
                ancho = pz.get("ancho_cm", 0)
                m2_u = round((largo / 100) * (ancho / 100), 4)
                m2_t = round(m2_u * cant, 4)
                lamina_m2_total += m2_t
                pileta_str = f"{pz['pileta_count']}×{pz.get('pileta_tipo', 'empotrada')}" if pz.get("pileta_count") else "—"
                notas = f" ({pz['notas']})" if pz.get("notas") else ""
                lines.append(f"| {pz.get('id', '?')}{notas} | {largo}cm | {ancho}cm | {m2_u:.4f} | {m2_t:.4f} | {pileta_str} |")
            lines.append(f"| **Subtotal** | | | | **{lamina_m2_total:.4f}** | |")
        lines.append("")

    # Zócalos summary if present
    zocalo_pages = [p for p in ok_pages if p.get("zocalos")]
    if zocalo_pages:
        lines.append("### Zócalos\n")
        for p in zocalo_pages:
            lamina = p.get("lamina_id", "?")
            cant = p.get("cantidad", 1)
            for z in p.get("zocalos", []):
                lines.append(f"- {lamina}: {z.get('largo_cm', 0)}cm × h={z.get('alto_cm', 5)}cm × {cant} unid")
        lines.append("")

    # Warnings
    if warnings:
        lines.append("### ⚠️ Advertencias\n")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines)
