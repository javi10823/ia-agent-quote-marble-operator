"""Tests para PR #395 — `build_brief_from_quote_columns`.

El helper toma un Quote de DB con datos del chatbot externo y arma un
brief natural (texto plano) que el `brief_analyzer` LLM sabe parsear
cuando el operador aprieta "Procesar plano y contexto". Equivalente al
user_message que usaba el bg task pre-#394.

Regla de no-invención: si una columna del Quote está `None` o vacía,
NO aparece línea en el brief. Nunca rellena con defaults.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.modules.agent.synthetic_brief import build_brief_from_quote_columns


def _q(**fields) -> SimpleNamespace:
    """Factory de fake-Quote con getattr-equivalent."""
    defaults = {
        "client_name": None,
        "project": None,
        "material": None,
        "localidad": None,
        "colocacion": None,
        "pileta": None,
        "anafe": None,
        "sink_type": None,
        "notes": None,
    }
    defaults.update(fields)
    return SimpleNamespace(**defaults)


class TestBuildBrief:
    def test_bernardi_style_full(self):
        """Quote típico del chatbot con varios datos presentes."""
        q = _q(
            client_name="Erica Bernardi",
            project="Cocina",
            material="Puraprima Onix White Mate",
            localidad="Rosario",
            colocacion=True,
            pileta="empotrada",
            anafe=True,
            notes="Sin zócalos, pileta Johnson LUXOR",
        )
        out = build_brief_from_quote_columns(q)
        lines = out.split("\n")
        assert "Cliente: Erica Bernardi" in lines
        assert "Proyecto: Cocina" in lines
        assert "Material: Puraprima Onix White Mate" in lines
        assert "Localidad: Rosario" in lines
        assert "Con colocación" in lines
        assert "Pileta: empotrada" in lines
        assert "Con anafe" in lines
        assert "Notas del cliente: Sin zócalos, pileta Johnson LUXOR" in lines
        assert lines[-1] == "Adjunto el plano cargado desde el chatbot web."

    def test_empty_quote_has_only_final_line(self):
        """Quote sin ningún dato → solo la línea final que indica al
        agente que el plano está adjunto."""
        q = _q()
        out = build_brief_from_quote_columns(q)
        assert out == "Adjunto el plano cargado desde el chatbot web."

    def test_colocacion_false_emits_sin(self):
        q = _q(client_name="X", colocacion=False)
        out = build_brief_from_quote_columns(q)
        assert "Sin colocación" in out
        assert "Con colocación" not in out

    def test_colocacion_none_omitted(self):
        q = _q(client_name="X", colocacion=None)
        out = build_brief_from_quote_columns(q)
        assert "colocación" not in out  # ninguna línea

    def test_anafe_false_or_none_omitted(self):
        """`anafe=False` no emite 'Sin anafe' — el helper omite. Si el
        chatbot no aclaró, no inventamos negación."""
        q1 = _q(client_name="X", anafe=False)
        q2 = _q(client_name="X", anafe=None)
        assert "anafe" not in build_brief_from_quote_columns(q1).lower()
        assert "anafe" not in build_brief_from_quote_columns(q2).lower()

    def test_sink_type_dict_rendered(self):
        q = _q(
            client_name="X",
            sink_type={"basin_count": "doble", "mount_type": "empotrada"},
        )
        out = build_brief_from_quote_columns(q)
        assert "Tipo de bacha:" in out
        assert "Doble" in out
        assert "Pegada de empotrada" in out

    def test_sink_type_empty_dict_omitted(self):
        q = _q(client_name="X", sink_type={"basin_count": "", "mount_type": ""})
        out = build_brief_from_quote_columns(q)
        assert "Tipo de bacha" not in out

    def test_notes_whitespace_only_omitted(self):
        q = _q(client_name="X", notes="   \n  \t ")
        out = build_brief_from_quote_columns(q)
        assert "Notas del cliente" not in out

    def test_does_not_invent_fields_not_present(self):
        """Lo que no está en el Quote NO aparece, ni como default."""
        q = _q(client_name="X")
        out = build_brief_from_quote_columns(q)
        # Solo 2 líneas: cliente + adjunto el plano.
        assert out.count("\n") == 1
        assert "Cliente: X" in out
        assert "Proyecto" not in out
        assert "Material" not in out
        assert "Localidad" not in out

    def test_output_is_llm_parseable_shape(self):
        """Sanity: el shape del output coincide con el que espera
        `brief_analyzer` (líneas `Clave: valor`)."""
        q = _q(client_name="Juan", material="Silestone Blanco Norte")
        out = build_brief_from_quote_columns(q)
        # Cada línea relevante matchea "Clave: valor" excepto la final.
        data_lines = [l for l in out.split("\n") if l != "Adjunto el plano cargado desde el chatbot web."]
        for line in data_lines:
            assert ":" in line, f"Línea sin formato 'clave: valor': {line!r}"
