"""Tests for deterministic edificio PDF parser."""
import math
import pytest
from app.modules.quote_engine.edificio_parser import (
    detect_edificio,
    parse_edificio_tables,
    normalize_edificio_data,
    compute_edificio_aggregates,
    validate_edificio,
)

# ── Test fixtures (ESH-like but no hardcodes) ────────────────────────────────

MARMOLERIA_TABLE = [
    ["MARMOLERÍA", None, None, None, None, None, None, None, None, None, None],
    ["ID / Pieza", None, "Ubicación", "Largo (m)", "Ancho (m)", "Superficie (m2)", "Espesor (cm)", "Tipo de material", "Terminación", "Perforaciones / Calados", "Aclaraciones"],
    ["M1", None, "13- Lavatorios", "2,3", "0,6", "1,38", "2", "Negro Boreal", "Lustrado", "3 Bachas y 3 griferías monocomandos", "Faldón de 10cm"],
    ["M2", None, "14- Kitchenette", "2,15", "0,6", "1,29", "2", "Negro Boreal", "Lustrado", "1 pileta y 1 grifería monocomando", "Faldón 5cm"],
    ["M3", None, "Ingreso Kitchenette", "1,3", "0,6", "0,78", "2", "Negro Boreal", "Lustrado", "-", "Faldón 5cm"],
    ["M5", None, "33- Baño caballeros", "1,66", "0,5", "0,83", "2", "Negro Boreal", "Lustrado", "2 bachas y 2 griferías monocomando", "Faldón de 10cm"],
    ["M6", None, "34- Baño damas", "1,66", "0,5", "0,83", "2", "Negro Boreal", "Lustrado", "2 bachas y 2 griferías monocomando", "Faldón de 10cm"],
    ["M7", None, "70- Baño damas", "2,1", "0,5", "1,05", "2", "Negro Boreal", "Lustrado", "2 bachas y 2 griferías monocomando", "Faldón de 10cm"],
    ["M8", None, "74- Baño caballeros", "2,5", "0,5", "1,25", "2", "Negro Boreal", "Lustrado", "2 bachas y 2 griferías monocomando", "Faldón de 10cm"],
    ["M9", None, "50- Kitchenette", "2,8", "0,6", "1,68", "2", "Negro Brasil", "Lustrado", "1 pileta y 1 grifería monocomando", None],
    ["M10", None, "52- Baño", "1,2", "0,5", "0,6", "2", "Negro Brasil", "Lustrado", "1 lavatorio de apoyar y 1 grifería monocomando", "Faldón de 15cm"],
    ["M11", None, "65- Cocina", "1,94", "0,6", "1,164", "2", "Negro Boreal", "Lustrado", "2 piletas y 2 griferías monocomando", "-"],
    ["M12", None, None, "3", "0,6", "1,8", "2", "Negro Brasil", "Lustrado", "-", None],
    ["M13", None, None, "3", "0,95", "2,85", "2", "Negro Boreal", "Lustrado", "-", None],
]

UMBRALES_TABLE = [
    ["UMBRALES", None, None, None, None, None, None, None, None, None, None, None],
    ["ID / Pieza", "Ubicación", None, "Largo (m)", "Ancho (m)", "Superficie (m2)", "Espesor (cm)", "Tipo de material", "Terminación", None, "Aclaraciones", None],
    ["U-01", None, "9- Repuestos", "2", "0,2", "0,4", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-02", None, "9- Repuestos", "2", "0,2", "0,4", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-03", None, "Calderas - Baño Externo", "0,85", "0,17", "0,1445", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-04", None, "1- Salón Principal Ingreso (Int)", "3", "0,3", "0,9", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-05", None, "1- Salón Principal Ingreso (Ext)", "4,3", "1,5", "6,45", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-06", None, "8- Entrega 0km y Usados", "9", "0,41", "3,69", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-07", None, "11- Atención Servicios", "8,41", "0,2", "1,682", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-08", None, "Garita control entrada/salida", "0,95", "0,28", "0,266", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-09", None, "Garita recepción", "0,95", "0,28", "0,266", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-10", None, "41- Gestoría y Requerimientos", "12,9", "0,2", "2,58", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-11", None, "44- Recepción y Espera admin.", "12,3", "0,2", "2,46", "3", "Granito new beige", "Pulido", None, None, None],
    ["U-12", None, "47- Comedor Personal", "14,75", "0,2", "2,95", "3", "Granito new beige", "Pulido", None, None, None],
]

