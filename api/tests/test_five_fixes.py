"""Tests for the 5 fixes: zócalo format, delivery tiers, pulido extra, espesor, flete default."""

import pytest
from app.modules.quote_engine.calculator import calculate_quote, _find_flete


def _base_input(**overrides):
    base = {
        "client_name": "Test",
        "project": "Cocina",
        "material": "Silestone Blanco Norte",
        "pieces": [
            {"description": "Mesada", "largo": 2.0, "prof": 0.6},
            {"description": "Zócalo", "largo": 2.0, "alto": 0.05},
        ],
        "localidad": "Rosario",
        "plazo": "40 dias desde la toma de medidas",
    }
    base.update(overrides)
    return base


# ── Fix 1: Zócalo format ────────────────────────────────────────────────────

class TestZocaloFormat:
    def test_zocalo_shows_ml_not_rectangular(self):
        result = calculate_quote(_base_input(
            pieces=[
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                {"description": "Zócalo", "largo": 6.90, "alto": 0.05},
            ]
        ))
        assert result["ok"]
        labels = result["sectors"][0]["pieces"]
        zocalo_labels = [l for l in labels if "ZOC" in l]
        assert len(zocalo_labels) == 1
        assert "ML" in zocalo_labels[0], f"Zócalo should show ML: {zocalo_labels[0]}"
        assert "ZOC" in zocalo_labels[0], f"Zócalo should show ZOC: {zocalo_labels[0]}"
        assert "×" not in zocalo_labels[0], f"Zócalo should not show ×: {zocalo_labels[0]}"

    def test_zocalo_no_2_tramos(self):
        """Zócalo > 3m should NOT get '(SE REALIZA EN 2 TRAMOS)'."""
        result = calculate_quote(_base_input(
            pieces=[
                {"description": "Mesada", "largo": 2.0, "prof": 0.6},
                {"description": "Zócalo", "largo": 6.90, "alto": 0.05},
            ]
        ))
        assert result["ok"]
        labels = result["sectors"][0]["pieces"]
        zocalo_labels = [l for l in labels if "ZOC" in l]
        assert "2 TRAMOS" not in zocalo_labels[0]

    def test_mesada_still_gets_2_tramos(self):
        """Mesada > 3m should still get '(SE REALIZA EN 2 TRAMOS)' for residential."""
        result = calculate_quote(_base_input(
            pieces=[{"description": "Mesada", "largo": 4.10, "prof": 0.65}]
        ))
        assert result["ok"]
        labels = result["sectors"][0]["pieces"]
        mesada_labels = [l for l in labels if "mesada" in l.lower()]
        assert "2 TRAMOS" in mesada_labels[0]

    def test_edificio_mesada_no_2_tramos_legend(self):
        """Edificio with mesada > 3m should NOT add '(SE REALIZA EN 2 TRAMOS)'.
        The tipología suffix (X 6, X 8) already lists how many pieces go."""
        result = calculate_quote(_base_input(
            pieces=[{"description": "Mesada DC-02", "largo": 3.00, "prof": 1.00}],
            is_edificio=True,
        ))
        assert result["ok"]
        labels = result["sectors"][0]["pieces"]
        mesada_labels = [l for l in labels if "mesada" in l.lower()]
        assert mesada_labels, "expected at least one mesada label"
        assert "2 TRAMOS" not in mesada_labels[0], (
            f"Edificio should NOT include '2 TRAMOS' legend, got: {mesada_labels[0]}"
        )

    def test_list_pieces_edificio_flag_suppresses_legend(self):
        """list_pieces(is_edificio=True) must not add the 2 TRAMOS legend."""
        from app.modules.quote_engine.calculator import list_pieces
        pieces = [{"description": "Mesada", "largo": 4.10, "prof": 0.65}]
        # Residential default → legend present
        res_default = list_pieces(pieces)
        assert any("2 TRAMOS" in p["label"] for p in res_default["pieces"])
        # Edificio mode → legend absent
        res_edif = list_pieces(pieces, is_edificio=True)
        assert not any("2 TRAMOS" in p["label"] for p in res_edif["pieces"])


# ── Fix 2: Delivery days tiers ──────────────────────────────────────────────

