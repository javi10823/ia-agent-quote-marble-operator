import base64
import logging
import tempfile
import time
from pathlib import Path
from typing import Optional
from PIL import Image

logger = logging.getLogger(__name__)

try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

TEMP_DIR = Path(tempfile.gettempdir()) / "marble_plans"
TEMP_DIR.mkdir(exist_ok=True)


async def read_plan(filename: str, crop_instructions: list) -> dict:
    """
    Rasterize a plan file at 300 DPI and optionally crop individual mesadas.
    Returns base64-encoded images for Claude to analyze.
    """
    plan_path = TEMP_DIR / filename
    if not plan_path.exists():
        return {"error": f"Archivo no encontrado: {filename}"}

    ext = plan_path.suffix.lower()
    images = []

    try:
        if ext == ".pdf" and PDF2IMAGE_AVAILABLE:
            pages = convert_from_bytes(
                plan_path.read_bytes(),
                dpi=300,
                fmt="jpeg",
            )
            if pages:
                images = [pages[0]]
        else:
            img = Image.open(plan_path)
            images = [img]
    except Exception as e:
        return {"error": f"Error al procesar el plano: {str(e)}"}

    if not images:
        return {"error": "No se pudo rasterizar el plano"}

    base_image = images[0]
    result_images = []

    # Full plan (reduced)
    full_w = base_image.width
    full_h = base_image.height
    result_images.append({
        "label": "plano_completo",
        "base64": _image_to_b64(base_image, max_width=2000),
        "width": full_w,
        "height": full_h,
    })

    # Individual crops
    for crop in crop_instructions:
        try:
            cropped = base_image.crop((
                crop["x1"], crop["y1"],
                crop["x2"], crop["y2"],
            ))
            result_images.append({
                "label": crop["label"],
                "base64": _image_to_b64(cropped),
                "width": cropped.width,
                "height": cropped.height,
            })
        except Exception as e:
            result_images.append({
                "label": crop.get("label", "crop"),
                "error": str(e),
            })

    return {
        "ok": True,
        "filename": filename,
        "original_size": {"width": full_w, "height": full_h},
        "images": result_images,
        "note": "Imágenes rasterizadas a 300 DPI. Analizar cada crop individualmente.",
    }


def _image_to_b64(img: Image.Image, max_width: Optional[int] = None) -> str:
    if max_width and img.width > max_width:
        ratio = max_width / img.width
        new_h = int(img.height * ratio)
        img = img.resize((max_width, new_h), Image.LANCZOS)

    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def save_plan_to_temp(filename: str, data: bytes) -> Path:
    """Save uploaded plan file to temp directory for tool access."""
    safe_name = Path(filename).name  # strip directory traversal (../ etc.)
    path = TEMP_DIR / safe_name
    path.write_bytes(data)
    return path


def cleanup_temp_file(filename: str) -> None:
    """Remove a specific temp file after processing."""
    safe_name = Path(filename).name
    path = TEMP_DIR / safe_name
    try:
        if path.exists():
            path.unlink()
    except OSError as e:
        logger.debug(f"Could not remove temp file {path}: {e}")


def cleanup_old_temp_files(max_age_hours: int = 24) -> int:
    """Remove temp files older than max_age_hours. Returns count removed."""
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    try:
        for f in TEMP_DIR.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
    except OSError as e:
        logger.debug(f"Temp cleanup error: {e}")
    return removed