ALFEIZARES_TABLE = [
    ["ALFEIZARES", None, None, None, None, None, None, None, None, None, None, None],
    ["ID / Pieza", "Ubicación", None, "Largo (m)", "Ancho (m)", "Superficie (m2)", "Espesor (cm)", "Tipo de material", "Terminación", None, "Aclaraciones", None],
    ["A-03", None, "8- Entrega 0km y usados", "6,4", "0,26", "1,664", "3", "Granito new beige", "Pulido", None, None, None],
    ["A-04", None, "8- Entrega 0km y usados", "7,44", "0,41", "3,0504", "3", "Granito new beige", "Pulido", None, None, None],
]

ESCALONES_TABLE = [
    ["ESCALONES", None, None, None, None, None, None, None, None, None, None],
    ["ID / Pieza", "Ubicación", "Largo (m)", "Ancho (m)", "Superficie (m2)", "Cantidad", "Superficie total (m2)", "Espesor (cm)", "Tipo de material", "Terminación", "Aclaraciones"],
    ["E-01", "39 - Salón Principal", "1,2", "0,4", "0,35", "19", "6,65", "3", "Granito new beige", "Pulido", None],
    ["E-02", "39 - Salón Principal", "1,2", "0,25", "0,3", "4", "1,2", "3", "Granito new beige", "Pulido", None],
]

ALL_TABLES = [MARMOLERIA_TABLE, UMBRALES_TABLE, ALFEIZARES_TABLE, ESCALONES_TABLE]


def _get_full_pipeline():
    raw = parse_edificio_tables(ALL_TABLES)
    normalized = normalize_edificio_data(raw)
    summary = compute_edificio_aggregates(normalized)
    return raw, normalized, summary


# ── detect_edificio tests ────────────────────────────────────────────────────

class TestDetectEdificio:
    def test_operador_dice_edificio(self):
        result = detect_edificio("Es un edificio, cliente ESH", [])
        assert result["is_edificio"] is True
        assert result["confidence"] >= 0.5
        assert any("operador" in r for r in result["reasons"])

    def test_tabla_con_umbrales(self):
        result = detect_edificio("", ALL_TABLES)
        assert result["is_edificio"] is True
        assert any("UMBRALES" in r.upper() for r in result["reasons"])

    def test_falso_positivo_una_señal_debil(self):
        """Only >15 rows (weak signal) should NOT trigger edificio."""
        big_table = [["row"] * 5 for _ in range(20)]
        result = detect_edificio("", [big_table])
        assert result["is_edificio"] is False

    def test_combinacion_señales(self):
        """Multiple materials + many rows should trigger."""
        table = [
            ["header", "material"],
            ["1", "Negro Boreal"],
            ["2", "Negro Brasil"],
            ["3", "Mármol Sahara"],
        ] + [["x", "Negro Boreal"] for _ in range(15)]
        result = detect_edificio("", [table])
        assert result["is_edificio"] is True

    def test_presupuesto_simple(self):
        simple_table = [
            ["ID", "Largo", "Ancho"],
            ["P1", "2.0", "0.6"],
        ]
        result = detect_edificio("mesada cocina silestone", [simple_table])
        assert result["is_edificio"] is False


# ── parse_edificio_tables tests ──────────────────────────────────────────────

