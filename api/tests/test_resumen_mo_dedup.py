"""PR #29 — MO dedup + plazo selection in resumen de obra.

Covers:
  Bug 1: Identical MO items across N quotes must appear once (not N times).
  Bug 2: mo_total must equal sum of deduplicated items (not N * original).
  Bug 3: Use persisted mo_items[].total (no recalculation drift).
  Bug 4: Pick the most specific plazo (skip "A confirmar").
"""
import pytest

from app.modules.agent.tools.resumen_obra_tool import _build_resumen_data


class _Q:
    """Duck-typed stub — avoids instantiating the SQLAlchemy model."""

    def __init__(
        self,
        cid: str,
        name: str = "Cliente Test",
        project: str = "Proyecto Test",
        mo_items: list | None = None,
        mo_total: int = 0,
        total_ars: int = 0,
        total_usd: int = 0,
        material: str = "SILESTONE BLANCO ZEUS",
        plazo: str = "",
    ) -> None:
        self.id = cid
        self.client_name = name
        self.project = project
        self.material = material
        self.total_ars = total_ars
        self.total_usd = total_usd
        bd: dict = {}
        if mo_items is not None:
            bd["mo_items"] = mo_items
        bd["mo_total"] = mo_total
        if plazo:
            bd["plazo"] = plazo
        self.quote_breakdown = bd


# ── Shared MO fixture (same work across 3 material options) ──

_SHARED_MO = [
    {"description": "Colocacion", "quantity": 1.03, "unit_price": 60135, "total": 61939},
    {"description": "Agujero y pegado pileta", "quantity": 1, "unit_price": 65147, "total": 65147},
    {"description": "Zocalo", "quantity": 5.8, "unit_price": 5135, "total": 29783},
    {"description": "Flete", "quantity": 1, "unit_price": 323774, "total": 323774},
]
_MO_TOTAL = sum(m["total"] for m in _SHARED_MO)  # 480_643


# ── Bug 1: dedup ──


def test_identical_mo_listed_once():
    """3 quotes with the same MO -> resumen has each item once."""
    quotes = [
        _Q("q1", mo_items=_SHARED_MO, mo_total=_MO_TOTAL),
        _Q("q2", mo_items=_SHARED_MO, mo_total=_MO_TOTAL),
        _Q("q3", mo_items=_SHARED_MO, mo_total=_MO_TOTAL),
    ]
    data = _build_resumen_data(quotes, notes="")
    assert len(data["mo_items"]) == len(_SHARED_MO)


def test_different_mo_not_deduped():
    """Quotes with genuinely different MO items must all appear."""
    mo_a = [{"description": "Colocacion", "quantity": 1, "unit_price": 60000, "total": 60000}]
    mo_b = [{"description": "Flete", "quantity": 1, "unit_price": 30000, "total": 30000}]
    quotes = [
        _Q("q1", mo_items=mo_a, mo_total=60000),
        _Q("q2", mo_items=mo_b, mo_total=30000),
    ]
    data = _build_resumen_data(quotes, notes="")
    assert len(data["mo_items"]) == 2


# ── Bug 2: mo_total matches deduplicated sum ──


def test_mo_total_equals_deduped_sum():
    """mo_total must be 480,643, NOT 3 * 480,643."""
    quotes = [
        _Q("q1", mo_items=_SHARED_MO, mo_total=_MO_TOTAL),
        _Q("q2", mo_items=_SHARED_MO, mo_total=_MO_TOTAL),
        _Q("q3", mo_items=_SHARED_MO, mo_total=_MO_TOTAL),
    ]
    data = _build_resumen_data(quotes, notes="")
    assert data["mo_total"] == _MO_TOTAL


# ── Bug 3: persisted total used, no recalculation ──


def test_uses_persisted_total_not_recalculated():
    """Colocacion: qty=1.03, price=60135 -> persisted total=61939.
    Naive recalc round(1.03*60135) could give 61939 or differ depending on
    intermediary rounding. We want the persisted value."""
    mo = [{"description": "Colocacion", "quantity": 1.03, "unit_price": 60135, "total": 61939}]
    quotes = [_Q("q1", mo_items=mo, mo_total=61939)]
    data = _build_resumen_data(quotes, notes="")
    assert data["mo_items"][0]["total"] == 61939
    assert data["mo_total"] == 61939


# ── Bug 4: plazo selection ──


def test_plazo_picks_specific_over_a_confirmar():
    """'40 dias' wins over 'A confirmar'."""
    quotes = [
        _Q("q1", plazo="A confirmar"),
        _Q("q2", plazo="40 dias"),
        _Q("q3", plazo="A confirmar"),
    ]
    data = _build_resumen_data(quotes, notes="")
    assert data["plazo"] == "40 dias"


def test_plazo_all_a_confirmar():
    """If all quotes say 'A confirmar', that's what we get."""
    quotes = [
        _Q("q1", plazo="A confirmar"),
        _Q("q2", plazo="A confirmar"),
    ]
    data = _build_resumen_data(quotes, notes="")
    assert data["plazo"] == "A confirmar"


def test_plazo_none_returns_empty():
    """No plazo info at all -> empty string."""
    quotes = [_Q("q1"), _Q("q2")]
    data = _build_resumen_data(quotes, notes="")
    assert data["plazo"] == ""


def test_plazo_mixed_specific_values():
    """If multiple specific plazos exist, first one wins."""
    quotes = [
        _Q("q1", plazo="A confirmar"),
        _Q("q2", plazo="40 dias"),
        _Q("q3", plazo="30 dias"),
    ]
    data = _build_resumen_data(quotes, notes="")
    assert data["plazo"] == "40 dias"
