"""PR #17 — nombre canónico del cliente en resumen consolidado.

Cuando el dashboard agrupa variantes fuzzy (ej: 'Estudio 72' y
'Estudio 72 — Fideicomiso Ventus'), el PDF del resumen debe usar la
forma más corta (núcleo del cliente).
"""
import pytest

from app.modules.agent.tools.resumen_obra_tool import _build_resumen_data


class _Q:
    """Duck-typed stub — evita instanciar el modelo SQLAlchemy."""

    def __init__(self, cid: str, name: str) -> None:
        self.id = cid
        self.client_name = name
        self.project = "Fideicomiso Ventus"
        self.quote_breakdown = {"mo_items": []}
        self.material = "GRANITO CEARA"
        self.total_ars = 0
        self.total_usd = 0


def _make(cid: str, name: str):
    return _Q(cid, name)


def test_canonical_picks_shortest_client_name():
    """Caso Estudio 72: mezcla de 'Estudio 72' y 'Estudio 72 — Fideicomiso Ventus'
    → PDF usa 'Estudio 72' (más corto)."""
    quotes = [
        _make("q1", "Estudio 72 — Fideicomiso Ventus"),
        _make("q2", "Estudio 72"),
        _make("q3", "Estudio 72 — Fideicomiso Ventus"),
    ]
    data = _build_resumen_data(quotes, notes="")
    assert data["client_name"] == "Estudio 72"


def test_canonical_all_same_name():
    """Si todas las quotes tienen el mismo nombre, se respeta ese."""
    quotes = [_make("q1", "DINALE S.A."), _make("q2", "DINALE S.A.")]
    data = _build_resumen_data(quotes, notes="")
    assert data["client_name"] == "DINALE S.A."


def test_canonical_skips_empty_names():
    """Quotes sin client_name NO deben contar como candidato."""
    quotes = [_make("q1", ""), _make("q2", "DINALE")]
    data = _build_resumen_data(quotes, notes="")
    assert data["client_name"] == "DINALE"


def test_canonical_all_empty_returns_empty():
    quotes = [_make("q1", ""), _make("q2", "")]
    data = _build_resumen_data(quotes, notes="")
    assert data["client_name"] == ""