class TestParseEdificioTables:
    def test_parse_preserves_raw_data(self):
        raw = parse_edificio_tables(ALL_TABLES)
        assert len(raw["sections"]) >= 1
        first_row = raw["sections"][0]["rows"][0]
        assert first_row["id"] == "M1"
        assert first_row["largo_raw"] == "2,3"
        assert first_row["perforaciones_raw"] is not None

    def test_m12_no_ubicacion(self):
        """M12 has None in ubicacion column."""
        raw = parse_edificio_tables(ALL_TABLES)
        m12 = next(r for s in raw["sections"] for r in s["rows"] if r["id"] == "M12")
        assert m12["ubicacion"] is None

    def test_m11_has_ubicacion(self):
        """M11 has '65- Cocina' in ubicacion column."""
        raw = parse_edificio_tables(ALL_TABLES)
        m11 = next(r for s in raw["sections"] for r in s["rows"] if r["id"] == "M11")
        assert m11["ubicacion"] == "65- Cocina"

    def test_m13_no_ubicacion(self):
        """M13 has no ubicacion in PDF — confirmed from rendered PDF."""
        raw = parse_edificio_tables(ALL_TABLES)
        m13 = next(r for s in raw["sections"] for r in s["rows"] if r["id"] == "M13")
        assert m13["ubicacion"] is None

    def test_m13_no_perforaciones(self):
        """M13 has '-' in perforaciones → null."""
        raw = parse_edificio_tables(ALL_TABLES)
        m13 = next(r for s in raw["sections"] for r in s["rows"] if r["id"] == "M13")
        assert m13["perforaciones_raw"] is None

    def test_m11_m12_m13_alignment(self):
        """Critical alignment test — verified against rendered PDF.
        M11 = 65-Cocina, 2 piletas, no faldón
        M12 = no ubicacion, no perforaciones, no faldón
        M13 = no ubicacion, no perforaciones, no faldón
        """
        raw = parse_edificio_tables(ALL_TABLES)
        rows = {r["id"]: r for s in raw["sections"] for r in s["rows"]}
        # M11: has ubicacion + perforaciones
        assert rows["M11"]["ubicacion"] == "65- Cocina"
        assert rows["M11"]["perforaciones_raw"] is not None
        assert "2 piletas" in rows["M11"]["perforaciones_raw"]
        # M12: no ubicacion, no perforaciones
        assert rows["M12"]["ubicacion"] is None
        assert rows["M12"]["perforaciones_raw"] is None
        # M13: no ubicacion, no perforaciones
        assert rows["M13"]["ubicacion"] is None
        assert rows["M13"]["perforaciones_raw"] is None

    def test_m12_perforaciones_dash(self):
        raw = parse_edificio_tables(ALL_TABLES)
        m12 = next(r for s in raw["sections"] for r in s["rows"] if r["id"] == "M12")
        assert m12["perforaciones_raw"] is None

    def test_m3_perforaciones_dash(self):
        raw = parse_edificio_tables(ALL_TABLES)
        m3 = next(r for s in raw["sections"] for r in s["rows"] if r["id"] == "M3")
        assert m3["perforaciones_raw"] is None


# ── normalize_edificio_data tests ────────────────────────────────────────────