class TestDeliveryTiers:
    def test_small_job_40_days_when_range_disabled(self):
        """With range_enabled=false (current config), all jobs get default 40 días."""
        result = calculate_quote(_base_input(
            pieces=[{"description": "Mesada", "largo": 1.0, "prof": 0.6}],
        ))
        assert result["ok"]
        assert "40" in result["delivery_days"]

    def test_medium_job_40_days_when_range_disabled(self):
        """With range_enabled=false, medium jobs also get 40 días."""
        result = calculate_quote(_base_input(
            pieces=[
                {"description": "Mesada", "largo": 3.5, "prof": 0.6},
                {"description": "Mesada 2", "largo": 2.0, "prof": 0.6},
            ],
        ))
        assert result["ok"]
        assert "40" in result["delivery_days"]

    def test_large_job_40_days(self):
        """> 6 m² → 40 días."""
        result = calculate_quote(_base_input(
            pieces=[
                {"description": "Mesada", "largo": 4.0, "prof": 0.65},
                {"description": "Mesada 2", "largo": 3.0, "prof": 0.65},
                {"description": "Mesada 3", "largo": 3.0, "prof": 0.65},
            ],
        ))
        assert result["ok"]
        assert result["material_m2"] > 6, f"Got {result['material_m2']}"
        assert "40" in result["delivery_days"]

    def test_explicit_plazo_not_overridden(self):
        """If operator sends explicit plazo, don't apply tier."""
        result = calculate_quote(_base_input(
            pieces=[{"description": "Mesada", "largo": 1.0, "prof": 0.6}],
            plazo="45 dias hábiles",
        ))
        assert result["ok"]
        assert "45" in result["delivery_days"]

    def test_tier_with_accented_plazo(self):
        """Claude may pass '40 días' with accent — tier should still apply."""
        result = calculate_quote(_base_input(
            pieces=[{"description": "Mesada", "largo": 1.0, "prof": 0.6}],
            plazo="40 días desde la toma de medidas",
        ))
        assert result["ok"]
        assert "40" in result["delivery_days"], f"Expected 40 dias (range_enabled=false), got: {result['delivery_days']}"

    def test_tier_with_short_plazo(self):
        """Claude may pass just '40 dias' — tier should still apply."""
        result = calculate_quote(_base_input(
            pieces=[{"description": "Mesada", "largo": 1.0, "prof": 0.6}],
            plazo="40 dias",
        ))
        assert result["ok"]
        assert "40" in result["delivery_days"], f"Expected 40 dias (range_enabled=false), got: {result['delivery_days']}"


# ── Fix 3: Pulido cantos extra ──────────────────────────────────────────────

class TestPulidoExtra:
    def test_rosario_no_pulido_extra(self):
        """Rosario: pulido_extra=false → no extra item."""
        result = calculate_quote(_base_input(localidad="Rosario", colocacion=True))
        assert result["ok"]
        descs = [m["description"].lower() for m in result["mo_items"]]
        assert not any("pulido de cantos" in d for d in descs)

    def test_funes_no_pulido_extra(self):
        """Funes: pulido_extra=false → no extra."""
        result = calculate_quote(_base_input(localidad="Funes", colocacion=True))
        assert result["ok"]
        descs = [m["description"].lower() for m in result["mo_items"]]
        assert not any("pulido de cantos" in d for d in descs)

    def test_roldan_no_pulido_extra(self):
        """Roldán: pulido_extra=false → no extra."""
        result = calculate_quote(_base_input(localidad="Roldan", colocacion=True))
        assert result["ok"]
        descs = [m["description"].lower() for m in result["mo_items"]]
        assert not any("pulido de cantos" in d for d in descs)

    def test_puerto_san_martin_has_pulido_extra(self):
        """Puerto San Martín: pulido_extra=true + colocación → extra item."""
        result = calculate_quote(_base_input(localidad="puerto san martin", colocacion=True))
        assert result["ok"]
        descs = [m["description"].lower() for m in result["mo_items"]]
        assert any("pulido de cantos" in d for d in descs), f"Expected pulido extra: {descs}"

    def test_pulido_extra_is_half_flete(self):
        """Pulido extra price should be flete / 2."""
        result = calculate_quote(_base_input(localidad="puerto san martin", colocacion=True))
        assert result["ok"]
        flete = next(m for m in result["mo_items"] if "flete" in m["description"].lower())
        pulido = next(m for m in result["mo_items"] if "pulido de cantos" in m["description"].lower())
        assert pulido["total"] == round(flete["unit_price"] / 2)

    def test_no_colocacion_no_pulido_extra(self):
        """Without colocación, no pulido extra even in distant zone."""
        result = calculate_quote(_base_input(localidad="puerto san martin", colocacion=False))
        assert result["ok"]
        descs = [m["description"].lower() for m in result["mo_items"]]
        assert not any("pulido de cantos" in d for d in descs)


