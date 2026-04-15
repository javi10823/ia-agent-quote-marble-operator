"""PR #12 — canonicalizar sectors/totales desde calc_result persistido.

Bug DINALE 15/04/2026: el LLM construía sectors con largos inventados
(ME01-B 2.15 → 1.10, ME03-B 4.50 → 2.30) y descripciones truncadas
('ME01-B' en vez de 'ME01-B Mesada recta c/zócalo h:10cm'). El
calc_result persistido en quote.quote_breakdown tiene los datos
correctos — los usamos para sobrescribir lo que pasó el LLM.
"""
import pytest

from app.modules.agent.agent import _canonicalize_quotes_data_from_db
from app.models.quote import Quote


@pytest.mark.asyncio
async def test_canonicalize_overrides_sectors_from_db(db_session):
    qid = "test-canonical-001"
    canonical = {
        "ok": True,
        "material_name": "GRANITO GRIS MARA EXTRA 2 ESP",
        "sectors": [{
            "label": "Cocina",
            "pieces": [
                "2.15 × 0.60 ME01-B Mesada recta c/zócalo h:10cm *",
                "4.50 × 0.60 ME03-B Mesada recta c/zócalo h:10cm *",
            ],
        }],
        "material_m2": 31.37,
        "material_total": 5994846,
        "total_ars": 7378519,
    }
    q = Quote(
        id=qid,
        client_name="DINALE S.A.",
        material="GRANITO GRIS MARA EXTRA 2 ESP",
        project="Test", quote_breakdown=canonical,
    )
    db_session.add(q)
    await db_session.commit()

    # LLM-built dict with mangled sectors (DINALE bug)
    llm_quotes = [{
        "client_name": "DINALE S.A.",
        "material_name": "GRANITO GRIS MARA EXTRA 2 ESP",
        "sectors": [{"label": "Cocina", "pieces": [
            "1.10 × 0.60 ME01-B *",   # WRONG largo + truncated desc
            "2.30 × 0.60 ME03-B *",   # WRONG largo + truncated desc
        ]}],
        "material_m2": 99,            # wrong
        "total_ars": 99999,           # wrong
    }]

    await _canonicalize_quotes_data_from_db(qid, llm_quotes, db_session)

    # Sectors should now be the canonical ones
    assert llm_quotes[0]["sectors"] == canonical["sectors"]
    assert llm_quotes[0]["material_m2"] == 31.37
    assert llm_quotes[0]["total_ars"] == 7378519
    # Visual labels preserve full description
    label = llm_quotes[0]["sectors"][0]["pieces"][0]
    assert "2.15" in label, f"largo correcto debe estar: {label}"
    assert "Mesada recta" in label, f"descripción full debe estar: {label}"


@pytest.mark.asyncio
async def test_canonicalize_skips_when_no_match(db_session):
    """Si no hay calc_result persistido para el material, no toca nada."""
    qid = "test-canonical-002"
    q = Quote(
        id=qid, client_name="OTRO CLIENTE",
        material="DEKTON KELYA", project="X", quote_breakdown={"material_name": "DEKTON KELYA"},
    )
    db_session.add(q)
    await db_session.commit()

    llm_quotes = [{
        "material_name": "GRANITO COMPLETAMENTE DISTINTO",
        "sectors": [{"label": "X", "pieces": ["original"]}],
        "total_ars": 12345,
    }]
    await _canonicalize_quotes_data_from_db(qid, llm_quotes, db_session)
    # Sin match → no debe sobrescribir
    assert llm_quotes[0]["sectors"] == [{"label": "X", "pieces": ["original"]}]
    assert llm_quotes[0]["total_ars"] == 12345


@pytest.mark.asyncio
async def test_canonicalize_handles_missing_material_name(db_session):
    """Defensive: qdata sin material_name no debe crashear."""
    qid = "test-canonical-003"
    q = Quote(id=qid, client_name="X", material=None, project="X", quote_breakdown={})
    db_session.add(q)
    await db_session.commit()
    llm_quotes = [{"sectors": [{"label": "X", "pieces": ["a"]}]}]
    # Should not raise
    await _canonicalize_quotes_data_from_db(qid, llm_quotes, db_session)
