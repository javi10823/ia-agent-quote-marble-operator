"""Tabla `system_config` — key/value para flags globales del sistema.

Schema acordado con el operador (Phase 2 debug mode):

    CREATE TABLE system_config (
        key VARCHAR(64) PRIMARY KEY,
        value JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_by VARCHAR(120)
    );

Diferencia con `catalogs`: ese es para JSONs de materiales/precios
del negocio. `system_config` es para flags operativos del sistema
(modo debug, kill switches, feature flags futuros). Separation of
concerns: NO los mezclo.

Convenciones de keys:

- `global_debug` → ver `models.GlobalDebugConfig` para el shape.

Cualquier key futura debe documentarse acá con su shape esperado.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # Username del último que tocó la key. Distinto del `started_by`
    # que vive DENTRO de `value` para `global_debug` — `updated_by`
    # es metadata genérica de tabla, válido para cualquier key futura.
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)


# ─────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────

GLOBAL_DEBUG_KEY = "global_debug"

# Auto-shutoff hardcap del modo manual (sin `until`). Si pasaron más
# de N horas desde `started_at`, el cron lo apaga.
MANUAL_MODE_HARD_CAP_HOURS = 24
