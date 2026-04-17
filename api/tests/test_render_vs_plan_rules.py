"""Regression: plan-reader-v1.md must teach Valentina the difference between
photorealistic renders and technical plans.

Caso Bernardi: el operador adjunta 1 PDF técnico + 2 renders fotorrealistas.
Sin la regla, Valentina intenta extraer cotas de los renders → hallucinations.
"""
from pathlib import Path


def _read_plan_reader() -> str:
    return (Path(__file__).parent.parent / "rules" / "plan-reader-v1.md").read_text()


def test_render_fotorrealista_view_type_documented():
    """El enum de view_type debe incluir render_fotorrealista."""
    assert "render_fotorrealista" in _read_plan_reader()


def test_rule_forbids_measuring_photorealistic_renders():
    """Regla debe prohibir extraer medidas de renders fotorrealistas."""
    text = _read_plan_reader()
    # Busca que haya una regla cerca de render_fotorrealista que diga NO extraer
    idx = text.find("render_fotorrealista")
    assert idx >= 0
    window = text[idx:idx + 500]
    assert "NO" in window and "medidas" in window.lower(), (
        "Rule near render_fotorrealista should forbid extracting measurements"
    )


def test_rule_asks_for_technical_plan_when_only_renders():
    """Si no hay planta técnica → debe pedirla al operador."""
    text = _read_plan_reader()
    idx = text.find("render_fotorrealista")
    window = text[idx:idx + 500]
    # La regla debe mencionar pedir el plano técnico
    assert "planta" in window.lower() or "plano t" in window.lower()
