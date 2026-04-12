import base64
import logging
import tempfile
from pathlib import Path
from typing import Optional
from PIL import Image

try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

TEMP_DIR = Path(tempfile.gettempdir()) / "marble_plans"
TEMP_DIR.mkdir(exist_ok=True)

# ── Limits to prevent token overflow ──
MAX_CROPS_PER_CALL = 2       # Hard limit: max 2 crops per tool call
CROP_MAX_WIDTH = 1024         # Max pixel width for crop output
CROP_JPEG_QUALITY = 75        # Aggressive compression
FULL_PLAN_MAX_WIDTH = 1200    # Full plan thumbnail (smaller than before)


def _fuzzy_find_file(filename: str) -> Optional[Path]:
    """Find file in TEMP_DIR with fuzzy matching for LLM-hallucinated filenames.

    Tries exact match first, then normalizes (lowercase, strip spaces/dashes)
    to find a unique candidate. Returns None if no match or ambiguous.
    """
    exact = TEMP_DIR / filename
    if exact.exists():
        return exact

    import re
    def _normalize(s: str) -> str:
        return re.sub(r'[\s\-_]+', '', s.lower())

    target = _normalize(filename)
    candidates = []
    for f in TEMP_DIR.iterdir():
        if f.is_file() and _normalize(f.name) == target:
            candidates.append(f)

    if len(candidates) == 1:
        logging.info(f"[read_plan] fuzzy match: '{filename}' → '{candidates[0].name}'")
        return candidates[0]

    return None


def _image_to_b64(img: Image.Image, max_width: int, quality: int = CROP_JPEG_QUALITY) -> str:
    """Convert PIL Image to compressed base64 JPEG, capped at max_width."""
    if img.width > max_width:
        ratio = max_width / img.width
        new_h = int(img.height * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)

    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


async def read_plan(filename: str, crop_instructions: list) -> list:
    """Rasterize a plan file at 200 DPI and return crops as native image content blocks.

    AUXILIARY tool for tactical zoom/crop only. PDF visual analysis should
    use native vision on the document already attached inline.

    Returns a LIST of Anthropic-native content blocks (type: "image" + type: "text")
    instead of a JSON dict, so images don't inflate the text context.

    Hard limits:
    - Max 2 crops per call (prevents token overflow)
    - Max 1024px width per crop
    - JPEG quality 75
    """
    plan_path = _fuzzy_find_file(filename)
    if plan_path is None:
        available = [f.name for f in TEMP_DIR.iterdir() if f.is_file()] if TEMP_DIR.exists() else []
        return [{"type": "text", "text": f"Error: archivo no encontrado: {filename}. Disponibles: {available}"}]

    ext = plan_path.suffix.lower()
    base_image = None

    try:
        if ext == ".pdf" and PDF2IMAGE_AVAILABLE:
            pages = convert_from_bytes(
                plan_path.read_bytes(),
                dpi=200,
                fmt="jpeg",
            )
            if pages:
                base_image = pages[0]
        else:
            base_image = Image.open(plan_path)
    except Exception as e:
        return [{"type": "text", "text": f"Error al procesar el plano: {str(e)}"}]

    if base_image is None:
        return [{"type": "text", "text": "No se pudo rasterizar el plano"}]

    result_blocks = []

    # If no crop instructions, return a compressed full thumbnail
    if not crop_instructions:
        b64 = _image_to_b64(base_image, max_width=FULL_PLAN_MAX_WIDTH)
        result_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
        result_blocks.append({
            "type": "text",
            "text": f"Plano completo ({base_image.width}x{base_image.height}px, reducido a {FULL_PLAN_MAX_WIDTH}px). Analizá directamente.",
        })
        return result_blocks

    # Enforce crop limit
    crops_to_process = crop_instructions[:MAX_CROPS_PER_CALL]
    truncated = len(crop_instructions) > MAX_CROPS_PER_CALL

    for crop in crops_to_process:
        try:
            cropped = base_image.crop((
                crop["x1"], crop["y1"],
                crop["x2"], crop["y2"],
            ))
            b64 = _image_to_b64(cropped, max_width=CROP_MAX_WIDTH)
            result_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
            })
            result_blocks.append({
                "type": "text",
                "text": f"Crop: {crop.get('label', '?')} ({cropped.width}x{cropped.height}px → {CROP_MAX_WIDTH}px max)",
            })
        except Exception as e:
            result_blocks.append({
                "type": "text",
                "text": f"Error en crop '{crop.get('label', '?')}': {str(e)}",
            })

    if truncated:
        remaining = [c.get("label", "?") for c in crop_instructions[MAX_CROPS_PER_CALL:]]
        result_blocks.append({
            "type": "text",
            "text": (
                f"⚠️ Límite de {MAX_CROPS_PER_CALL} crops por llamada alcanzado. "
                f"Analizá estos primero. Pendientes: {', '.join(remaining)}. "
                f"Llamá read_plan de nuevo para los siguientes crops."
            ),
        })

    logging.info(f"[read_plan] Returned {len(crops_to_process)} crops ({len(result_blocks)} blocks) for {filename}")
    return result_blocks


def save_plan_to_temp(filename: str, data: bytes) -> Path:
    """Save uploaded plan file to temp directory for tool access."""
    safe_name = Path(filename).name
    path = TEMP_DIR / safe_name
    path.write_bytes(data)
    return path


def cleanup_temp_files():
    """Remove old temp files (>1 hour). Call periodically or after processing."""
    import time
    if not TEMP_DIR.exists():
        return
    cutoff = time.time() - 3600
    for f in TEMP_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
