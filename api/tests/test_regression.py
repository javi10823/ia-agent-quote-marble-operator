"""Regression tests — each bug fix gets a test that reproduces the exact scenario."""

from app.modules.quote_engine.calculator import calculate_quote, calculate_merma, calculate_m2


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


# ── BUG-045: Blanco Nube — m² inconsistente, anafe falso, rounding cascado ──

class TestBug045BlancoNubeM2Rounding:
    """BUG-045: Per-piece rounding caused 3.89 instead of 3.88."""

    def test_no_per_piece_rounding(self):
        """Pieces must NOT be rounded individually before summing."""
        pieces = [
            {"description": "Mesada principal", "largo": 3.00, "prof": 0.62},
            {"description": "Mesada secundaria", "largo": 1.16, "prof": 0.60},
            {"description": "Revestimiento pared", "largo": 0.99, "prof": 1.22},
            {"description": "Zócalo", "largo": 2.01, "alto": 0.06},
        ]
        m2, details = calculate_m2(pieces)
        # Raw: 1.86 + 0.696 + 1.2078 + 0.1206 = 3.8844 → round(2) = 3.88
        assert m2 == 3.88, f"Expected 3.88 but got {m2} — likely per-piece rounding"

    def test_total_is_sum_rounded_not_sum_of_rounded(self):
        """Verify round(sum) != sum(round) for this specific case."""
        pieces = [
            {"description": "Mesada principal", "largo": 3.00, "prof": 0.62},
            {"description": "Mesada secundaria", "largo": 1.16, "prof": 0.60},
            {"description": "Revestimiento pared", "largo": 0.99, "prof": 1.22},
            {"description": "Zócalo", "largo": 2.01, "alto": 0.06},
        ]
        m2, details = calculate_m2(pieces)
        # Sum of individually rounded (2 dec) = 1.86 + 0.70 + 1.21 + 0.12 = 3.89
        sum_of_rounded = sum(round(d["largo"] * d["dim2"], 2) for d in details)
        assert m2 != round(sum_of_rounded, 2), \
            "m2 should be round(raw_sum) not sum(round(each))"


class TestBug045AnafeSinEvidencia:
    """BUG-045: Agujero anafe was added without plan evidence."""

    def test_no_anafe_when_false(self):
        """ANAFE must not appear when anafe=False (no evidence)."""
        result = calculate_quote({
            "client_name": "Test Arquitectura",
            "material": "Blanco Nube",
            "pieces": [{"description": "Mesada cocina", "largo": 3.00, "prof": 0.62}],
            "localidad": "Rosario",
            "plazo": "30 días",
            "anafe": False,
        })
        assert result["ok"]
        mo_descs = [m["description"].lower() for m in result["mo_items"]]
        assert not any("anafe" in d for d in mo_descs), \
            f"ANAFE found without evidence: {mo_descs}"

    def test_anafe_when_true(self):
        """ANAFE must appear when anafe=True (evidence exists)."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Blanco Nube",
            "pieces": [{"description": "Mesada cocina", "largo": 3.00, "prof": 0.62}],
            "localidad": "Rosario",
            "plazo": "30 días",
            "anafe": True,
        })
        assert result["ok"]
        mo_descs = [m["description"].lower() for m in result["mo_items"]]
        assert any("anafe" in d for d in mo_descs), \
            f"ANAFE not found when anafe=True: {mo_descs}"


class TestBug045ColocacionMatchesMaterial:
    """BUG-045: Colocación qty must use same m² as material."""

    def test_colocacion_qty_equals_material_m2(self):
        result = calculate_quote({
            "client_name": "Test",
            "material": "Blanco Nube",
            "pieces": [
                {"description": "Mesada", "largo": 3.00, "prof": 0.62},
                {"description": "Mesada 2", "largo": 1.16, "prof": 0.60},
                {"description": "Rev pared", "largo": 0.99, "prof": 1.22},
                {"description": "Zócalo", "largo": 2.01, "alto": 0.06},
            ],
            "localidad": "Rosario",
            "colocacion": True,
            "plazo": "30 días",
        })
        assert result["ok"]
        coloc = next(m for m in result["mo_items"] if "colocación" in m["description"].lower())
        assert coloc["quantity"] == result["material_m2"], \
            f"Colocación qty {coloc['quantity']} ≠ material_m2 {result['material_m2']}"


class TestBug045IVATraceability:
    """BUG-045: Each MO item must include base_price for IVA traceability."""

    def test_mo_items_have_base_price(self):
        result = calculate_quote({
            "client_name": "Test",
            "material": "Blanco Nube",
            "pieces": [{"description": "Mesada", "largo": 2.00, "prof": 0.60}],
            "localidad": "Rosario",
            "plazo": "30 días",
        })
        assert result["ok"]
        for item in result["mo_items"]:
            assert "base_price" in item, \
                f"MO item '{item['description']}' missing base_price"
            if item["base_price"] > 0:
                expected_with_iva = round(item["base_price"] * 1.21)
                assert item["unit_price"] == expected_with_iva, \
                    f"'{item['description']}': unit_price {item['unit_price']} ≠ round({item['base_price']} × 1.21) = {expected_with_iva}"

    def test_piece_details_in_result(self):
        """calculate_quote must return piece_details for preview."""
        result = calculate_quote({
            "client_name": "Test",
            "material": "Blanco Nube",
            "pieces": [
                {"description": "Mesada", "largo": 3.00, "prof": 0.62},
                {"description": "Zócalo", "largo": 3.00, "alto": 0.05},
            ],
            "localidad": "Rosario",
            "plazo": "30 días",
        })
        assert result["ok"]
        assert "piece_details" in result
        assert len(result["piece_details"]) == 2
        assert result["piece_details"][0]["description"] == "Mesada"
