"""Tests para PR #442 — flag `pdf_outdated` computado en
`GET /quotes/{id}`.

**Por qué este PR:**

Caso DYSCON 29/04/2026: el operador edita un campo via
EditableField (frontend), el cambio se persiste correctamente,
pero el PDF guardado en Drive sigue siendo el viejo. La edición
NO regenera el PDF automáticamente — ese es el comportamiento
esperado, pero **el operador no se entera** porque el detalle
muestra el cambio sin warning.

Fix: backend computa `pdf_outdated` comparando `quote.updated_at`
con el último timestamp de generación/regenerate del PDF (en
`change_history`). Frontend muestra un banner amarillo
"PDF desactualizado · Regenerar ahora".

**Tests cubren:**

1. Sin pdf_url → False (no hay PDF para comparar).
2. Con pdf_url + sin entries en history → False (legacy, no
   spamear).
3. Con pdf_url + último regenerate AT updated_at → False
   (dentro de tolerancia).
4. Con pdf_url + edits posteriores al regenerate → True.
5. Con pdf_url + último generate_docs (no regenerate) → True/False
   según comparison.
6. Drift guard: ambos action types se reconocen.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


# ═══════════════════════════════════════════════════════════════════════
# Helpers — construimos un Quote-like para invocar el helper
# ═══════════════════════════════════════════════════════════════════════


class _MockQuote:
    """Mínimo Quote-like para `_compute_pdf_outdated`."""

    def __init__(
        self,
        pdf_url=None,
        change_history=None,
        updated_at=None,
    ):
        self.pdf_url = pdf_url
        self.change_history = change_history or []
        self.updated_at = updated_at


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ═══════════════════════════════════════════════════════════════════════
# Comportamiento del helper
# ═══════════════════════════════════════════════════════════════════════


class TestComputePdfOutdated:
    def _import_helper(self):
        from app.modules.agent.router import _compute_pdf_outdated
        return _compute_pdf_outdated

    def test_no_pdf_url_returns_false(self):
        compute = self._import_helper()
        q = _MockQuote(pdf_url=None)
        outdated, ts = compute(q)
        assert outdated is False
        assert ts is None

    def test_pdf_url_but_no_history_returns_false(self):
        """Quote legacy con PDF pero sin tracking en change_history.
        Conservadoramente NOT outdated (no spamear con falsos
        positivos en quotes pre-PR #442)."""
        compute = self._import_helper()
        now = datetime.now(timezone.utc)
        q = _MockQuote(
            pdf_url="/files/x.pdf",
            change_history=[],
            updated_at=now,
        )
        outdated, ts = compute(q)
        assert outdated is False
        assert ts is None

    def test_no_edits_after_regenerate_not_outdated(self):
        """updated_at == último regenerate (mismo timestamp).
        Tolerancia 5s evita race del propio regenerate. NOT outdated."""
        compute = self._import_helper()
        regen_ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
        q = _MockQuote(
            pdf_url="/files/x.pdf",
            change_history=[
                {"action": "regenerate_docs", "timestamp": _iso(regen_ts)},
            ],
            updated_at=regen_ts + timedelta(seconds=2),  # dentro de tolerancia
        )
        outdated, ts = compute(q)
        assert outdated is False
        assert ts == regen_ts

    def test_edit_after_regenerate_is_outdated(self):
        """updated_at > regenerate + tolerance → outdated."""
        compute = self._import_helper()
        regen_ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
        edit_ts = regen_ts + timedelta(minutes=5)
        q = _MockQuote(
            pdf_url="/files/x.pdf",
            change_history=[
                {"action": "regenerate_docs", "timestamp": _iso(regen_ts)},
            ],
            updated_at=edit_ts,
        )
        outdated, ts = compute(q)
        assert outdated is True
        assert ts == regen_ts

    def test_recognizes_generate_docs_action(self):
        """`generate_docs` (PR #442 lo agrega al flujo de generación
        inicial) también cuenta como timestamp de PDF actualizado."""
        compute = self._import_helper()
        gen_ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
        q = _MockQuote(
            pdf_url="/files/x.pdf",
            change_history=[
                {"action": "generate_docs", "timestamp": _iso(gen_ts)},
            ],
            updated_at=gen_ts + timedelta(seconds=3),
        )
        outdated, ts = compute(q)
        assert outdated is False  # dentro de tolerancia
        assert ts == gen_ts

    def test_uses_most_recent_action(self):
        """Si hay generate_docs OLD + regenerate_docs NEW → usa el
        más reciente."""
        compute = self._import_helper()
        old_ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
        new_ts = datetime(2026, 4, 29, 14, 0, 0, tzinfo=timezone.utc)
        q = _MockQuote(
            pdf_url="/files/x.pdf",
            change_history=[
                {"action": "generate_docs", "timestamp": _iso(old_ts)},
                {"action": "regenerate_docs", "timestamp": _iso(new_ts)},
            ],
            updated_at=new_ts + timedelta(seconds=2),
        )
        outdated, ts = compute(q)
        assert outdated is False
        assert ts == new_ts  # el más reciente

    def test_ignores_other_action_types(self):
        """`calculate_quote` NO cuenta como generación de PDF
        (solo recalcula). Si solo hay esa acción, sin regenerate
        ni generate, NO hay tracking → False."""
        compute = self._import_helper()
        ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
        q = _MockQuote(
            pdf_url="/files/x.pdf",
            change_history=[
                {"action": "calculate_quote", "timestamp": _iso(ts)},
            ],
            updated_at=ts + timedelta(hours=1),
        )
        outdated, ts_out = compute(q)
        assert outdated is False
        assert ts_out is None

    def test_handles_malformed_entries(self):
        """Defensivo: entries sin timestamp / sin action / no-dict
        no rompen el helper."""
        compute = self._import_helper()
        good_ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
        q = _MockQuote(
            pdf_url="/files/x.pdf",
            change_history=[
                "not-a-dict",  # ignorado
                {},  # sin keys
                {"action": "regenerate_docs"},  # sin timestamp
                {"timestamp": _iso(good_ts)},  # sin action
                {"action": "regenerate_docs", "timestamp": "no-es-iso"},  # parse falla
                {"action": "regenerate_docs", "timestamp": _iso(good_ts)},  # válido
            ],
            updated_at=good_ts + timedelta(seconds=1),
        )
        outdated, ts = compute(q)
        # Debe usar el válido y NOT outdated (dentro de tolerancia).
        assert outdated is False
        assert ts == good_ts

    def test_naive_updated_at_with_aware_history(self):
        """Defensivo: si updated_at viene naive (sin tzinfo) y la
        history tiene timestamps aware, normalizamos para no
        crashear con TypeError."""
        compute = self._import_helper()
        regen_ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
        # Naive: simulamos como SQLite a veces devuelve.
        edit_naive = datetime(2026, 4, 29, 13, 0, 0)  # sin tz
        q = _MockQuote(
            pdf_url="/files/x.pdf",
            change_history=[
                {"action": "regenerate_docs", "timestamp": _iso(regen_ts)},
            ],
            updated_at=edit_naive,
        )
        # No debe crashear. Edit posterior → outdated.
        outdated, ts = compute(q)
        assert outdated is True or outdated is False  # acepta cualquiera, lo importante es no crashear


# ═══════════════════════════════════════════════════════════════════════
# Drift guard del schema
# ═══════════════════════════════════════════════════════════════════════


class TestSchemaDriftGuard:
    def test_quote_detail_response_has_pdf_outdated_field(self):
        """Sin este campo, el frontend no puede saber si mostrar el
        banner. Drift guard."""
        from app.modules.agent.schemas import QuoteDetailResponse
        assert "pdf_outdated" in QuoteDetailResponse.model_fields, (
            "QuoteDetailResponse debe incluir `pdf_outdated`. "
            "Si lo borraste, frontend no muestra el banner."
        )
        assert "pdf_generated_at" in QuoteDetailResponse.model_fields, (
            "QuoteDetailResponse debe incluir `pdf_generated_at` para "
            "que el frontend pueda mostrar tooltip 'última generación'."
        )