class TestNormalizeEdificioData:
    def test_perforaciones_3_bachas(self):
        raw = parse_edificio_tables(ALL_TABLES)
        norm = normalize_edificio_data(raw)
        m1 = next(p for s in norm["sections"] for p in s["pieces"] if p["id"] == "M1")
        assert m1["pileta_count"] == 3
        assert m1["pileta_type"] == "empotrada"

    def test_perforaciones_1_lavatorio_apoyo(self):
        raw = parse_edificio_tables(ALL_TABLES)
        norm = normalize_edificio_data(raw)
        m10 = next(p for s in norm["sections"] for p in s["pieces"] if p["id"] == "M10")
        assert m10["pileta_count"] == 1
        assert m10["pileta_type"] == "apoyo"

    def test_perforaciones_2_piletas(self):
        raw = parse_edificio_tables(ALL_TABLES)
        norm = normalize_edificio_data(raw)
        m11 = next(p for s in norm["sections"] for p in s["pieces"] if p["id"] == "M11")
        assert m11["pileta_count"] == 2
        assert m11["pileta_type"] == "empotrada"

    def test_perforaciones_dash_is_zero(self):
        raw = parse_edificio_tables(ALL_TABLES)
        norm = normalize_edificio_data(raw)
        m12 = next(p for s in norm["sections"] for p in s["pieces"] if p["id"] == "M12")
        assert m12["pileta_count"] == 0
        assert m12["pileta_type"] is None

    def test_aclaraciones_faldon_10cm(self):
        raw = parse_edificio_tables(ALL_TABLES)
        norm = normalize_edificio_data(raw)
        m1 = next(p for s in norm["sections"] for p in s["pieces"] if p["id"] == "M1")
        assert m1["faldon_cm"] == 10
        assert m1["faldon_ml_unit"] == 2.3

    def test_aclaraciones_faldon_5cm(self):
        raw = parse_edificio_tables(ALL_TABLES)
        norm = normalize_edificio_data(raw)
        m2 = next(p for s in norm["sections"] for p in s["pieces"] if p["id"] == "M2")
        assert m2["faldon_cm"] == 5

    def test_aclaraciones_dash_is_null(self):
        raw = parse_edificio_tables(ALL_TABLES)
        norm = normalize_edificio_data(raw)
        m11 = next(p for s in norm["sections"] for p in s["pieces"] if p["id"] == "M11")
        assert m11["faldon_cm"] is None
        assert m11["faldon_ml_unit"] is None

    def test_cantidad_multiplied_in_m2(self):
        raw = parse_edificio_tables(ALL_TABLES)
        norm = normalize_edificio_data(raw)
        e01 = next(p for s in norm["sections"] for p in s["pieces"] if p["id"] == "E-01")
        assert e01["cantidad"] == 19
        assert e01["m2_calc_unit"] == pytest.approx(0.48, abs=0.001)
        assert e01["m2_calc_total"] == pytest.approx(0.48 * 19, abs=0.01)

    def test_perforaciones_variante_bacha_singular(self):
        """'1 bacha' should parse as 1."""
        raw = parse_edificio_tables([[
            ["ID", "Perforaciones / Calados", "Largo (m)", "Ancho (m)"],
            ["T1", "1 bacha", "1", "0,5"],
        ]])
        norm = normalize_edificio_data(raw)
        assert norm["sections"][0]["pieces"][0]["pileta_count"] == 1

    def test_perforaciones_lavatorio_sin_apoyo(self):
        """'1 lavatorio' without 'apoyo' should be empotrada."""
        raw = parse_edificio_tables([[
            ["ID", "Perforaciones / Calados", "Largo (m)", "Ancho (m)"],
            ["T1", "1 lavatorio y 1 grifería", "1", "0,5"],
        ]])
        norm = normalize_edificio_data(raw)
        assert norm["sections"][0]["pieces"][0]["pileta_type"] == "empotrada"

    def test_aclaraciones_variante_sin_de(self):
        """'Faldón 15cm' without 'de' should parse."""
        raw = parse_edificio_tables([[
            ["ID", "Aclaraciones", "Largo (m)", "Ancho (m)"],
            ["T1", "Faldón 15cm", "2", "0,5"],
        ]])
        norm = normalize_edificio_data(raw)
        assert norm["sections"][0]["pieces"][0]["faldon_cm"] == 15


# ── compute_edificio_aggregates tests ────────────────────────────────────────