# ── Fix 4: Espesor not duplicated ───────────────────────────────────────────

class TestEspesor:
    def test_thickness_in_breakdown(self):
        """Breakdown should include thickness_mm from catalog."""
        result = calculate_quote(_base_input())
        assert result["ok"]
        assert "thickness_mm" in result

    def test_silestone_default_20mm(self):
        """Silestone default thickness should be 20."""
        result = calculate_quote(_base_input())
        assert result["ok"]
        assert result["thickness_mm"] == 20


# ── Fix 5: Flete default + skip_flete ───────────────────────────────────────

class TestFleteDefault:
    def test_empty_localidad_defaults_to_rosario(self):
        """Empty localidad should fallback to Rosario flete."""
        result = calculate_quote(_base_input(localidad=""))
        assert result["ok"]
        flete = [m for m in result["mo_items"] if "flete" in m["description"].lower()]
        assert len(flete) == 1, f"Expected flete: {[m['description'] for m in result['mo_items']]}"

    def test_unknown_zone_falls_back_to_rosario(self):
        """Unknown zone should fallback to Rosario."""
        result = calculate_quote(_base_input(localidad="atlantida"))
        assert result["ok"]
        flete = [m for m in result["mo_items"] if "flete" in m["description"].lower()]
        assert len(flete) == 1

    def test_skip_flete_no_flete(self):
        """skip_flete=True should skip flete entirely."""
        result = calculate_quote(_base_input(skip_flete=True))
        assert result["ok"]
        flete = [m for m in result["mo_items"] if "flete" in m["description"].lower()]
        assert len(flete) == 0

    def test_normal_has_flete(self):
        """Normal quote always has flete."""
        result = calculate_quote(_base_input())
        assert result["ok"]
        flete = [m for m in result["mo_items"] if "flete" in m["description"].lower()]
        assert len(flete) == 1


# ── Integration: full case from bug report ──────────────────────────────────

class TestAlvaroTorresCase:
    """The exact case from the bug report."""

    def test_full_case(self):
        result = calculate_quote({
            "client_name": "Alvaro Torres",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada tramo 1", "largo": 4.10, "prof": 0.65},
                {"description": "Mesada tramo 2", "largo": 2.80, "prof": 0.65},
                {"description": "Zócalo", "largo": 6.90, "alto": 0.05},
            ],
            "localidad": "puerto san martin",
            "colocacion": True,
            "anafe": True,
            "pileta": "empotrada_cliente",
            "plazo": "40 dias desde la toma de medidas",
        })

        assert result["ok"]

        # Total m²: 4.10×0.65 + 2.80×0.65 + 6.90×0.05 = 2.665 + 1.82 + 0.345 = 4.83
        assert abs(result["material_m2"] - 4.83) < 0.05

        # Zócalo label format
        labels = result["sectors"][0]["pieces"]
        zocalo_labels = [l for l in labels if "ZOC" in l]
        assert len(zocalo_labels) == 1
        assert "ML" in zocalo_labels[0]
        assert "ZOC" in zocalo_labels[0]
        assert "6.90" in zocalo_labels[0]
        assert "0.05" in zocalo_labels[0]
        assert "2 TRAMOS" not in zocalo_labels[0]

        # Mesada tramo 1 (4.10m) should have 2 TRAMOS
        tramo1 = [l for l in labels if "tramo 1" in l.lower()]
        assert len(tramo1) == 1
        assert "2 TRAMOS" in tramo1[0]

        # Flete for Puerto San Martín
        flete = [m for m in result["mo_items"] if "flete" in m["description"].lower()]
        assert len(flete) == 1
        assert "san martin" in flete[0]["description"].lower()

        # Pulido de cantos extra (colocación + distant zone)
        pulido = [m for m in result["mo_items"] if "pulido de cantos" in m["description"].lower()]
        assert len(pulido) == 1

        # Pileta present
        pileta = [m for m in result["mo_items"] if "pileta" in m["description"].lower()]
        assert len(pileta) == 1

        # Anafe present
        anafe = [m for m in result["mo_items"] if "anafe" in m["description"].lower()]
        assert len(anafe) == 1

        # Thickness in breakdown
        assert result["thickness_mm"] == 20

        # Delivery: 4.83 m² → 30 días tier (between 3 and 6)
        assert "40" in result["delivery_days"], f"Expected 40 dias (range_enabled=false), got: {result['delivery_days']}"

        # No warnings — Puerto San Martin is a valid zone
        assert "warnings" not in result or len(result.get("warnings", [])) == 0


