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


# ═══════════════════════════════════════════════════════
# PR #375 — persistencia temprana de columnas Quote.* desde brief_analysis
# ═══════════════════════════════════════════════════════

from unittest.mock import MagicMock  # noqa: E402
from app.modules.agent.agent import _extract_column_updates_from_analysis  # noqa: E402


def _make_quote(client_name="", project="", material="", localidad=""):
    """Mock Quote ORM con atributos indexables. Usamos MagicMock con spec
    sólo por los getattr que necesitamos — suficiente para el helper."""
    q = MagicMock()
    q.client_name = client_name
    q.project = project
    q.material = material
    q.localidad = localidad
    return q


class TestExtractColumnUpdatesFromAnalysis:
    """Bernardi: brief dice 'Cliente: Erica Bernardi' → el analysis lo
    detecta, pero el flujo hace return early con la card y nunca llega
    al save del while loop. El quote queda `client_name=""` en DB y el
    filtro del listado lo trata como empty draft.

    El helper puro toma el analysis + quote actual y devuelve las
    columnas a setear (sólo las vacías). Lo llama `_run_dual_read` al
    persistir la card para que desde el turno 1 el quote sea visible.
    """

    def test_bernardi_populates_empty_columns_from_brief(self):
        """Caso central: quote recién creado (todo vacío), brief con datos."""
        quote = _make_quote()
        analysis = {
            "client_name": "Erica Bernardi",
            "project": "",
            "material": "Puraprima Onix White Mate",
            "localidad": "Rosario",
        }
        updates = _extract_column_updates_from_analysis(analysis, quote)
        assert updates == {
            "client_name": "Erica Bernardi",
            "material": "Puraprima Onix White Mate",
            "localidad": "Rosario",
        }
        assert "project" not in updates  # era vacío y el analysis no trae

    def test_does_not_overwrite_existing_client_name(self):
        """Regla central: NO pisar valores previos del operador o de
        turnos anteriores."""
        quote = _make_quote(client_name="Juan Pérez (manual)")
        analysis = {"client_name": "Erica Bernardi"}
        updates = _extract_column_updates_from_analysis(analysis, quote)
        assert "client_name" not in updates

    def test_partial_fill_respects_existing_and_completes_empty(self):
        """Quote tiene material pero no cliente → completa cliente, no
        toca material."""
        quote = _make_quote(material="Silestone ya seteado")
        analysis = {
            "client_name": "Nuevo Cliente",
            "material": "Otro material (analysis)",
        }
        updates = _extract_column_updates_from_analysis(analysis, quote)
        assert updates == {"client_name": "Nuevo Cliente"}
        assert "material" not in updates

    def test_strips_markdown_bold_before_persisting(self):
        """`**CLIENTE:** X` — el analyze_brief a veces deja ** residual
        en el value, el helper los limpia antes de persistir."""
        quote = _make_quote()
        analysis = {"client_name": "**Luciana Villagra**"}
        updates = _extract_column_updates_from_analysis(analysis, quote)
        assert updates["client_name"] == "Luciana Villagra"
        assert "*" not in updates["client_name"]

    def test_strips_newlines(self):
        quote = _make_quote()
        analysis = {"client_name": "Cliente\nCon\nSaltos"}
        updates = _extract_column_updates_from_analysis(analysis, quote)
        assert "\n" not in updates["client_name"]
        assert "\r" not in updates["client_name"]

    def test_truncates_long_values_to_450(self):
        """DB columns son VARCHAR(500). Defensivo: truncar a 450."""
        quote = _make_quote()
        long_name = "X" * 600
        analysis = {"client_name": long_name}
        updates = _extract_column_updates_from_analysis(analysis, quote)
        assert len(updates["client_name"]) == 450

    def test_empty_analysis_returns_empty(self):
        quote = _make_quote()
        assert _extract_column_updates_from_analysis({}, quote) == {}
        assert _extract_column_updates_from_analysis(None, quote) == {}

    def test_none_quote_returns_empty(self):
        """Sin quote no hay nada con qué comparar → empty update, no crash."""
        assert _extract_column_updates_from_analysis({"client_name": "X"}, None) == {}

    def test_analysis_with_none_fields_skipped(self):
        """Analysis con `None` en varios campos (estado común con brief
        vacío): no emitir updates para esos fields."""
        quote = _make_quote()
        analysis = {
            "client_name": None,
            "project": None,
            "material": None,
            "localidad": None,
        }
        assert _extract_column_updates_from_analysis(analysis, quote) == {}

    def test_non_string_values_treated_as_empty(self):
        """Si el analysis trae un tipo raro (int, dict), no romper."""
        quote = _make_quote()
        analysis = {"client_name": 42, "project": {"foo": "bar"}}
        assert _extract_column_updates_from_analysis(analysis, quote) == {}

    def test_whitespace_only_values_dropped(self):
        quote = _make_quote()
        analysis = {"client_name": "   ", "project": "\n\t"}
        assert _extract_column_updates_from_analysis(analysis, quote) == {}

    def test_existing_none_is_treated_as_empty(self):
        """En DB, si el campo nunca fue seteado puede ser `None` (no `""`).
        Ambos se consideran vacíos."""
        quote = _make_quote(client_name=None)
        analysis = {"client_name": "Nuevo"}
        updates = _extract_column_updates_from_analysis(analysis, quote)
        assert updates == {"client_name": "Nuevo"}