class TestComputeEdificioAggregates:
    def test_pegadopileta_boreal(self):
        _, norm, summary = _get_full_pipeline()
        boreal = summary["materials"].get("Negro Boreal", {})
        # M1=3, M2=1, M5=2, M6=2, M7=2, M8=2, M11=2 = 14
        assert boreal["pileta_pegado"] == 14

    def test_pegadopileta_total(self):
        _, _, summary = _get_full_pipeline()
        # Boreal 14 + Brasil 1 (M9) = 15
        assert summary["totals"]["pileta_pegado_total"] == 15

    def test_agujeroapoyo(self):
        _, _, summary = _get_full_pipeline()
        assert summary["totals"]["pileta_apoyo_total"] == 1

    def test_faldon_ml_boreal(self):
        _, _, summary = _get_full_pipeline()
        boreal = summary["materials"].get("Negro Boreal", {})
        # M1=2.3, M2=2.15, M3=1.3, M5=1.66, M6=1.66, M7=2.1, M8=2.5
        expected = 2.3 + 2.15 + 1.3 + 1.66 + 1.66 + 2.1 + 2.5
        assert abs(boreal["faldon_ml_total"] - expected) < 0.01

    def test_flete(self):
        _, _, summary = _get_full_pipeline()
        physical = summary["totals"]["pieces_physical_total"]
        assert summary["totals"]["flete_qty"] == math.ceil(physical / 8)

    def test_escalones_quantity(self):
        _, norm, summary = _get_full_pipeline()
        beige = summary["materials"].get("Marmol Sahara", {})
        # E-01: 19 + E-02: 4 = 23 escalones in physical count
        assert beige["piece_count_physical"] >= 23

    def test_descuento_all_materials(self):
        _, _, summary = _get_full_pipeline()
        assert summary["totals"]["descuento_18_aplica"] is True
        assert summary["totals"]["m2_total"] > 15

    def test_m2_validation_by_components(self):
        _, _, summary = _get_full_pipeline()
        for mat, ms in summary["materials"].items():
            expected = round(ms["m2_mesadas"] + ms["m2_faldones"], 2)
            assert abs(ms["m2_total"] - expected) < 0.05, f"{mat}: {ms['m2_total']} != {expected}"

    def test_piece_count_physical_multiplies_cantidad(self):
        """Escalones with qty=19 should count 19 physical pieces, not 1 row."""
        _, _, summary = _get_full_pipeline()
        beige = summary["materials"].get("Marmol Sahara", {})
        # At minimum: 12 umbrales + 2 alfeizares + 19 + 4 escalones = 37
        assert beige["piece_count_physical"] >= 37


# ── validate_edificio tests ──────────────────────────────────────────────────

class TestValidateEdificio:
    def test_valid_data_no_errors(self):
        _, norm, summary = _get_full_pipeline()
        result = validate_edificio(norm, summary)
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    def test_reject_invented_piletas(self):
        """Piece with perforaciones=null but pileta_count>0 must error."""
        raw = parse_edificio_tables([[
            ["ID", "Perforaciones / Calados", "Largo (m)", "Ancho (m)"],
            ["T1", "-", "1", "0,5"],
        ]])
        norm = normalize_edificio_data(raw)
        # Manually inject invalid pileta
        norm["sections"][0]["pieces"][0]["pileta_count"] = 2
        norm["sections"][0]["pieces"][0]["pileta_type"] = "empotrada"
        summary = compute_edificio_aggregates(norm)
        result = validate_edificio(norm, summary)
        assert result["is_valid"] is False
        assert any("pileta_count" in e for e in result["errors"])

    def test_reject_invented_faldones(self):
        """Piece with aclaraciones=null but faldon_cm set must error."""
        raw = parse_edificio_tables([[
            ["ID", "Aclaraciones", "Largo (m)", "Ancho (m)"],
            ["T1", "-", "1", "0,5"],
        ]])
        norm = normalize_edificio_data(raw)
        norm["sections"][0]["pieces"][0]["faldon_cm"] = 10
        summary = compute_edificio_aggregates(norm)
        result = validate_edificio(norm, summary)
        assert result["is_valid"] is False

    def test_reject_duplicate_ids(self):
        raw = parse_edificio_tables([[
            ["ID", "Largo (m)", "Ancho (m)"],
            ["X1", "1", "0,5"],
            ["X1", "2", "0,6"],
        ]])
        norm = normalize_edificio_data(raw)
        summary = compute_edificio_aggregates(norm)
        result = validate_edificio(norm, summary)
        assert result["is_valid"] is False
        assert any("duplicado" in e.lower() or "duplic" in e.lower() for e in result["errors"])

    def test_warn_m2_pdf_vs_calc(self):
        """m2_pdf != m2_calc should produce warning."""
        _, norm, summary = _get_full_pipeline()
        result = validate_edificio(norm, summary)
        # E-01 has m2_pdf=0.35 but m2_calc=0.48 → should warn
        e01_warnings = [w for w in result["warnings"] if "E-01" in w and "m2" in w.lower()]
        assert len(e01_warnings) > 0

    def test_warn_no_ubicacion(self):
        _, norm, summary = _get_full_pipeline()
        result = validate_edificio(norm, summary)
        # M12 and M13 have no ubicacion → warnings
        no_ubi = [w for w in result["warnings"] if "ubicación" in w.lower() or "ubicacion" in w.lower()]
        assert len(no_ubi) >= 2
