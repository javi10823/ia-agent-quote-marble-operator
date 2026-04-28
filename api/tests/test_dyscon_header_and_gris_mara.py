"""Tests para PR #410 — header parser + default Gris Mara.

Bugs cerrados:

1. **Header parser** (`agent.py:_extract_quote_info`): cuando el brief
   viene en una sola línea con labels pegados a `:` (caso DYSCON
   `CLIENTE: DYSCON S.A. OBRA: ...`), los delimitadores del regex
   exigían whitespace después de la keyword (`\\s+obra\\s`) — y el
   `:` no es whitespace → cliente absorbía todo hasta fin de string.
   Mismo bug afectaba al regex del proyecto.

2. **Default Gris Mara** (`calculator.py:_find_material`): el granito
   Gris Mara tiene 3 variantes en el catálogo (Extra 2, Fiamatado,
   Leather). Regla del operador: solo se vende como Extra 2 salvo
   pedido explícito. El agente Sonnet, leyendo "NO Extra 2" en el
   brief, infería otra variante e inyectaba "Granito Gris Mara
   Fiamatado" al calculator → matcher fuzzy resolvía a FIAMATADO.

Fix:
- Header parser: delimiters aceptan `[:\\s]` (corte por dos puntos
  o whitespace). Preserve case si input viene 100% mayúsculas.
- Gris Mara: pre-check determinístico antes del fuzzy. Si input
  contiene "gris mara" sin "fiamatado"/"leather" explícito →
  resolver directo a SKU GRISMARA (Extra 2 ESP).
"""
from __future__ import annotations

import pytest

from app.modules.agent.agent import _extract_quote_info
from app.modules.quote_engine.calculator import _find_material


# ═══════════════════════════════════════════════════════════════════════
# Header parser — caso DYSCON (single-line con :)
# ═══════════════════════════════════════════════════════════════════════


class TestHeaderParserDyscon:
    def test_dyscon_full_brief_single_line(self):
        """Caso real: brief en una sola línea con labels pegados a `:`."""
        msg = (
            "CLIENTE: DYSCON S.A. OBRA: Unidad Penal N°8 — Piñero "
            "MATERIAL: Granito Gris Mara — 20mm (SKU estándar, NO Extra 2)"
        )
        info = _extract_quote_info(msg)

        # Cliente: cortado por OBRA: (con dos puntos), NO absorbe el resto.
        assert info.get("client_name") == "DYSCON S.A.", (
            f"Cliente regresión: {info.get('client_name')!r}, esperaba 'DYSCON S.A.'"
        )
        # Proyecto: cortado por MATERIAL: (con dos puntos), NO absorbe.
        assert info.get("project") == "Unidad Penal N°8 — Piñero", (
            f"Proyecto regresión: {info.get('project')!r}, esperaba 'Unidad Penal N°8 — Piñero'"
        )
        # Material: extraído por keyword "granito".
        assert info.get("material") is not None
        assert "Gris Mara" in info["material"]


class TestHeaderParserNoRegression:
    """Formatos viejos siguen funcionando."""

    def test_cliente_obra_with_comma(self):
        info = _extract_quote_info("Cliente: Pérez, Obra: Casa Laprida")
        assert info["client_name"] == "Pérez"
        assert info["project"] == "Casa Laprida"

    def test_slash_separator(self):
        info = _extract_quote_info("Munge / A1335")
        assert info["client_name"] == "Munge"
        assert info["project"] == "A1335"

    def test_lowercase_input_gets_titled(self):
        """Si el input viene en minúsculas/mixed-case, sigue aplicándose
        `.title()` (vía `_preserve_case`). Solo se preserva mayúsculas
        cuando TODAS las letras son uppercase."""
        info = _extract_quote_info("Cliente: juan perez, Obra: casa norte")
        assert info["client_name"] == "Juan Perez"
        assert info["project"] == "Casa Norte"

    def test_uppercase_preserved(self):
        """Input con cliente 100% mayúsculas → preserva como vino."""
        info = _extract_quote_info("Cliente: DYSCON S.A., Obra: Penal")
        assert info["client_name"] == "DYSCON S.A."


# ═══════════════════════════════════════════════════════════════════════
# Default Gris Mara — Extra 2 salvo pedido explícito
# ═══════════════════════════════════════════════════════════════════════


class TestGrisMaraDefault:
    def test_gris_mara_default_extra_2(self):
        """'Granito Gris Mara' sin variante explícita → EXTRA 2 ESP."""
        result = _find_material("Granito Gris Mara")
        assert result.get("found") is True
        assert result["sku"] == "GRISMARA"
        assert "EXTRA 2 ESP" in result["name"], (
            f"Esperaba EXTRA 2 ESP, got {result.get('name')}"
        )

    def test_gris_mara_with_no_extra_2_noise_still_default(self):
        """Brief con ruido tipo 'NO Extra 2' → sigue siendo EXTRA 2.
        Caso DYSCON: el operador escribe 'NO Extra 2' como aclaración,
        pero esa es la única variante real → debe respetarse."""
        result = _find_material("Granito Gris Mara — 20mm (SKU estándar, NO Extra 2)")
        assert result.get("found") is True
        assert result["sku"] == "GRISMARA"
        assert "EXTRA 2 ESP" in result["name"]

    def test_gris_mara_fiamatado_explicit_respected(self):
        """Si el operador escribe 'fiamatado' explícito → respeta variante."""
        result = _find_material("Granito Gris Mara Fiamatado")
        assert result.get("found") is True
        assert "FIAMATADO" in result["name"], (
            f"Esperaba FIAMATADO, got {result.get('name')}"
        )

    def test_gris_mara_leather_explicit_respected(self):
        """Si el operador escribe 'leather' explícito → respeta variante."""
        result = _find_material("Granito Gris Mara Leather")
        assert result.get("found") is True
        assert "LEATHER" in result["name"], (
            f"Esperaba LEATHER, got {result.get('name')}"
        )

    def test_gris_mara_default_carries_fuzzy_metadata(self):
        """El override determinístico debe registrar trazabilidad
        (fuzzy_corrected_from + fuzzy_catalog) para que el operador
        vea que el sistema lo ajustó."""
        result = _find_material("Granito Gris Mara")
        assert result.get("fuzzy_corrected_from") == "Granito Gris Mara"
        assert result.get("fuzzy_catalog") == "granito-nacional"
        assert result.get("fuzzy_family") == "granito"

    def test_other_granitos_unaffected(self):
        """Regression guard: el pre-check solo dispara con 'gris mara'.
        Otros granitos del catálogo no deben verse afectados."""
        # Negro Brasil — granito común, no afectado por el guard.
        result = _find_material("Granito Negro Brasil")
        # El test no exige un SKU específico (puede haber varias variantes
        # de Negro Brasil), pero NO debe ser GRISMARA.
        assert result.get("sku") != "GRISMARA"
