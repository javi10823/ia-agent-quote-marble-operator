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
    unmatched = await _canonicalize_quotes_data_from_db(qid, llm_quotes, db_session)
    # Sin match → no sobrescribe, pero lo REPORTA para que generate_documents
    # rechace: los montos del LLM nunca van al PDF.
    assert unmatched == ["GRANITO COMPLETAMENTE DISTINTO"]
    assert llm_quotes[0]["sectors"] == [{"label": "X", "pieces": ["original"]}]


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


def test_match_prefiere_nombre_exacto_sobre_substring():
    from app.modules.agent.agent import _match_calc_for_material
    zeus = {"material_name": "SILESTONE BLANCO ZEUS", "total_ars": 1}
    suede = {"material_name": "SILESTONE BLANCO ZEUS SUEDE", "total_ars": 2}
    assert _match_calc_for_material("SILESTONE BLANCO ZEUS", [suede, zeus]) is zeus
    assert _match_calc_for_material("SILESTONE BLANCO ZEUS SUEDE", [zeus, suede]) is suede


def test_match_substring_ambiguo_no_elige():
    from app.modules.agent.agent import _match_calc_for_material
    a = {"material_name": "SILESTONE BLANCO ZEUS 20MM"}
    b = {"material_name": "SILESTONE BLANCO ZEUS SUEDE"}
    assert _match_calc_for_material("SILESTONE BLANCO ZEUS", [a, b]) is None


def test_match_substring_unico_tolera_espesor():
    from app.modules.agent.agent import _match_calc_for_material
    a = {"material_name": "SILESTONE BLANCO NORTE 20MM"}
    assert _match_calc_for_material("SILESTONE BLANCO NORTE", [a]) is a


@pytest.mark.asyncio
async def test_sin_calculo_persistido_reporta_todos_los_materiales(db_session):
    qid = "test-canonical-004"
    db_session.add(Quote(id=qid, client_name="SIN CALC", material=None, project="X", quote_breakdown=None))
    await db_session.commit()
    llm_quotes = [{"material_name": "Silestone X", "total_ars": 999}]
    assert await _canonicalize_quotes_data_from_db(qid, llm_quotes, db_session) == ["Silestone X"]


def test_stash_guarda_calculo_de_otro_material():
    from app.modules.agent.agent import _stash_prior_calcs
    old = {"material_name": "SILESTONE BLANCO NORTE", "total_ars": 10, "dual_read_result": {"x": 1}}
    prior = _stash_prior_calcs(old, "PURASTONE BLANCO PALOMA")
    assert len(prior) == 1 and prior[0]["material_name"] == "SILESTONE BLANCO NORTE"
    assert "dual_read_result" not in prior[0]


def test_stash_mismo_material_no_acumula():
    from app.modules.agent.agent import _stash_prior_calcs
    old = {"material_name": "SILESTONE BLANCO NORTE", "total_ars": 10}
    assert _stash_prior_calcs(old, "silestone blanco norte") == []


def test_stash_reemplaza_si_vuelve_al_material_previo():
    from app.modules.agent.agent import _stash_prior_calcs
    a = {"material_name": "A", "total_ars": 1}
    b = {"material_name": "B", "total_ars": 2, "_prior_calcs": [a]}
    # vuelve a A: B pasa a prior y A (vieja) se descarta
    prior = _stash_prior_calcs(b, "A")
    assert [p["material_name"] for p in prior] == ["B"]


@pytest.mark.asyncio
async def test_canonicaliza_material_previo_desde_prior_calcs(db_session):
    qid = "test-canonical-005"
    a = {"material_name": "SILESTONE BLANCO NORTE", "total_ars": 111, "total_usd": 5, "material_m2": 1.0}
    b = {"material_name": "PURASTONE BLANCO PALOMA", "total_ars": 222, "total_usd": 6,
         "material_m2": 1.0, "_prior_calcs": [a]}
    db_session.add(Quote(id=qid, client_name="MULTI", material=None, project="X", quote_breakdown=b))
    await db_session.commit()
    llm = [
        {"material_name": "SILESTONE BLANCO NORTE", "total_ars": 999999},
        {"material_name": "PURASTONE BLANCO PALOMA", "total_ars": 888888},
    ]
    assert await _canonicalize_quotes_data_from_db(qid, llm, db_session) == []
    assert llm[0]["total_ars"] == 111 and llm[1]["total_ars"] == 222


@pytest.mark.asyncio
async def test_generate_documents_rechaza_sin_calculo_guardado(db_session):
    """Los montos que escribe el LLM nunca llegan al PDF."""
    from app.modules.agent.agent import AgentService
    qid = "test-canonical-006"
    db_session.add(Quote(id=qid, client_name="Juan", material=None, project="X", quote_breakdown=None))
    await db_session.commit()
    res = await AgentService()._execute_tool(
        "generate_documents",
        {"quotes": [{"client_name": "Juan", "project": "X", "material_name": "SILESTONE BLANCO NORTE",
                     "total_ars": 1, "total_usd": 1}]},
        quote_id=qid, db=db_session,
    )
    assert res["ok"] is False
    assert "cálculo guardado" in res["error"]
