"""Regression tests — each bug fix gets a test that reproduces the exact scenario."""

from app.modules.quote_engine.calculator import calculate_quote, calculate_merma


# ── BUG-043: Plano Marmoleria — zócalo omitido + revestimiento sin TOMAS ─────

class TestBug043ZocaloOmitido:
    """BUG-043: Zócalo de 2,01 × 0,06 fue omitido del presupuesto."""

    def test_small_zocalo_included_in_m2(self):
        """A piece of 2.01 × 0.06 must be included in total m² as a zócalo."""
        result = calculate_quote({
            "client_name": "Basa Arquitectura",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada principal", "largo": 3.00, "prof": 0.62},
                {"description": "Mesada secundaria", "largo": 1.16, "prof": 0.60},
                {"description": "Zócalo", "largo": 2.01, "alto": 0.06},
            ],
            "localidad": "Rosario",
            "plazo": "30 días",
        })
        assert result["ok"] is True
        # Total m² must include the zócalo: 1.86 + 0.696 + 0.1206 ≈ 2.677
        assert result["material_m2"] > 2.6, f"m² too low ({result['material_m2']}), zócalo probably omitted"


class TestBug043RevestimientoTomas:
    """BUG-043: Revestimiento de pared must auto-add TOMAS."""

    def test_revestimiento_pared_adds_tomas(self):
        """If any piece has 'revestimiento' in description, add TOMAS."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada", "largo": 3.00, "prof": 0.62},
                {"description": "Revestimiento pared", "largo": 0.99, "prof": 1.16},
            ],
            "localidad": "Rosario",
            "plazo": "30 días",
        })
        assert result["ok"] is True
        mo_descs = [m["description"].lower() for m in result["mo_items"]]
        assert any("toma corriente" in d for d in mo_descs), \
            f"TOMAS not found for revestimiento pared. MO items: {mo_descs}"

    def test_no_revestimiento_no_tomas_from_this_rule(self):
        """Without revestimiento and without tall zócalo, no TOMAS added."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada", "largo": 2.00, "prof": 0.60},
                {"description": "Zócalo", "largo": 2.00, "alto": 0.05},
            ],
            "localidad": "Rosario",
            "plazo": "30 días",
        })
        assert result["ok"] is True
        mo_descs = [m["description"].lower() for m in result["mo_items"]]
        assert not any("toma corriente" in d for d in mo_descs), \
            f"TOMAS should NOT be present without revestimiento or tall zócalo"


# ── BUG-042: Zócalo > 10cm debe agregar TOMAS ───────────────────────────────

class TestBug042TallZocaloTomas:
    """BUG-042: Zócalo > 10cm was not adding TOMAS."""

    def test_zocalo_15cm_adds_tomas(self):
        result = calculate_quote({
            "client_name": "Test",
            "material": "Silestone Blanco Norte",
            "pieces": [
                {"description": "Mesada", "largo": 2.00, "prof": 0.60},
                {"description": "Zócalo", "largo": 2.00, "alto": 0.15},
            ],
            "localidad": "Rosario",
            "plazo": "30 días",
        })
        mo_descs = [m["description"].lower() for m in result["mo_items"]]
        assert any("toma corriente" in d for d in mo_descs)


# ── BUG-044: Statuarietto — m2 incorrecto sin zócalo, total USD no coincide ──

class TestBug044StatuariettoM2:
    """BUG-044: Valentina calculó 3.88 m² omitiendo zócalo. Real: 4.00 m²."""

    def test_plano_marmoleria_zocalo_included_in_total(self):
        """Zócalo 2.01×0.06 must be included — total must be higher than without it."""
        pieces_without_zocalo = [
            {"description": "Mesada principal", "largo": 3.00, "prof": 0.62},
            {"description": "Mesada pequeña", "largo": 1.16, "prof": 0.60},
            {"description": "Revestimiento pared", "largo": 0.99, "prof": 1.16},
        ]
        pieces_with_zocalo = pieces_without_zocalo + [
            {"description": "Zócalo", "largo": 2.01, "alto": 0.06},
        ]

        r_without = calculate_quote({
            "client_name": "Test", "material": "Blanco Nube",
            "pieces": pieces_without_zocalo, "localidad": "Rosario", "plazo": "30 días",
        })
        r_with = calculate_quote({
            "client_name": "Test", "material": "Blanco Nube",
            "pieces": pieces_with_zocalo, "localidad": "Rosario", "plazo": "30 días",
        })
        assert r_with["ok"] and r_without["ok"]
        # With zócalo must have more m² and higher total
        assert r_with["material_m2"] > r_without["material_m2"], "Zócalo not adding m²"
        assert r_with["material_total"] > r_without["material_total"], "Zócalo not adding to total"

    def test_total_usd_matches_m2_times_price(self):
        """Total USD must equal round(m2 × price_unit). No invented adjustments."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Blanco Nube",
            "pieces": [
                {"description": "Mesada", "largo": 3.00, "prof": 0.62},
                {"description": "Mesada 2", "largo": 1.16, "prof": 0.60},
                {"description": "Revestimiento pared", "largo": 0.99, "prof": 1.16},
                {"description": "Zócalo", "largo": 2.01, "alto": 0.06},
            ],
            "localidad": "Rosario",
            "plazo": "30 días",
        })
        assert result["ok"] is True
        expected_total = round(result["material_m2"] * result["material_price_unit"])
        assert result["material_total"] == expected_total, \
            f"Total {result['material_total']} ≠ round({result['material_m2']} × {result['material_price_unit']}) = {expected_total}"


# ── BUG-038: Negro Brasil nunca lleva merma ──────────────────────────────────

class TestBug038NegroBrasilMerma:
    """BUG-038: Negro Brasil was charging merma."""

    def test_negro_brasil_never_merma(self):
        merma = calculate_merma(2.0, "GRANITO NEGRO BRASIL")
        assert merma["aplica"] is False
        assert "Negro Brasil" in merma["motivo"]
