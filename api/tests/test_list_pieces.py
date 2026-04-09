"""Tests for list_pieces tool — the deterministic source of truth for Paso 1 visible output."""

import pytest
from app.modules.quote_engine.calculator import list_pieces, calculate_quote
from app.modules.agent.agent import AgentService


# ── Unit tests: list_pieces function ─────────────────────────────────────────

class TestListPieces:
    """Verify list_pieces returns correct labels and total m² for display."""

    def test_alvaro_torres_case(self):
        """The exact case from the bug report."""
        result = list_pieces([
            {"description": "Mesada tramo 1", "largo": 4.10, "prof": 0.65},
            {"description": "Mesada tramo 2", "largo": 2.80, "prof": 0.65},
            {"description": "Zócalo", "largo": 6.90, "alto": 0.05},
        ])

        assert result["ok"]

        # Total MUST include zócalo: 2.665 + 1.82 + 0.345 = 4.83
        assert result["total_m2"] == 4.83, f"Expected 4.83, got {result['total_m2']}"

        # Check each piece label
        labels = [p["label"] for p in result["pieces"]]

        # Mesada tramo 1: >3m → must have "2 TRAMOS"
        assert any("tramo 1" in l.lower() and "2 TRAMOS" in l for l in labels), f"Mesada tramo 1 missing 2 TRAMOS: {labels}"

        # Mesada tramo 2: <3m → no "2 TRAMOS"
        tramo2 = [l for l in labels if "tramo 2" in l.lower()]
        assert len(tramo2) == 1
        assert "2 TRAMOS" not in tramo2[0]

        # Zócalo: must use "ml" format, NOT "×" format
        zocalo = [l for l in labels if "calo" in l.lower()]
        assert len(zocalo) == 1
        assert "ml" in zocalo[0], f"Zócalo should show ml: {zocalo[0]}"
        assert "×" not in zocalo[0], f"Zócalo should NOT show ×: {zocalo[0]}"
        assert "6.90" in zocalo[0]

    def test_zocalo_included_in_total(self):
        """Zócalo m² must be included in total."""
        result = list_pieces([
            {"description": "Mesada", "largo": 2.0, "prof": 0.6},
            {"description": "Zócalo", "largo": 2.0, "alto": 0.05},
        ])
        assert result["ok"]
        # 2.0×0.6=1.2 + 2.0×0.05=0.1 = 1.3
        assert result["total_m2"] == 1.3

    def test_zocalo_label_format(self):
        """Zócalo must render as 'Zócalo: X.XX ml'."""
        result = list_pieces([
            {"description": "Zócalo trasero", "largo": 3.50, "alto": 0.05},
        ])
        label = result["pieces"][0]["label"]
        assert "ml" in label
        assert "3.50" in label
        assert "×" not in label

    def test_mesada_3m_gets_2_tramos(self):
        """Mesada ≥ 3m must show '(SE REALIZA EN 2 TRAMOS)'."""
        result = list_pieces([
            {"description": "Mesada cocina", "largo": 3.50, "prof": 0.65},
        ])
        label = result["pieces"][0]["label"]
        assert "2 TRAMOS" in label

    def test_mesada_under_3m_no_tramos(self):
        result = list_pieces([
            {"description": "Mesada", "largo": 2.50, "prof": 0.60},
        ])
        label = result["pieces"][0]["label"]
        assert "2 TRAMOS" not in label

    def test_multiple_identical_pieces(self):
        """Duplicate pieces should be grouped with quantity."""
        result = list_pieces([
            {"description": "Mesada", "largo": 1.0, "prof": 0.6},
            {"description": "Mesada", "largo": 1.0, "prof": 0.6},
            {"description": "Mesada", "largo": 1.0, "prof": 0.6},
        ])
        assert result["ok"]
        assert len(result["pieces"]) == 1
        assert result["pieces"][0].get("qty") == 3
        assert result["total_m2"] == 1.8

    def test_consistency_with_calculate_quote(self):
        """list_pieces total_m2 must match calculate_quote material_m2."""
        pieces = [
            {"description": "Mesada tramo 1", "largo": 4.10, "prof": 0.65},
            {"description": "Mesada tramo 2", "largo": 2.80, "prof": 0.65},
            {"description": "Zócalo", "largo": 6.90, "alto": 0.05},
        ]
        lp_result = list_pieces(pieces)
        cq_result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": pieces,
            "localidad": "Rosario",
            "plazo": "30 dias",
        })
        assert lp_result["total_m2"] == cq_result["material_m2"], (
            f"list_pieces={lp_result['total_m2']} vs calculate_quote={cq_result['material_m2']}"
        )


# ── Agent tool dispatch test ─────────────────────────────────────────────────

class TestListPiecesToolDispatch:
    """Verify the tool is callable through the agent handler."""

    @pytest.mark.asyncio
    async def test_agent_dispatches_list_pieces(self, db_session):
        """Agent must route list_pieces tool correctly."""
        import uuid
        from app.models.quote import Quote, QuoteStatus

        qid = f"test-{uuid.uuid4()}"
        quote = Quote(id=qid, client_name="", project="", messages=[], status=QuoteStatus.DRAFT)
        db_session.add(quote)
        await db_session.commit()

        agent = AgentService()
        result = await agent._execute_tool(
            "list_pieces",
            {"pieces": [
                {"description": "Mesada tramo 1", "largo": 4.10, "prof": 0.65},
                {"description": "Mesada tramo 2", "largo": 2.80, "prof": 0.65},
                {"description": "Zócalo", "largo": 6.90, "alto": 0.05},
            ]},
            quote_id=qid,
            db=db_session,
        )

        assert result["ok"]
        assert result["total_m2"] == 4.83

        labels = [p["label"] for p in result["pieces"]]
        zocalo = [l for l in labels if "calo" in l.lower()]
        assert "ml" in zocalo[0]
        assert "×" not in zocalo[0]


# ── Verify list_pieces is in TOOLS schema ────────────────────────────────────

class TestListPiecesInToolSchema:
    def test_tool_registered(self):
        from app.modules.agent.agent import TOOLS
        tool_names = [t["name"] for t in TOOLS]
        assert "list_pieces" in tool_names

    def test_tool_schema_has_pieces(self):
        from app.modules.agent.agent import TOOLS
        tool = next(t for t in TOOLS if t["name"] == "list_pieces")
        assert "pieces" in tool["input_schema"]["properties"]
        assert tool["input_schema"]["properties"]["pieces"]["type"] == "array"
