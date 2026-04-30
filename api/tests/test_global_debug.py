"""Tests Phase 2 — modo debug global.

Cubre:
- Helper `_is_global_debug_active`: enabled+until válido, expirado,
  manual dentro/fuera del cap de 24h.
- `log_event()` con debug ON: payload extendido a 16 KB +
  flag `debug_payload=True`.
- `log_event()` con debug OFF: trunca normal, descarta `debug_only_payload`.
- Sanitizer: keys nuevas redactadas (client_name, precio_costo, etc.).
  Phase 1 keys siguen redactadas (regression guard).
- Endpoints: POST toggle + GET status + cron shutoff.
- Bundle copy: events con `debug_payload=True` → placeholder.
- GATE de carga: 10 inserts con debug ON, p95 < 100ms.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.observability import log_event
from app.modules.observability.helper import _is_global_debug_active
from app.modules.observability.sanitizer import (
    DEBUG_PAYLOAD_MAX_BYTES,
    DEFAULT_MAX_BYTES,
    redact_sensitive,
)
from app.modules.observability.system_config import (
    GLOBAL_DEBUG_KEY,
    SystemConfig,
)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


async def _set_debug(db_session, *, enabled: bool, until=None, started_at=None):
    """Inserta/actualiza la fila system_config[global_debug]."""
    from sqlalchemy import select

    value = {
        "enabled": enabled,
        "mode": "manual" if enabled and until is None else ("1h" if enabled else None),
        "until": until.isoformat() if until else None,
        "started_at": started_at.isoformat() if started_at else None,
        "started_by": "test" if enabled else None,
    }
    result = await db_session.execute(
        select(SystemConfig).where(SystemConfig.key == GLOBAL_DEBUG_KEY)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = value
    else:
        db_session.add(SystemConfig(
            key=GLOBAL_DEBUG_KEY, value=value,
            updated_by="test",
        ))
    await db_session.commit()


# ═══════════════════════════════════════════════════════════════════════
# Helper _is_global_debug_active
# ═══════════════════════════════════════════════════════════════════════


class TestIsGlobalDebugActive:
    @pytest.mark.asyncio
    async def test_no_row_returns_false(self, db_session):
        assert await _is_global_debug_active(db_session) is False

    @pytest.mark.asyncio
    async def test_enabled_false_returns_false(self, db_session):
        await _set_debug(db_session, enabled=False)
        assert await _is_global_debug_active(db_session) is False

    @pytest.mark.asyncio
    async def test_enabled_with_future_until_returns_true(self, db_session):
        until = datetime.now(timezone.utc) + timedelta(hours=1)
        started = datetime.now(timezone.utc)
        await _set_debug(db_session, enabled=True, until=until, started_at=started)
        assert await _is_global_debug_active(db_session) is True

    @pytest.mark.asyncio
    async def test_enabled_with_past_until_returns_false(self, db_session):
        until = datetime.now(timezone.utc) - timedelta(minutes=5)
        started = datetime.now(timezone.utc) - timedelta(hours=2)
        await _set_debug(db_session, enabled=True, until=until, started_at=started)
        assert await _is_global_debug_active(db_session) is False

    @pytest.mark.asyncio
    async def test_manual_within_24h_returns_true(self, db_session):
        # Modo manual: until=None, started_at hace 5h → activo.
        started = datetime.now(timezone.utc) - timedelta(hours=5)
        await _set_debug(db_session, enabled=True, until=None, started_at=started)
        assert await _is_global_debug_active(db_session) is True

    @pytest.mark.asyncio
    async def test_manual_after_24h_returns_false(self, db_session):
        # Modo manual: until=None, started_at hace 25h → NO activo
        # (cron debería apagarlo, pero acá testeamos el helper).
        started = datetime.now(timezone.utc) - timedelta(hours=25)
        await _set_debug(db_session, enabled=True, until=None, started_at=started)
        assert await _is_global_debug_active(db_session) is False


# ═══════════════════════════════════════════════════════════════════════
# log_event() con debug ON / OFF
# ═══════════════════════════════════════════════════════════════════════


class TestLogEventDebugMode:
    @pytest.mark.asyncio
    async def test_debug_off_truncates_normal_and_drops_debug_only_payload(
        self, db_session,
    ):
        await _set_debug(db_session, enabled=False)
        # 5 KB en debug_only_payload → en modo normal NO debe aparecer.
        big_data = "x" * 5000
        ev = await log_event(
            db_session,
            event_type="test.debug_off",
            source="test",
            summary="off",
            payload={"k": "v"},
            debug_only_payload={"big": big_data},
        )
        await db_session.commit()
        assert ev.debug_payload is False
        # `big` NO está en el payload final (descartado).
        assert "big" not in (ev.payload or {})

    @pytest.mark.asyncio
    async def test_debug_on_merges_debug_only_payload(self, db_session):
        until = datetime.now(timezone.utc) + timedelta(hours=1)
        await _set_debug(
            db_session, enabled=True, until=until,
            started_at=datetime.now(timezone.utc),
        )
        big_data = {"pieces": [{"largo": 2.0, "prof": 0.6}] * 10}
        ev = await log_event(
            db_session,
            event_type="agent.tool_called",
            source="agent",
            summary="tool called",
            payload={"tool": "calculate_quote"},
            debug_only_payload={"tool_input": big_data},
        )
        await db_session.commit()
        assert ev.debug_payload is True
        assert "tool_input" in ev.payload
        assert ev.payload["tool"] == "calculate_quote"

    @pytest.mark.asyncio
    async def test_debug_on_truncates_at_16kb(self, db_session):
        until = datetime.now(timezone.utc) + timedelta(hours=1)
        await _set_debug(
            db_session, enabled=True, until=until,
            started_at=datetime.now(timezone.utc),
        )
        # Payload >> 16 KB → debe truncarse a shape pero con flag debug.
        huge = {"data": "x" * 20_000}
        ev = await log_event(
            db_session,
            event_type="test.huge",
            source="test",
            summary="huge",
            payload=huge,
        )
        await db_session.commit()
        assert ev.payload_truncated is True
        assert ev.debug_payload is True


# ═══════════════════════════════════════════════════════════════════════
# Sanitizer — keys nuevas + regression guard de Phase 1
# ═══════════════════════════════════════════════════════════════════════


class TestSanitizerPhase2:
    def test_phase1_keys_still_redacted(self):
        """REGRESSION GUARD: las 15 keys de Phase 1 siguen redactadas."""
        phase1_keys = [
            "password", "token", "secret", "api_key", "apikey",
            "authorization", "cookie", "phone", "telefono", "whatsapp",
            "address", "direccion", "dni", "cuit", "email",
        ]
        for k in phase1_keys:
            out = redact_sensitive({k: "VALUE"})
            assert out[k] == "<redacted>", (
                f"Phase 1 key '{k}' NO redactada — regresión silenciosa "
                f"de la blacklist."
            )

    def test_phase2_new_keys_redacted(self):
        """9 keys nuevas: client_name, cliente, nombre_cliente,
        cost_price, precio_costo, internal_price, obra,
        ubicacion_obra, destino."""
        new_keys = [
            "client_name", "cliente", "nombre_cliente",
            "cost_price", "precio_costo", "internal_price",
            "obra", "ubicacion_obra", "destino",
        ]
        for k in new_keys:
            out = redact_sensitive({k: "VALUE"})
            assert out[k] == "<redacted>", f"Phase 2 key '{k}' no redactada"

    def test_legitimate_cost_keys_NOT_redacted(self):
        """`cost_breakdown`, `labor_cost`, etc. son LEGÍTIMOS en debug
        — NO deben quedar redactados (substring `cost` solo no aplica)."""
        legitimate = ["cost_breakdown", "labor_cost", "material_cost", "cost_per_m2", "total_cost"]
        for k in legitimate:
            out = redact_sensitive({k: 12345})
            assert out[k] == 12345, (
                f"'{k}' fue redactado pero es LEGÍTIMO. "
                f"Si se rompe, revisar blacklist (no debe contener `cost` solo)."
            )

    def test_localidad_NOT_redacted(self):
        """`localidad` es lista pública (delivery zones), no PII."""
        out = redact_sensitive({"localidad": "Rosario"})
        assert out["localidad"] == "Rosario"

    def test_project_NOT_redacted(self):
        """`project` es visible al cliente en el PDF."""
        out = redact_sensitive({"project": "Cocina Smith"})
        assert out["project"] == "Cocina Smith"


# ═══════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════


class TestGlobalDebugEndpoints:
    @pytest.mark.asyncio
    async def test_get_status_initial_disabled(self, client):
        r = await client.get("/api/admin/system-config/global-debug")
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False

    @pytest.mark.asyncio
    async def test_post_1h_enables_with_until(self, client):
        r = await client.post(
            "/api/admin/system-config/global-debug",
            json={"mode": "1h"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is True
        assert body["mode"] == "1h"
        assert body["until"] is not None
        assert body["remaining_seconds"] is not None
        assert 3500 < body["remaining_seconds"] <= 3600

    @pytest.mark.asyncio
    async def test_post_manual_no_until(self, client):
        r = await client.post(
            "/api/admin/system-config/global-debug",
            json={"mode": "manual"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert body["mode"] == "manual"
        assert body["until"] is None

    @pytest.mark.asyncio
    async def test_post_off_disables(self, client):
        # Activar primero.
        await client.post(
            "/api/admin/system-config/global-debug",
            json={"mode": "1h"},
        )
        # Apagar.
        r = await client.post(
            "/api/admin/system-config/global-debug",
            json={"mode": "off"},
        )
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    @pytest.mark.asyncio
    async def test_post_logs_audit_global_debug_toggled(
        self, client, db_session,
    ):
        await client.post(
            "/api/admin/system-config/global-debug",
            json={"mode": "1h"},
        )
        # Verificar evento en audit_events.
        from sqlalchemy import select
        from app.modules.observability.models import AuditEvent
        result = await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "audit.global_debug_toggled"
            )
        )
        events = list(result.scalars().all())
        assert len(events) >= 1
        # El payload tiene `previous_state`, `new_state`, `action`.
        last = events[-1]
        assert "action" in last.payload
        assert "new_state" in last.payload

    @pytest.mark.asyncio
    async def test_post_invalid_mode_rejected(self, client):
        r = await client.post(
            "/api/admin/system-config/global-debug",
            json={"mode": "foobar"},
        )
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
# end_of_day — zona horaria Argentina (UTC-3)
# ═══════════════════════════════════════════════════════════════════════
#
# Caso reportado por el operador: si Marina prende `end_of_day` un
# viernes a las 22:00 AR, el `until` debe ser viernes 23:59 AR =
# sábado 02:59 UTC. Si guardamos sin convertir, el cron en UTC
# apaga 3h antes de tiempo.


class TestEndOfDayTimezone:
    """Lockea el cómputo de `until` para `mode=end_of_day` en zona AR.

    Mockea `datetime.now()` en el módulo del router para simular la
    hora de Marina. Verifica:
    1. `until` guardado en DB es la hora UTC correcta (NO la AR raw).
    2. El cron en UTC NO apaga durante el período válido.
    3. El cron SÍ apaga después del cutoff UTC real.
    """

    @pytest.mark.asyncio
    async def test_end_of_day_at_22_ar_stores_correct_utc_until(
        self, client, db_session, monkeypatch,
    ):
        """Marina toca el toggle viernes 22:00 AR (= sábado 01:00 UTC).
        until debe ser sábado 02:59 UTC (= viernes 23:59 AR)."""
        from datetime import datetime, timezone
        import app.modules.observability.router as router_mod

        # Sábado 01:00 UTC == viernes 22:00 AR.
        fake_now_utc = datetime(2026, 5, 2, 1, 0, 0, tzinfo=timezone.utc)

        class _MockDateTime:
            @staticmethod
            def now(tz=None):
                if tz is None:
                    return fake_now_utc.replace(tzinfo=None)
                return fake_now_utc.astimezone(tz)

            @staticmethod
            def fromisoformat(s):
                return datetime.fromisoformat(s)

        monkeypatch.setattr(router_mod, "datetime", _MockDateTime)

        r = await client.post(
            "/api/admin/system-config/global-debug",
            json={"mode": "end_of_day"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # `until` debe ser sábado 02:59 UTC (= viernes 23:59 AR).
        until = datetime.fromisoformat(body["until"].replace("Z", "+00:00"))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        # Verificación dura: el día UTC debe ser sábado (2 de mayo)
        # y la hora UTC debe ser 02:59 (≈ 23:59 AR).
        assert until.day == 2, f"Día UTC esperado 2 (sábado), got {until.day}"
        assert until.hour == 2, f"Hora UTC esperada 2 (=23 AR), got {until.hour}"
        assert until.minute == 59
        # Check explícito en zona AR para que la intención sea legible.
        from datetime import timedelta
        ar_until = until.astimezone(timezone(timedelta(hours=-3)))
        assert ar_until.hour == 23 and ar_until.minute == 59, (
            f"En zona AR el until debe ser 23:59. got {ar_until.isoformat()}"
        )

    @pytest.mark.asyncio
    async def test_cron_does_not_shutoff_within_end_of_day_window(
        self, client, db_session,
    ):
        """Marina prende end_of_day. El cron corre 30 min después →
        NO debe apagar.

        Plant directo en DB para evitar el monkeypatching del POST.
        """
        from datetime import datetime, timedelta, timezone
        from app.modules.observability.system_config import (
            SystemConfig, GLOBAL_DEBUG_KEY,
        )

        # Setup: until = ahora + 3h (modo end_of_day típico, 22 AR + 5h).
        now_utc = datetime.now(timezone.utc)
        until = now_utc + timedelta(hours=3)
        started = now_utc - timedelta(hours=1)
        db_session.add(SystemConfig(
            key=GLOBAL_DEBUG_KEY,
            value={
                "enabled": True,
                "mode": "end_of_day",
                "until": until.isoformat(),
                "started_at": started.isoformat(),
                "started_by": "marina",
            },
            updated_by="marina",
        ))
        await db_session.commit()

        r = await client.post("/api/admin/audit/global-debug-shutoff")
        assert r.status_code == 200
        body = r.json()
        assert body["apagados"] == 0, "El cron apagó dentro del window."

    @pytest.mark.asyncio
    async def test_cron_DOES_shutoff_after_end_of_day_window(
        self, client, db_session,
    ):
        """Pasó el `until`. El cron debe apagar."""
        from datetime import datetime, timedelta, timezone
        from app.modules.observability.system_config import (
            SystemConfig, GLOBAL_DEBUG_KEY,
        )

        now_utc = datetime.now(timezone.utc)
        # until expirado hace 30 min.
        until = now_utc - timedelta(minutes=30)
        started = now_utc - timedelta(hours=5)
        db_session.add(SystemConfig(
            key=GLOBAL_DEBUG_KEY,
            value={
                "enabled": True,
                "mode": "end_of_day",
                "until": until.isoformat(),
                "started_at": started.isoformat(),
                "started_by": "marina",
            },
            updated_by="marina",
        ))
        await db_session.commit()

        r = await client.post("/api/admin/audit/global-debug-shutoff")
        body = r.json()
        assert body["apagados"] == 1
        assert body["razones"]["expired"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Breadcrumb del cron de shutoff
# ═══════════════════════════════════════════════════════════════════════


class TestShutoffBreadcrumb:
    """Para detectar silencios del cron: cada run loguea
    `audit.global_debug_shutoff_run` con `rows_affected` (puede ser 0).

    Si el cron se cae silenciosamente (excepción tragada, container
    OOM, etc.), la falta de filas durante varias horas seguidas es la
    señal.
    """

    async def _last_run_event(self, db_session):
        from sqlalchemy import select
        from app.modules.observability.models import AuditEvent
        result = await db_session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == "audit.global_debug_shutoff_run")
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @pytest.mark.asyncio
    async def test_run_logged_when_nothing_to_shutoff(
        self, client, db_session,
    ):
        """Sin debug activo → breadcrumb con rows_affected=0."""
        from app.modules.observability.system_config import (
            SystemConfig, GLOBAL_DEBUG_KEY,
        )

        # Asegurar que NO hay debug activo.
        db_session.add(SystemConfig(
            key=GLOBAL_DEBUG_KEY,
            value={"enabled": False},
            updated_by="test",
        ))
        await db_session.commit()

        r = await client.post("/api/admin/audit/global-debug-shutoff")
        assert r.status_code == 200
        # Breadcrumb persistido.
        ev = await self._last_run_event(db_session)
        assert ev is not None, "Falta breadcrumb del cron — silencio fatal."
        assert ev.payload["rows_affected"] == 0
        assert ev.actor == "system"

    @pytest.mark.asyncio
    async def test_run_logged_when_within_window(
        self, client, db_session,
    ):
        """Debug activo dentro del window → breadcrumb con rows=0,
        reason=within_window."""
        from datetime import datetime, timedelta, timezone
        from app.modules.observability.system_config import (
            SystemConfig, GLOBAL_DEBUG_KEY,
        )

        now_utc = datetime.now(timezone.utc)
        until = now_utc + timedelta(hours=2)
        db_session.add(SystemConfig(
            key=GLOBAL_DEBUG_KEY,
            value={
                "enabled": True,
                "mode": "1h",
                "until": until.isoformat(),
                "started_at": now_utc.isoformat(),
                "started_by": "marina",
            },
            updated_by="marina",
        ))
        await db_session.commit()

        r = await client.post("/api/admin/audit/global-debug-shutoff")
        ev = await self._last_run_event(db_session)
        assert ev is not None
        assert ev.payload["rows_affected"] == 0
        assert ev.payload.get("reason") == "within_window"

    @pytest.mark.asyncio
    async def test_run_logged_when_actually_shutoff(
        self, client, db_session,
    ):
        """Apagado real → breadcrumb con rows=1, reason=expired."""
        from datetime import datetime, timedelta, timezone
        from app.modules.observability.system_config import (
            SystemConfig, GLOBAL_DEBUG_KEY,
        )

        now_utc = datetime.now(timezone.utc)
        until = now_utc - timedelta(minutes=10)
        db_session.add(SystemConfig(
            key=GLOBAL_DEBUG_KEY,
            value={
                "enabled": True,
                "mode": "1h",
                "until": until.isoformat(),
                "started_at": (now_utc - timedelta(hours=2)).isoformat(),
                "started_by": "marina",
            },
            updated_by="marina",
        ))
        await db_session.commit()

        r = await client.post("/api/admin/audit/global-debug-shutoff")
        assert r.json()["apagados"] == 1
        ev = await self._last_run_event(db_session)
        assert ev is not None
        assert ev.payload["rows_affected"] == 1
        assert ev.payload.get("reason") == "expired"


# ═══════════════════════════════════════════════════════════════════════
# Cron shutoff endpoint
# ═══════════════════════════════════════════════════════════════════════


class TestGlobalDebugShutoffCron:
    @pytest.mark.asyncio
    async def test_no_active_returns_zero(self, client, db_session):
        await _set_debug(db_session, enabled=False)
        r = await client.post("/api/admin/audit/global-debug-shutoff")
        assert r.status_code == 200
        assert r.json()["apagados"] == 0

    @pytest.mark.asyncio
    async def test_active_within_window_not_shut_off(self, client, db_session):
        until = datetime.now(timezone.utc) + timedelta(hours=1)
        await _set_debug(
            db_session, enabled=True, until=until,
            started_at=datetime.now(timezone.utc),
        )
        r = await client.post("/api/admin/audit/global-debug-shutoff")
        assert r.json()["apagados"] == 0

    @pytest.mark.asyncio
    async def test_expired_until_shut_off(self, client, db_session):
        until = datetime.now(timezone.utc) - timedelta(minutes=10)
        await _set_debug(
            db_session, enabled=True, until=until,
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        r = await client.post("/api/admin/audit/global-debug-shutoff")
        body = r.json()
        assert body["apagados"] == 1
        assert body["razones"]["expired"] == 1

    @pytest.mark.asyncio
    async def test_manual_24h_cap_shut_off(self, client, db_session):
        # Modo manual con 25h → debe apagarse.
        started = datetime.now(timezone.utc) - timedelta(hours=25)
        await _set_debug(
            db_session, enabled=True, until=None, started_at=started,
        )
        r = await client.post("/api/admin/audit/global-debug-shutoff")
        body = r.json()
        assert body["apagados"] == 1
        assert body["razones"]["manual_24h_cap"] == 1


# ═══════════════════════════════════════════════════════════════════════
# GATE de carga — p95 < 100ms con debug ON
# ═══════════════════════════════════════════════════════════════════════


class TestLoadGateDebugOn:
    @pytest.mark.asyncio
    async def test_10_inserts_with_debug_on_p95_under_100ms(self, db_session):
        """GATE: si falla, PARAR antes de implementar cache TTL.

        El SELECT extra a `system_config` cada `log_event()` agrega
        overhead. Threshold mismo que Phase 1: 10 inserts seguidos
        deben totalizar < 100ms p95.
        """
        until = datetime.now(timezone.utc) + timedelta(hours=1)
        await _set_debug(
            db_session, enabled=True, until=until,
            started_at=datetime.now(timezone.utc),
        )
        runs = []
        for _ in range(5):
            start = time.perf_counter()
            for i in range(10):
                await log_event(
                    db_session,
                    event_type=f"load.debug_on_{i % 3}",
                    source="test",
                    summary=f"load test {i}",
                    quote_id=f"load-{i}",
                    payload={"i": i, "data": "x" * 100},
                    debug_only_payload={"big": "y" * 5000},
                )
            await db_session.commit()
            runs.append((time.perf_counter() - start) * 1000)

        runs.sort()
        p95 = runs[-1]
        median = runs[len(runs) // 2]
        print(
            f"\n[load-test-debug-on] runs_ms={[round(r, 2) for r in runs]} "
            f"median={median:.2f}ms p95={p95:.2f}ms"
        )
        assert p95 < 100.0, (
            f"p95 {p95:.2f}ms exceeds 100ms threshold con debug ON. "
            f"PARAR y considerar cache TTL antes de mergear. "
            f"All runs (ms): {runs}"
        )
