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

        # Total = suma de displays half-up (PR consistencia m²):
        # 2.67 (2.665 up) + 1.82 + 0.35 (0.345 up) = 4.84
        assert result["total_m2"] == 4.84, f"Expected 4.84, got {result['total_m2']}"

        # Check each piece label
        labels = [p["label"] for p in result["pieces"]]

        # Mesada tramo 1: >3m → must have "2 TRAMOS"
        assert any("tramo 1" in l.lower() and "2 TRAMOS" in l for l in labels), f"Mesada tramo 1 missing 2 TRAMOS: {labels}"

        # Mesada tramo 2: <3m → no "2 TRAMOS"
        tramo2 = [l for l in labels if "tramo 2" in l.lower()]
        assert len(tramo2) == 1
        assert "2 TRAMOS" not in tramo2[0]

        # Zócalo: must use "ml" format, NOT "×" format
        zocalo = [l for l in labels if "ZOC" in l]
        assert len(zocalo) == 1
        assert "ML" in zocalo[0], f"Zócalo should show ML: {zocalo[0]}"
        assert "ZOC" in zocalo[0], f"Zócalo should show ZOC: {zocalo[0]}"
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
        """Zócalo must render as 'X.XXML X Y.YY ZOC'."""
        result = list_pieces([
            {"description": "Zócalo trasero", "largo": 3.50, "alto": 0.05},
        ])
        label = result["pieces"][0]["label"]
        assert "ML" in label
        assert "ZOC" in label
        assert "3.50" in label
        assert "0.05" in label

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
            "project": "Cocina",
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
        assert result["total_m2"] == 4.84

        labels = [p["label"] for p in result["pieces"]]
        zocalo = [l for l in labels if "ZOC" in l]
        assert "ML" in zocalo[0]
        assert "ZOC" in zocalo[0]


class TestMesadaConZocaloNoCollapsed:
    """Regression: 'Mesada recta c/zócalo h:10cm' must render as MESADA, not ZOC.

    Bug DINALE 14/04/2026: el PDF colapsaba todas las tipologías edificio
    (ME01-B, ME02-B, etc.) con descripciones tipo "Mesada recta c/zócalo h:10cm"
    a filas "X.XXML X 0.60 ZOC" porque el check `"zócalo" in desc` matcheaba
    la palabra dentro de la descripción. Solo deben colapsarse piezas cuya
    descripción EMPIECE con "zócalo".
    """

    def test_mesada_con_zocalo_keeps_description(self):
        result = list_pieces([
            {"description": "ME01-B Mesada recta c/zócalo h:10cm", "largo": 2.15, "prof": 0.60},
        ])
        assert result["ok"]
        label = result["pieces"][0]["label"]
        # Must preserve full description, NOT collapse to "ZOC"
        assert "Mesada recta" in label
        assert "ME01-B" in label
        assert "ZOC" not in label

    def test_mesada_con_zocalo_alto_50cm(self):
        """ME04-B con zócalo h:50cm sigue siendo mesada."""
        result = list_pieces([
            {"description": "Mesada recta c/zócalo h:50cm", "largo": 2.30, "prof": 0.60},
        ])
        label = result["pieces"][0]["label"]
        assert "Mesada" in label
        assert "ZOC" not in label

    def test_pure_zocalo_still_collapses(self):
        """Zócalo puro (descripción empieza con 'Zócalo') se sigue colapsando."""
        result = list_pieces([
            {"description": "Zócalo trasero", "largo": 3.50, "alto": 0.05},
        ])
        label = result["pieces"][0]["label"]
        assert "ZOC" in label
        assert "ML" in label

    def test_calculate_quote_sectors_keep_mesada_label(self):
        """calculate_quote (código en sectors) también debe preservar label."""
        result = calculate_quote({
            "client_name": "TEST",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [
                {"description": "ME01-B Mesada recta c/zócalo h:10cm",
                 "largo": 2.15, "prof": 0.60, "m2_override": 1.625},
                {"description": "ME04-B Mesada recta c/zócalo h:50cm",
                 "largo": 2.30, "prof": 0.60, "quantity": 4, "m2_override": 3.130},
            ],
            "localidad": "rosario",
            "plazo": "4 meses",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
        })
        assert result.get("ok"), result
        sectors = result.get("sectors", [])
        assert sectors
        labels = sectors[0]["pieces"]
        # Ninguno debe ser ZOC puro: el brief tiene solo mesadas c/zócalo
        assert not any(" ZOC" in lbl.split("*")[0].rstrip() for lbl in labels), labels
        # Debe preservar "Mesada" en los labels
        assert any("Mesada" in lbl for lbl in labels), labels


