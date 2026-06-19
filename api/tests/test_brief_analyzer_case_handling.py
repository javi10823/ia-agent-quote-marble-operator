"""Sub-PR sprint-4/brief-analyzer-deuda-cleanup.

Cubre 2 colaterales reales destapados en FASE 1.5:
1. `_CLIENT_RE` era case-sensitive · "Cliente" (mayúscula) no matcheaba la
   ancla. Fix: inline `(?i:cliente)` + stop-words post-processing
   (`_clean_client_match`) que trunca "Tel"/"Email" cuando entran al captura.
2. `products_only_detector._CLIENT_RE` con field-label lookahead que no
   listaba tel/cel/email/mail · el captura arrastraba contacto. Fix: agregar
   esas palabras al lookahead.

Variantes B/C (brief sin ancla "cliente:" / "Cliente:") quedan documentadas
como comportamiento aceptable: `client_name = None`, phone/email extraídos
limpio cuando tienen ancla propia. Si Marina reporta frustración real,
sub-PR follow-up con extracción sin ancla.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-fake")
os.environ.setdefault("SECRET_KEY", "test-secret-min-16chars")
os.environ.setdefault("GOOGLE_DRIVE_FOLDER_ID", "test")
os.environ.setdefault("APP_ENV", "test")

import pytest

from app.modules.quote_engine.brief_analyzer import (
    _analyze_regex_fallback,
    _clean_client_match,
)
from app.modules.quote_engine.products_only_detector import _extract_client_project


# ═══════════════════════════════════════════════════════
# _clean_client_match helper · stop-words truncation
# ═══════════════════════════════════════════════════════


class TestCleanClientMatch:
    @pytest.mark.parametrize("raw,expected", [
        ("Juan Pérez Tel", "Juan Pérez"),
        ("Juan Pérez Email", "Juan Pérez"),
        ("Juan Pérez en Rosario", "Juan Pérez"),
        ("Juan Pérez de la Cruz", "Juan Pérez"),
        ("Juan Pérez con descuento", "Juan Pérez"),
        ("Juan Pérez WhatsApp", "Juan Pérez"),
        ("Juan Pérez", "Juan Pérez"),
        ("Erica Bernardi", "Erica Bernardi"),
        ("Juan Pérez Tel:", "Juan Pérez"),
        ("Juan Pérez Email,", "Juan Pérez"),
    ])
    def test_truncates_at_stop_word(self, raw, expected):
        assert _clean_client_match(raw) == expected

    def test_empty_input(self):
        assert _clean_client_match("") == ""

    def test_only_whitespace(self):
        assert _clean_client_match("   ") == ""


# ═══════════════════════════════════════════════════════
# _analyze_regex_fallback · Colateral 1
# ═══════════════════════════════════════════════════════


class TestClientNameExtractionWithAncla:
    """Variantes con ancla 'cliente' (cualquier case) extraen limpio."""

    @pytest.mark.parametrize("brief,expected,variant", [
        (
            "Cliente Juan Pérez Tel: 3415551234 Email: juan@gmail.com",
            "Juan Pérez",
            "A_mayuscula_con_tel_email",
        ),
        (
            "cliente Juan Pérez en Rosario",
            "Juan Pérez",
            "D_minuscula_preposicion",
        ),
        (
            "Cliente: Juan Pérez en Rosario",
            "Juan Pérez",
            "E_synthetic_brief_format",
        ),
        (
            "cliente Juan Pérez Email: juan@gmail.com",
            "Juan Pérez",
            "F_email_pegado",
        ),
        (
            "material silestone cliente Erica Bernardi SIN zocalos en rosario",
            "Erica Bernardi",
            "G_baseline_existente",
        ),
    ])
    def test_extracts_clean_name(self, brief, expected, variant):
        result = _analyze_regex_fallback(brief)
        assert result["client_name"] == expected, (
            f"[{variant}] esperaba '{expected}', extrajo {result['client_name']!r}"
        )

    @pytest.mark.parametrize("brief,variant", [
        ("Cliente Juan Pérez Tel: 3415551234", "A_mayuscula"),
        ("cliente Juan Pérez en Rosario", "D_minuscula"),
        ("Cliente: Juan Pérez Email: juan@gmail.com", "E_format"),
    ])
    def test_no_contamination_tel_email(self, brief, variant):
        result = _analyze_regex_fallback(brief)
        name = result["client_name"] or ""
        assert "Tel" not in name, f"[{variant}] 'Tel' contaminó client_name: {name!r}"
        assert "Email" not in name, f"[{variant}] 'Email' contaminó client_name: {name!r}"
        assert "@" not in name, f"[{variant}] '@' contaminó client_name: {name!r}"


class TestClientNameExtractionWithoutAncla:
    """Variantes sin ancla 'cliente' · documenta comportamiento actual:
    client_name=None, phone/email se extraen si tienen ancla propia.

    Forward: si Marina reporta frustración, sub-PR follow-up con extracción
    sin ancla."""

    @pytest.mark.parametrize("brief,variant", [
        ("Juan Pérez Tel: 3415551234 Email: juan@gmail.com en Rosario", "B_sin_ancla"),
        ("Juan Pérez 3415551234 juan.perez@gmail.com Rosario", "C_whatsapp_pegado"),
    ])
    def test_no_extraction_documented(self, brief, variant):
        result = _analyze_regex_fallback(brief)
        assert result["client_name"] is None, (
            f"[{variant}] client_name debería ser None sin ancla, got {result['client_name']!r}"
        )

    def test_phone_with_ancla_still_extracted(self):
        result = _analyze_regex_fallback("Juan Pérez Tel: 3415551234 en Rosario")
        assert result["phone"] == "3415551234"

    def test_email_always_extracted(self):
        result = _analyze_regex_fallback("Juan Pérez juan.perez@gmail.com Rosario")
        assert result["email"] == "juan.perez@gmail.com"


# ═══════════════════════════════════════════════════════
# products_only_detector._extract_client_project · Colateral 1 hermano
# ═══════════════════════════════════════════════════════


class TestProductsOnlyClientExtraction:
    """`_extract_client_project` tiene su propio `_CLIENT_RE` con
    field-label lookahead · el fix agrega tel/cel/email/mail al stop list."""

    def test_truncates_at_tel_label(self):
        client, _ = _extract_client_project(
            "cliente: Juan Pérez tel: 3415551234 obra: cocina"
        )
        assert client == "Juan Pérez"

    def test_truncates_at_email_label(self):
        client, _ = _extract_client_project(
            "cliente: Juan Pérez email: juan@gmail.com"
        )
        assert client == "Juan Pérez"

    def test_truncates_at_uppercase_Tel(self):
        client, _ = _extract_client_project(
            "cliente: Juan Pérez Tel: 3415551234 Email: juan@gmail.com"
        )
        assert client == "Juan Pérez"

    def test_baseline_clean_brief_works(self):
        client, project = _extract_client_project(
            "cliente: Erica Bernardi obra: cocina"
        )
        assert client == "Erica Bernardi"
        assert project == "cocina"


# ═══════════════════════════════════════════════════════
# Colateral 2 · _phone_email_from_breakdown helper + wire en GET /quotes
# ═══════════════════════════════════════════════════════


from app.modules.agent.router import _phone_email_from_breakdown


class TestPhoneEmailFromBreakdown:
    def test_returns_pair_of_none_when_empty(self):
        assert _phone_email_from_breakdown(None) == (None, None)
        assert _phone_email_from_breakdown({}) == (None, None)

    def test_extracts_from_top_level_brief_analysis_raw(self):
        bd = {"_brief_analysis_raw": {"phone": "3464696027", "email": "x@y.com"}}
        assert _phone_email_from_breakdown(bd) == ("3464696027", "x@y.com")

    def test_extracts_from_verified_context_analysis(self):
        bd = {
            "verified_context_analysis": {
                "_brief_analysis_raw": {"phone": "3464696027", "email": "x@y.com"}
            }
        }
        assert _phone_email_from_breakdown(bd) == ("3464696027", "x@y.com")

    def test_precedence_verified_over_pending(self):
        bd = {
            "verified_context_analysis": {
                "_brief_analysis_raw": {"phone": "VERIFIED_PHONE", "email": "verified@y.com"}
            },
            "context_analysis_pending": {
                "_brief_analysis_raw": {"phone": "PENDING_PHONE", "email": "pending@y.com"}
            },
        }
        assert _phone_email_from_breakdown(bd) == ("VERIFIED_PHONE", "verified@y.com")

    def test_falls_through_pending_when_verified_missing(self):
        bd = {
            "context_analysis_pending": {
                "_brief_analysis_raw": {"phone": "3464696027", "email": "x@y.com"}
            }
        }
        assert _phone_email_from_breakdown(bd) == ("3464696027", "x@y.com")

    def test_phone_only_email_none(self):
        bd = {"_brief_analysis_raw": {"phone": "3464696027"}}
        assert _phone_email_from_breakdown(bd) == ("3464696027", None)

    def test_empty_strings_become_none(self):
        bd = {"_brief_analysis_raw": {"phone": "", "email": ""}}
        assert _phone_email_from_breakdown(bd) == (None, None)


# ═══════════════════════════════════════════════════════
# Roundtrip synthetic_brief → brief_analyzer · smoke
# ═══════════════════════════════════════════════════════


class TestSyntheticBriefRoundtrip:
    """`build_brief_from_quote_columns` construye con `Cliente: <name>` mayúscula.
    Antes del fix `_CLIENT_RE` case-sensitive lo rechazaba silenciosamente.
    """

    def test_construct_and_reparse_clean(self):
        from app.modules.agent.synthetic_brief import build_brief_from_quote_columns

        class FakeQuote:
            client_name = "Erica Bernardi"
            project = None
            material = None
            localidad = "Rosario"
            colocacion = True
            pileta = None
            anafe = None
            sink_type = None
            notes = None

        brief = build_brief_from_quote_columns(FakeQuote())
        assert "Cliente: Erica Bernardi" in brief

        result = _analyze_regex_fallback(brief)
        assert result["client_name"] == "Erica Bernardi", (
            f"roundtrip falló: brief={brief!r}, extrajo {result['client_name']!r}"
        )