# ── Residential: multiple anafes (gas + eléctrico) in one kitchen ───────────

class TestResidentialMultipleAnafes:
    """Caso Bernardi: cocina con 2 anafes empotrados (gas + eléctrico) en
    la misma mesada. Valentina debe pasar `anafe_qty=2` y el calculator
    debe agregar 1 línea "Agujero anafe" con quantity=2."""

    def test_anafe_qty_2_doubles_mo_quantity(self):
        result = calculate_quote({
            "client_name": "Érica Bernardi",
            "project": "Cocina",
            "material": "Puraprima Onix White",
            "pieces": [
                {"description": "Mesada lateral", "largo": 2.95, "prof": 0.60},
                {"description": "Mesada bajo",    "largo": 2.05, "prof": 0.60},
                {"description": "Isla",           "largo": 1.60, "prof": 0.60},
            ],
            "localidad": "rosario",
            "colocacion": True,
            "anafe": True,
            "anafe_qty": 2,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias desde la toma de medidas",
        })

        assert result["ok"]
        anafe_items = [m for m in result["mo_items"]
                       if "anafe" in m["description"].lower()]
        # Debe haber exactamente 1 línea de anafe con quantity=2 (no 2 líneas separadas)
        assert len(anafe_items) == 1, (
            f"Expected 1 anafe line with quantity=2, got {len(anafe_items)}: {anafe_items}"
        )
        assert anafe_items[0]["quantity"] == 2
        assert anafe_items[0]["total"] == round(anafe_items[0]["unit_price"] * 2)

    def test_anafe_qty_default_1_for_single_anafe(self):
        """Sin anafe_qty explícito → default 1 (no debe duplicarse)."""
        result = calculate_quote({
            "client_name": "Test",
            "project": "Cocina",
            "material": "Silestone Blanco Norte",
            "pieces": [{"description": "Mesada", "largo": 2.0, "prof": 0.60}],
            "localidad": "rosario",
            "colocacion": True,
            "anafe": True,
            "pileta": "empotrada_cliente",
            "plazo": "30 dias desde la toma de medidas",
        })
        anafe_items = [m for m in result["mo_items"]
                       if "anafe" in m["description"].lower()]
        assert len(anafe_items) == 1
        assert anafe_items[0]["quantity"] == 1


# ── Warnings visibility ─────────────────────────────────────────────────────

class TestFleteWarnings:
    def test_unknown_zone_produces_warning(self):
        """Unknown zone should produce a visible warning in the result."""
        result = calculate_quote(_base_input(localidad="atlantida"))
        assert result["ok"]
        assert "warnings" in result
        assert any("atlantida" in w.lower() for w in result["warnings"])
        # Should still have flete (Rosario fallback)
        flete = [m for m in result["mo_items"] if "flete" in m["description"].lower()]
        assert len(flete) == 1

    def test_valid_zone_no_warning(self):
        """Valid zone should NOT produce warnings."""
        result = calculate_quote(_base_input(localidad="Rosario"))
        assert result["ok"]
        assert result.get("warnings") is None or len(result.get("warnings", [])) == 0

    def test_skip_flete_no_warning(self):
        """skip_flete should not produce a warning about missing zone."""
        result = calculate_quote(_base_input(skip_flete=True))
        assert result["ok"]
        assert result.get("warnings") is None or len(result.get("warnings", [])) == 0


# ══════════════════════════════════════════════════════════════════
# Edificio fixes: merma + flete count + dims validation
# ══════════════════════════════════════════════════════════════════

