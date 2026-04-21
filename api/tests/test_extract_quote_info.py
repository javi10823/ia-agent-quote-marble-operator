"""Tests de `_extract_quote_info`: parseo de cliente/proyecto/material desde
el brief del operador. Cubre briefs con Markdown bold (`**CLIENTE:** ...`)
que antes colaban asteriscos en los valores extraídos (Bug F)."""
from app.modules.agent.agent import _extract_quote_info


class TestMarkdownBoldBrief:
    """Brief con `**LABEL:**` — pre-strip de Markdown bold antes del regex."""

    def test_markdown_bold_client_has_no_asterisks(self):
        """`**CLIENTE:** Luciana Villagra Dos` no debe quedar con `**`
        colándose dentro del nombre ni trailing del título."""
        msg = (
            "**CLIENTE:** Luciana Villagra Dos\n"
            "**OBRA:** Cocina\n"
            "**MATERIAL:** Purastone Blanco Nube — 20mm"
        )
        info = _extract_quote_info(msg)
        assert info.get("client_name") == "Luciana Villagra Dos", info
        assert "*" not in info.get("client_name", "")

    def test_markdown_bold_project_has_no_asterisks(self):
        msg = (
            "**CLIENTE:** Luciana\n"
            "**OBRA:** Cocina\n"
            "**MATERIAL:** Purastone"
        )
        info = _extract_quote_info(msg)
        assert info.get("project") == "Cocina", info
        assert "*" not in info.get("project", "")

    def test_markdown_bold_material_is_clean(self):
        """Antes daba 'TERIAL:** Purastone Blanco Nube' por un slicing
        roto del extractor de material. Ahora debe ser el nombre solo."""
        msg = (
            "**CLIENTE:** Luciana\n"
            "**OBRA:** Cocina\n"
            "**MATERIAL:** Purastone Blanco Nube — 20mm"
        )
        info = _extract_quote_info(msg)
        mat = info.get("material", "")
        assert "TERIAL" not in mat, mat
        assert "*" not in mat, mat
        assert "Purastone" in mat

    def test_inline_markdown_single_line_no_asterisk_leak(self):
        """Misma info en una sola línea (sin \\n), también con bold.
        No testeamos el parseo perfecto del cliente/proyecto (el delimiter
        regex pide whitespace alrededor de 'obra', y 'OBRA:' no califica —
        caso edge no reportado en Bug F). Sí validamos que no queden `**`
        en los valores, que es el corazón del bug."""
        msg = (
            "**CLIENTE:** Pérez **OBRA:** Lofts "
            "**MATERIAL:** Silestone Blanco Norte"
        )
        info = _extract_quote_info(msg)
        for v in info.values():
            assert "*" not in v, f"asterisk leaked into extracted value: {v!r}"
        assert "silestone" in info.get("material", "").lower()


class TestPlainBriefsStillWork:
    """No romper los formatos previos (sin Markdown)."""

    def test_explicit_cliente_obra(self):
        info = _extract_quote_info("Cliente: Munge, Obra: A1335")
        assert info.get("client_name") == "Munge"
        assert info.get("project") == "A1335"

    def test_slash_separator(self):
        info = _extract_quote_info("Juan Pérez / Casa Laprida")
        assert info.get("client_name") == "Juan Pérez"
        assert info.get("project") == "Casa Laprida"

    def test_material_only(self):
        info = _extract_quote_info("cotizar Silestone Blanco Norte para cocina")
        assert "silestone" in info.get("material", "").lower()
