"""SQLAlchemy model para `audit_events`.

Schema acordado con el operador (Phase 1 diagnostic + 5 ajustes):

- `summary` TEXT NOT NULL → frase humana corta para listar en UI sin
  parsear payload.
- `source` VARCHAR(32) → permite filtrar "todos los warnings del
  validator" o "eventos del módulo docs".
- `session_id` VARCHAR(64) NULL → reservado. Hoy se popula con
  `quote_id` cuando aplica o queda NULL. Evita migration futura.
- `request_id` UUID NULL → correlation por request HTTP, generado en
  middleware. Indexado para "todo lo que pasó en este request".
- `turn_index` INTEGER NULL → índice en `Quote.messages` cuando aplica
  (chat). NULL en eventos no-chat (regenerate, status_change).
- `payload` JSONB → ya sanitizado y truncado (ver `sanitizer.py`).
- `payload_truncated` BOOLEAN → flag explícito para que la UI muestre
  "payload truncado".

Índices: ver migration en `app/core/database.py`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    # UUID en formato string. PostgreSQL usa gen_random_uuid() vía
    # default server-side; en SQLite (tests) se genera en Python.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    quote_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(20), nullable=False)

    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # JSONB en Postgres / JSON en SQLite — SQLAlchemy maneja el dialect.
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload_truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Phase 2 — TRUE cuando este event fue grabado con `global_debug`
    # activo. Implica que su payload puede pesar hasta 16 KB (vs 2/4
    # KB normales) y contiene `tool_input` / `tool_result` / brief
    # text completos. Bundle copy NO incluye payloads de estos events.
    debug_payload: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