class TestFrentinDoesNotDoubleCountMaterial:
    """Regression: faldón/frentín listado como pieza separada NO debe
    sumar m² al material (DINALE 14/04/2026).

    Antes del fix: brief "Faldón recto — 2.90 ml" se convertía en una
    pieza con prof=0.05 default → sumaba 0.145 m² al material bruto
    Y al mismo tiempo se cobraba MO "Armado frentín" por 2.90 ml →
    doble cobro.
    """

    def test_faldon_excluded_from_material_m2(self):
        from app.modules.quote_engine.calculator import calculate_m2
        total, details = calculate_m2([
            {"description": "Mesada", "largo": 2.15, "prof": 0.60, "m2_override": 1.625},
            {"description": "Faldón recto", "largo": 2.90, "prof": 0.05},
        ])
        # Solo la mesada contribuye. m2_override=1.625 → half-up 2dec = 1.63.
        assert total == 1.63, f"Expected 1.63 (half-up de 1.625, faldón no se suma), got {total}"
        faldon = next(d for d in details if "Faldón" in d["description"])
        assert faldon["_is_frentin"] is True
        assert faldon["m2"] == 0, f"Faldón m² debe ser 0: {faldon}"

    def test_frentin_piece_same_treatment(self):
        """'Frentín' (sin tilde) debe comportarse igual."""
        from app.modules.quote_engine.calculator import calculate_m2
        total, _ = calculate_m2([
            {"description": "Mesada", "largo": 2.0, "prof": 0.60},
            {"description": "Frentin recto", "largo": 1.80, "prof": 0.10},
        ])
        # Solo mesada: 2.0 × 0.6 = 1.2
        assert total == 1.2, f"Expected 1.2, got {total}"

    def test_list_pieces_faldon_label_uses_ml(self):
        """list_pieces para Paso 1 renderiza faldón como 'X.XXML FALDON'."""
        result = list_pieces([
            {"description": "Mesada", "largo": 2.15, "prof": 0.60},
            {"description": "Faldón recto", "largo": 2.90, "prof": 0.05},
        ])
        labels = [p["label"] for p in result["pieces"]]
        faldon = [l for l in labels if "FALDON" in l]
        assert len(faldon) == 1, f"Expected 1 FALDON label, got: {labels}"
        assert "2.90ML" in faldon[0], f"Expected 'X.XXML FALDON', got: {faldon[0]}"

    def test_sectors_label_includes_quantity_multiplier(self):
        """PR #14 (B3) — labels en sectors deben incluir (×N) cuando
        quantity > 1. Caso DINALE: ME04-B con 4 unidades, ME04b-B con 2.
        Antes solo se agrupaban duplicados textuales, no piezas con qty
        explícito."""
        from app.modules.quote_engine.calculator import calculate_quote
        result = calculate_quote({
            "client_name": "DINALE", "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "project": "Cocina",
            "pieces": [
                {"description": "ME01-B Mesada recta c/zócalo h:10cm",
                 "largo": 2.15, "prof": 0.60, "m2_override": 1.625},
                {"description": "ME04-B Mesada recta c/zócalo h:50cm",
                 "largo": 2.30, "prof": 0.60, "quantity": 4, "m2_override": 12.520},
                {"description": "ME04b-B Mesada recta",
                 "largo": 1.45, "prof": 0.50, "quantity": 2, "m2_override": 1.840},
            ],
            "localidad": "rosario", "plazo": "4 meses",
            "is_edificio": True, "colocacion": False,
            "pileta": "empotrada_cliente",
        })
        assert result.get("ok"), result
        sectors = result.get("sectors", [])
        labels = sectors[0]["pieces"]
        # ME01-B (qty=1) — sin multiplicador
        me01 = [l for l in labels if "ME01-B" in l]
        assert me01 and "(×" not in me01[0], f"qty=1 no debe llevar (×N): {me01}"
        # ME04-B (qty=4) — con multiplicador
        me04 = [l for l in labels if "ME04-B" in l]
        assert me04 and "(×4)" in me04[0], f"qty=4 debe mostrar (×4): {me04}"
        # ME04b-B (qty=2) — con multiplicador
        me04b = [l for l in labels if "ME04b-B" in l]
        assert me04b and "(×2)" in me04b[0], f"qty=2 debe mostrar (×2): {me04b}"

    def test_total_mo_distinct_from_grand_total(self):
        """PR #11 — TOTAL MO != GRAND TOTAL. Antes el render usaba total_ars
        (que es el grand total para ARS) en la fila 'TOTAL MO', dando la
        impresión de que MO == grand total."""
        from app.modules.quote_engine.calculator import (
            calculate_quote, build_deterministic_paso2,
        )
        r = calculate_quote({
            "client_name": "DINALE",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.60, "m2_override": 31.37}],
            "localidad": "rosario", "plazo": "4 meses",
            "is_edificio": True, "colocacion": False,
            "pileta": "empotrada_cliente", "pileta_qty": 19,
            "discount_pct": 15, "mo_discount_pct": 5,
        })
        # Calc result expone total_mo_ars (subtotal MO solo)
        assert "total_mo_ars" in r
        assert r["total_mo_ars"] < r["total_ars"], (
            f"MO subtotal ({r['total_mo_ars']}) debe ser < grand total "
            f"({r['total_ars']}) cuando hay material"
        )
        out = build_deterministic_paso2(r)
        # La fila TOTAL MO debe mostrar el subtotal MO, NO el grand total
        import re
        mo_row_match = re.search(r'\*\*TOTAL MO\*\*[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\*\*\$([\d.]+)', out)
        if not mo_row_match:
            # try simpler format (residential, fewer columns)
            mo_row_match = re.search(r'\*\*TOTAL MO\*\*[^|]*\|[^|]*\|[^|]*\|[^|]*\*\*\$([\d.]+)', out)
        assert mo_row_match, f"No TOTAL MO row found in:\n{out}"
        rendered_mo = int(mo_row_match.group(1).replace(".", ""))
        assert rendered_mo == r["total_mo_ars"], (
            f"TOTAL MO render ({rendered_mo}) debe igualar total_mo_ars "
            f"({r['total_mo_ars']}), NO total_ars ({r['total_ars']})"
        )

    def test_grand_total_visually_emphasized(self):
        """PR #11 — Grand Total debe destacarse visualmente en el render
        para que el operador lo identifique de un vistazo."""
        from app.modules.quote_engine.calculator import (
            calculate_quote, build_deterministic_paso2,
        )
        r = calculate_quote({
            "client_name": "T", "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "project": "Cocina",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.60}],
            "localidad": "rosario", "plazo": "30 dias",
            "is_edificio": True, "colocacion": False,
            "pileta": "empotrada_cliente",
        })
        out = build_deterministic_paso2(r)
        assert "## 💰 GRAND TOTAL" in out, "Grand total debe usar heading h2 con emoji"
        assert "### " in out, "Grand total amount debe usar heading h3"

    def test_frentin_qty_uses_ml_unit(self):
        """PR #12 — La fila de Armado frentín en MO debe decir 'ml' no 'm²'."""
        from app.modules.quote_engine.calculator import (
            calculate_quote, build_deterministic_paso2,
        )
        r = calculate_quote({
            "client_name": "T", "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "project": "Cocina",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.60, "m2_override": 5.0},
                {"description": "Faldón recto", "largo": 2.90, "prof": 0.05},
            ],
            "localidad": "rosario", "plazo": "30 dias",
            "is_edificio": True, "colocacion": False,
            "pileta": "empotrada_cliente", "frentin": True,
        })
        out = build_deterministic_paso2(r)
        # Buscar la fila de Armado frentín y asegurar 'ml' (no 'm²')
        for line in out.splitlines():
            if "Armado frentín" in line or "Armado frentin" in line:
                assert "ml" in line, f"Frentín debe usar 'ml': {line}"
                assert "m²" not in line, f"Frentín NO debe decir 'm²': {line}"
                break
        else:
            raise AssertionError(f"No 'Armado frentín' row found:\n{out}")

    def test_build_paso2_omits_faldon_row(self):
        """PR #9 — el render del Paso 2 NO debe incluir fila para faldón.
        DINALE 15/04/2026: aparecía 'Faldón recto 2,9 x 0,05 → 0,00' en
        el bloque material aunque el m² ya era 0 (PR #164)."""
        from app.modules.quote_engine.calculator import build_deterministic_paso2
        calc_result = calculate_quote({
            "client_name": "DINALE",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.60, "m2_override": 31.37},
                {"description": "Faldón recto", "largo": 2.90, "prof": 0.05},
            ],
            "localidad": "rosario",
            "plazo": "4 meses",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "frentin": True,
        })
        paso2 = build_deterministic_paso2(calc_result)
        # No debe haber línea de tabla 'Faldón' en el bloque material
        material_section = paso2.split("MANO DE OBRA")[0] if "MANO DE OBRA" in paso2 else paso2
        assert "Faldón" not in material_section and "Faldon" not in material_section, (
            f"Faldón no debe renderizarse en bloque material. Got:\n{material_section}"
        )
        # Pero SÍ debe seguir apareciendo Armado frentín en MO
        assert "frentín" in paso2.lower() or "frentin" in paso2.lower()

    def test_calculate_quote_faldon_as_mo_only(self):
        """calculate_quote completo: faldón NO suma material, sí genera
        línea MO 'Armado frentín' con ml (no m²)."""
        result = calculate_quote({
            "client_name": "DINALE",
            "project": "Cocina",
            "material": "GRANITO GRIS MARA EXTRA 2 ESP",
            "pieces": [
                {"description": "Mesada", "largo": 2.0, "prof": 0.60, "m2_override": 31.37},
                {"description": "Faldón recto", "largo": 2.90, "prof": 0.05},
            ],
            "localidad": "rosario",
            "plazo": "4 meses",
            "is_edificio": True,
            "colocacion": False,
            "pileta": "empotrada_cliente",
            "frentin": True,
        })
        assert result.get("ok"), result
        # Material m²: solo la mesada (31.37), NO incluye 0.145 del faldón
        assert result["material_m2"] == 31.37, (
            f"material_m2 debe ser 31.37, got {result['material_m2']}"
        )
        # MO incluye Armado frentín con 2.90 ml
        mo = result["mo_items"]
        frentin_mo = [m for m in mo if "frentín" in m["description"].lower() or "frentin" in m["description"].lower()]
        assert len(frentin_mo) == 1
        assert frentin_mo[0]["quantity"] == 2.90


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