class TestEdificioMerma:
    def test_edificio_never_applies_merma(self):
        """Edificios NEVER apply merma regardless of material."""
        result = calculate_quote(_base_input(
            is_edificio=True,
            pieces=[{"description": "DC-02 mesada", "largo": 3.0, "prof": 1.0, "quantity": 2}],
        ))
        assert result["ok"]
        assert result["merma"]["aplica"] is False
        assert "edificio" in result["merma"]["motivo"].lower()

    def test_residential_silestone_still_applies_merma(self):
        """Residential Silestone must still apply merma (no regression)."""
        result = calculate_quote(_base_input(
            pieces=[{"description": "Mesada", "largo": 2.0, "prof": 0.6}],
        ))
        assert result["ok"]
        # Silestone residential triggers merma logic (may or may not have sobrante)
        assert "motivo" in result["merma"]

    def test_calculate_merma_function_direct(self):
        """Direct test of calculate_merma with is_edificio flag.

        is_edificio=True short-circuits BEFORE any material classification:
        even if the material would normally merma (Silestone with big desperdicio),
        the edificio branch wins.
        """
        from app.modules.quote_engine.calculator import calculate_merma
        # Size that triggers merma for Silestone (desperdicio > 1.0)
        # Silestone uses media placa (2.10 m²). 1.3 m² → needs 1 media → desperdicio 0.80
        # Use 2.8 m² → needs 2 medias = 4.20 → desperdicio 1.40 > 1.0 → aplica
        result_edif = calculate_merma(2.8, "Silestone Blanco Norte", is_edificio=True)
        assert result_edif["aplica"] is False
        assert "edificio" in result_edif["motivo"].lower()
        result_res = calculate_merma(2.8, "Silestone Blanco Norte", is_edificio=False)
        assert result_res["aplica"] is True


class TestEdificioFleteCount:
    def test_flete_counts_quantity_not_descriptions(self):
        """DC-04 × 8 must count as 8 physical pieces, not 1."""
        # 25 total pieces (2+6+8+1+1+6+1) ÷ 6 per trip → 5 fletes
        result = calculate_quote(_base_input(
            is_edificio=True,
            pileta=None,
            pieces=[
                {"description": "DC-02 mesada", "largo": 3.0, "prof": 1.0, "quantity": 2},
                {"description": "DC-03 mesada", "largo": 2.96, "prof": 1.0, "quantity": 6},
                {"description": "DC-04 mesada", "largo": 2.87, "prof": 1.0, "quantity": 8},
                {"description": "DC-05 mesada", "largo": 1.17, "prof": 1.0, "quantity": 1},
                {"description": "DC-06 mesada", "largo": 1.12, "prof": 1.0, "quantity": 1},
                {"description": "DC-07 mesada", "largo": 2.60, "prof": 1.0, "quantity": 6},
                {"description": "DC-08 mesada", "largo": 1.79, "prof": 1.0, "quantity": 1},
            ],
        ))
        assert result["ok"]
        flete_item = next((m for m in result["mo_items"] if "flete" in m["description"].lower()), None)
        assert flete_item is not None, "flete mo_item missing"
        assert flete_item["quantity"] == 5, (
            f"25 pieces ÷ 6 per trip → ceil=5, got {flete_item['quantity']}"
        )

    def test_flete_excludes_zocalos(self):
        """Zócalos travel with mesadas, don't count as separate pieces for flete."""
        result = calculate_quote(_base_input(
            is_edificio=True,
            pileta=None,
            pieces=[
                {"description": "DC-02 mesada", "largo": 3.0, "prof": 1.0, "quantity": 2},
                {"description": "DC-02 zócalo", "largo": 4.85, "alto": 0.075, "quantity": 2},
            ],
        ))
        assert result["ok"]
        flete_item = next((m for m in result["mo_items"] if "flete" in m["description"].lower()), None)
        # 2 mesadas only → ceil(2/6) = 1
        assert flete_item["quantity"] == 1


class TestEdificioDimsValidation:
    def test_missing_dims_produces_warning(self):
        """Pieces without largo/prof in edificio must produce a warning."""
        result = calculate_quote(_base_input(
            is_edificio=True,
            pieces=[
                # Missing prof
                {"description": "DC-02 mesada", "largo": 3.0, "quantity": 2},
            ],
        ))
        assert result["ok"]
        warnings = result.get("warnings", [])
        assert any("largo y prof" in w.lower() or "dimensiones" in w.lower() for w in warnings), (
            f"Expected validation warning, got: {warnings}"
        )

    def test_complete_dims_no_warning(self):
        """Pieces with full largo + prof should not trigger this warning."""
        result = calculate_quote(_base_input(
            is_edificio=True,
            pieces=[
                {"description": "DC-02 mesada", "largo": 3.0, "prof": 1.0, "quantity": 2},
            ],
        ))
        assert result["ok"]
        warnings = result.get("warnings", [])
        assert not any("largo y prof" in w.lower() for w in warnings)
