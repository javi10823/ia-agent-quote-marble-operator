"""Tests para PR #394 — Gate de auto-estimate en `/api/v1/quote/{id}/files`.

Regla acordada con el operador:
    Si el quote tiene `source="web"` Y se guardó al menos 1 archivo
    válido en la request, NO se dispara el `_process_plan_background`
    (agente Valentina calculando estimate). El response incluye los 3
    campos aditivos: `estimate_skipped=True`,
    `estimate_skip_reason="web_upload_manual_review"`, `message` en
    español.

Alcance testeado:
    - Gate activo: source=web + ≥1 archivo válido guardado.
    - Gate inactivo: source != web (operador manual / flujos internos).
    - Gate inactivo: source=web pero 0 archivos válidos (ej: todos
      rechazados por tipo o tamaño).
    - File storage funciona idéntico en ambos casos (saved + source_files
      se escriben en DB).
    - Campos aditivos del response no rompen clientes viejos (ok, saved,
      errors, files siguen presentes).
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.quote import Quote


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


async def _insert_quote(db_session, *, source: str | None = "web") -> str:
    """Inserta un quote limpio sin breakdown, con el `source` dado.
    Simula el quote creado por `POST /api/v1/quote` antes del upload
    de archivos."""
    import uuid
    from app.models.quote import QuoteStatus

    qid = f"web-{uuid.uuid4()}"
    q = Quote(
        id=qid,
        client_name="Test Client",
        project="Cocina test",
        material="Silestone Blanco Norte",
        status=QuoteStatus.DRAFT,
        source=source,
        is_read=False,
    )
    db_session.add(q)
    await db_session.commit()
    return qid


def _dummy_pdf_bytes() -> bytes:
    """Bytes mínimos válidos como PDF (header %PDF-1.4 + trailer)."""
    return b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _upload_payload_pdf(name: str = "plano.pdf") -> dict:
    """Payload multipart válido para un solo PDF."""
    return {
        "files": (name, io.BytesIO(_dummy_pdf_bytes()), "application/pdf"),
    }


# ─────────────────────────────────────────────────────────────────────
# Gate activo: source=web + archivo válido
# ─────────────────────────────────────────────────────────────────────


class TestGateActive:
    """Web + archivo válido → skip auto-estimate + response con flags."""

    @pytest.mark.asyncio
    async def test_skips_background_processing(self, client, db_session):
        """El `asyncio.create_task(_process_plan_background)` NO debe
        invocarse. Mock del bg task + assert en el número de calls."""
        qid = await _insert_quote(db_session, source="web")

        with patch(
            "app.modules.quote_engine.router._schedule_agent_background_processing",
        ) as mock_schedule, patch(
            "app.modules.agent.tools.drive_tool.upload_single_file_to_drive",
            new_callable=AsyncMock,
            return_value={"ok": False},
        ):
            res = await client.post(
                f"/api/v1/quote/{qid}/files",
                files=_upload_payload_pdf(),
            )

        assert res.status_code == 200, res.text
        # El gate corta ANTES de asyncio.create_task → 0 invocaciones.
        assert mock_schedule.call_count == 0

    @pytest.mark.asyncio
    async def test_response_includes_skip_flags(self, client, db_session):
        """Response con los 3 campos aditivos."""
        qid = await _insert_quote(db_session, source="web")

        with patch(
            "app.modules.agent.tools.drive_tool.upload_single_file_to_drive",
            new_callable=AsyncMock,
            return_value={"ok": False},
        ):
            res = await client.post(
                f"/api/v1/quote/{qid}/files",
                files=_upload_payload_pdf(),
            )

        body = res.json()
        assert body["ok"] is True
        assert body["estimate_skipped"] is True
        assert body["estimate_skip_reason"] == "web_upload_manual_review"
        assert body["message"] == (
            "Archivo recibido. Un operador revisará la información antes de cotizar."
        )

    @pytest.mark.asyncio
    async def test_file_storage_unchanged(self, client, db_session):
        """El gate NO toca la lógica de storage: saved, source_files,
        response.files siguen iguales."""
        qid = await _insert_quote(db_session, source="web")

        with patch(
            "app.modules.agent.tools.drive_tool.upload_single_file_to_drive",
            new_callable=AsyncMock,
            return_value={"ok": False},
        ):
            res = await client.post(
                f"/api/v1/quote/{qid}/files",
                files=_upload_payload_pdf("plano-cocina.pdf"),
            )

        body = res.json()
        assert body["saved"] == 1
        assert len(body["files"]) == 1
        assert body["files"][0]["filename"] == "plano-cocina.pdf"
        assert body["files"][0]["type"] == "application/pdf"

        # Persistencia: source_files del quote se actualizó.
        result = await db_session.execute(select(Quote).where(Quote.id == qid))
        q = result.scalar_one()
        assert q.source_files
        assert q.source_files[0]["filename"] == "plano-cocina.pdf"
        # Y el quote sigue sin breakdown (gate cortó el bg task).
        assert not q.quote_breakdown


# ─────────────────────────────────────────────────────────────────────
# Gate inactivo: otros sources
# ─────────────────────────────────────────────────────────────────────


class TestGateInactive:
    """Fuera de `source=web` el flujo auto-estimate sigue intacto."""

    @pytest.mark.asyncio
    async def test_source_none_triggers_background(self, client, db_session):
        """Quote con `source=None` (legacy / operador manual creando
        desde la UI) → sigue disparando el background task."""
        qid = await _insert_quote(db_session, source=None)

        with patch(
            "app.modules.quote_engine.router._schedule_agent_background_processing",
        ) as mock_schedule, patch(
            "app.modules.agent.tools.drive_tool.upload_single_file_to_drive",
            new_callable=AsyncMock,
            return_value={"ok": False},
        ):
            res = await client.post(
                f"/api/v1/quote/{qid}/files",
                files=_upload_payload_pdf(),
            )

        assert res.status_code == 200
        # source != "web" → NO skipea → create_task se invoca.
        assert mock_schedule.call_count == 1
        body = res.json()
        # Response sin los campos aditivos.
        assert "estimate_skipped" not in body
        assert "estimate_skip_reason" not in body

    @pytest.mark.asyncio
    async def test_source_manual_triggers_background(self, client, db_session):
        """Quote con `source="manual"` (u otro valor no-web) también
        dispara el auto-estimate."""
        qid = await _insert_quote(db_session, source="manual")

        with patch(
            "app.modules.quote_engine.router._schedule_agent_background_processing",
        ) as mock_schedule, patch(
            "app.modules.agent.tools.drive_tool.upload_single_file_to_drive",
            new_callable=AsyncMock,
            return_value={"ok": False},
        ):
            res = await client.post(
                f"/api/v1/quote/{qid}/files",
                files=_upload_payload_pdf(),
            )

        assert res.status_code == 200
        assert mock_schedule.call_count == 1


# ─────────────────────────────────────────────────────────────────────
# Gate depende de archivos VÁLIDOS guardados, no de la request
# ─────────────────────────────────────────────────────────────────────


class TestGateRequiresValidSavedFile:
    """El gate se activa por `bool(saved)`, NO por `files` del request.
    Si todos los archivos fueron rechazados (tipo / tamaño / empty), el
    gate queda inactivo y el quote sigue sin auto-estimate igual
    (porque el `if saved and not quote_breakdown` sin skip también
    requiere archivos)."""

    @pytest.mark.asyncio
    async def test_web_with_invalid_file_does_not_set_skip_flag(
        self, client, db_session,
    ):
        """Archivo con MIME no soportado → rechazado por validación →
        `saved=0` → gate NO se activa → response SIN `estimate_skipped`."""
        qid = await _insert_quote(db_session, source="web")

        with patch(
            "app.modules.agent.tools.drive_tool.upload_single_file_to_drive",
            new_callable=AsyncMock,
            return_value={"ok": False},
        ):
            res = await client.post(
                f"/api/v1/quote/{qid}/files",
                files={"files": (
                    "archivo.xyz",
                    io.BytesIO(b"algo"),
                    "application/octet-stream",
                )},
            )

        body = res.json()
        assert res.status_code == 200
        assert body["saved"] == 0
        assert len(body["errors"]) == 1
        # Sin archivos válidos, el gate no se activa → response sin
        # campos aditivos (coherente: no hay nada que "skipear"
        # porque no hay input que generara estimate).
        assert "estimate_skipped" not in body
        assert "estimate_skip_reason" not in body


# ─────────────────────────────────────────────────────────────────────
# Quote con breakdown pre-existente: gate no interfiere
# ─────────────────────────────────────────────────────────────────────


class TestGateDoesNotTouchExistingBreakdowns:
    @pytest.mark.asyncio
    async def test_web_upload_when_breakdown_already_exists(
        self, client, db_session,
    ):
        """Quote web con breakdown YA calculado (ej: subieron archivo
        complementario post-estimate). El gate y el `if not
        quote.quote_breakdown` ambos cortan el bg task; lo importante es
        que tampoco se dispara — y que saved sigue escribiendo archivos."""
        import uuid
        from app.models.quote import QuoteStatus

        qid = f"web-{uuid.uuid4()}"
        q = Quote(
            id=qid,
            client_name="X",
            project="Y",
            status=QuoteStatus.PENDING,
            source="web",
            is_read=False,
            quote_breakdown={"material_name": "SILESTONE", "total_ars": 100},
        )
        db_session.add(q)
        await db_session.commit()

        with patch(
            "app.modules.quote_engine.router._schedule_agent_background_processing",
        ) as mock_schedule, patch(
            "app.modules.agent.tools.drive_tool.upload_single_file_to_drive",
            new_callable=AsyncMock,
            return_value={"ok": False},
        ):
            res = await client.post(
                f"/api/v1/quote/{qid}/files",
                files=_upload_payload_pdf(),
            )

        assert res.status_code == 200
        # Nunca se dispara (el breakdown ya existía + el gate también corta).
        assert mock_schedule.call_count == 0
        body = res.json()
        # Pero el flag estimate_skipped SÍ sale porque source=web + archivo
        # fueron las condiciones del gate (independiente del breakdown).
        assert body["estimate_skipped"] is True
        assert body["saved"] == 1
