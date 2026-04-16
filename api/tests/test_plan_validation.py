"""PR #25 — validación estricta de piezas cuando hay plano adjunto.

Gateada a has_plan: briefs de texto puro (DINALE, Estudio 72 edificio)
NO pasan por esta validación y mantienen comportamiento legacy.
"""
import pytest

from app.modules.agent.agent import _validate_plan_pieces


def test_missing_tipo_is_rejected():
    pieces = [{"description": "M1", "largo": 1.72, "prof": 0.75}]
    errs = _validate_plan_pieces(pieces)
    assert any("tipo" in e.lower() for e in errs)


def test_valid_mesada_and_zocalo_pass():
    pieces = [
        {"description": "Mesada principal", "tipo": "mesada", "largo": 1.72, "prof": 0.75},
        {"description": "Zócalo fondo", "tipo": "zocalo", "largo": 1.74, "alto": 0.07},
    ]
    errs = _validate_plan_pieces(pieces)
    assert errs == [], f"Expected no errors: {errs}"


def test_mesada_with_shallow_prof_rejected():
    """Mesada con prof < 0.30 → sospecha de zócalo mal tipado."""
    pieces = [{"description": "Fondo", "tipo": "mesada", "largo": 1.74, "prof": 0.07}]
    errs = _validate_plan_pieces(pieces)
    assert any("zócalo" in e.lower() or "zocalo" in e.lower() for e in errs)


def test_zocalo_tall_splashback_accepted():
    """PR #42 — zócalos hasta 60 cm se aceptan (splashback baños/lavaderos
    industriales). Antes el límite era 15 cm y rechazaba ME04 DINALE (50cm)."""
    pieces = [{"description": "Splashback", "tipo": "zocalo", "largo": 2.30, "alto": 0.50}]
    errs = _validate_plan_pieces(pieces)
    assert errs == [], f"Zócalo de 50cm debe aceptarse: {errs}"


def test_zocalo_above_60cm_rejected():
    """Más de 60 cm ya es alzada/revestimiento, no zócalo."""
    pieces = [{"description": "Pared", "tipo": "zocalo", "largo": 2.0, "alto": 0.80}]
    errs = _validate_plan_pieces(pieces)
    assert any("alzada" in e.lower() or "revestimiento" in e.lower() for e in errs)


def test_zocalo_missing_alto_rejected():
    pieces = [{"description": "Z", "tipo": "zocalo", "largo": 1.74}]
    errs = _validate_plan_pieces(pieces)
    assert any("alto" in e.lower() for e in errs)


def test_alzada_with_low_alto_rejected():
    pieces = [{"description": "A", "tipo": "alzada", "largo": 0.60, "alto": 0.20}]
    errs = _validate_plan_pieces(pieces)
    assert any("alzada" in e.lower() for e in errs)


def test_invalid_tipo_rejected():
    pieces = [{"description": "X", "tipo": "lavadero", "largo": 1.0, "prof": 0.5}]
    errs = _validate_plan_pieces(pieces)
    assert any("tipo" in e.lower() for e in errs)


def test_a1335_canonical_case_passes():
    """Caso canónico A1335 — 2 tramos de mesada + 3 zócalos."""
    pieces = [
        {"description": "Mesada cocina",  "tipo": "mesada", "largo": 1.72, "prof": 0.75},
        {"description": "Retorno cocina", "tipo": "mesada", "largo": 0.60, "prof": 1.55},
        {"description": "Zócalo fondo",        "tipo": "zocalo", "largo": 1.74, "alto": 0.07},
        {"description": "Zócalo lateral izq",  "tipo": "zocalo", "largo": 1.55, "alto": 0.07},
        {"description": "Zócalo lateral der",  "tipo": "zocalo", "largo": 0.75, "alto": 0.07},
    ]
    errs = _validate_plan_pieces(pieces)
    assert errs == [], f"A1335 canonical should pass: {errs}"


def test_empty_pieces_list_does_not_crash():
    assert _validate_plan_pieces([]) == []


def test_non_dict_piece_flagged():
    errs = _validate_plan_pieces(["not a dict"])
    assert any("formato" in e.lower() for e in errs)
