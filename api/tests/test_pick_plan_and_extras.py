"""Regression: PDFs deben tener prioridad sobre imágenes al elegir plan_bytes.

Caso Bernardi: operador subió [render.jpg, render.jpg, plano.pdf]. Con la
lógica anterior (validated_files[0]) el render terminaba como plan_bytes y
dual_read leía un render fotorrealista como si fuera un plano técnico.
"""
from app.modules.agent.router import _pick_plan_and_extras


def test_pdf_wins_over_images_regardless_of_order():
    files = [
        (b"render1", "WhatsApp Image (4).jpeg"),
        (b"render2", "WhatsApp Image (3).jpeg"),
        (b"plano_bytes", "Bernardi-Mesadas cocina.pdf"),
    ]
    plan_bytes, plan_name, extras = _pick_plan_and_extras(files)
    assert plan_bytes == b"plano_bytes"
    assert plan_name == "Bernardi-Mesadas cocina.pdf"
    extra_names = [name for _b, name in extras]
    assert extra_names == ["WhatsApp Image (4).jpeg", "WhatsApp Image (3).jpeg"]


def test_pdf_first_still_works():
    files = [
        (b"plano", "plano.pdf"),
        (b"render", "render.jpg"),
    ]
    plan_bytes, plan_name, extras = _pick_plan_and_extras(files)
    assert plan_name == "plano.pdf"
    assert len(extras) == 1
    assert extras[0][1] == "render.jpg"


def test_no_pdf_falls_back_to_first_file():
    """Sin PDF → usar primer archivo (comportamiento legacy)."""
    files = [
        (b"img1", "foto.jpg"),
        (b"img2", "foto2.png"),
    ]
    plan_bytes, plan_name, extras = _pick_plan_and_extras(files)
    assert plan_name == "foto.jpg"
    assert len(extras) == 1
    assert extras[0][1] == "foto2.png"


def test_multiple_pdfs_takes_the_first_pdf():
    files = [
        (b"render", "render.jpg"),
        (b"plano1", "primer-plano.pdf"),
        (b"plano2", "segundo-plano.pdf"),
    ]
    plan_bytes, plan_name, extras = _pick_plan_and_extras(files)
    assert plan_name == "primer-plano.pdf"
    # ambos no-elegidos caen como extras, preservando orden relativo
    extra_names = [name for _b, name in extras]
    assert extra_names == ["render.jpg", "segundo-plano.pdf"]


def test_empty_input():
    plan_bytes, plan_name, extras = _pick_plan_and_extras([])
    assert plan_bytes is None
    assert plan_name is None
    assert extras == []


def test_uppercase_pdf_extension_detected():
    files = [
        (b"render", "render.jpg"),
        (b"plano", "PLANO.PDF"),
    ]
    plan_bytes, plan_name, _ = _pick_plan_and_extras(files)
    assert plan_name == "PLANO.PDF"
