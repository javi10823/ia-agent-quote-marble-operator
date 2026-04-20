"""Cache global del topology output por plan_hash (cross-quote).

Motivación: el topology VLM es estocástico — el mismo PDF puede dar bboxes
distintos entre corridas. Si cacheamos en `quote_breakdown` del quote,
cada nueva quote con el mismo PDF vuelve a pagar VLM + vuelve a poder
divergir. El cache GLOBAL por plan_hash garantiza que una vez que el
topology salió (y pasó validaciones contra el brief), se reusa para
cualquier quote futura con el mismo archivo.

**Shape intencionalmente mínimo.** Si llegan más de 2 divergencias, no
guardamos toda la historia — solo incrementamos `divergence_count` y
el snapshot perdedor queda en `quote_breakdown.topology_cache_meta`
del quote que lo produjo (auditoría por-quote, no historia global).
"""
from datetime import datetime
from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class PlanTopologyCache(Base):
    __tablename__ = "plan_topology_cache"

    # sha256(plan_bytes)[:16] — mismo hash que usa _run_dual_read
    plan_hash: Mapped[str] = mapped_column(String(32), primary_key=True)

    # Response JSON del topology LLM tal cual. Al reusarlo, el reader lo
    # anota con _from_cache=True antes de devolver.
    topology_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # "stable" | "unstable". Inicia stable. Si dos corridas del mismo hash
    # divergen materialmente (n_regions distinto o bbox IoU<0.5), pasa a
    # unstable. Los retries/bypass NO disparan sobre un hash unstable —
    # si ya sabemos que es inestable, usar cache + marcar review y seguir.
    stability_status: Mapped[str] = mapped_column(String(16), default="stable", nullable=False)

    # n_regions del topology_json actual, precomputado para queries rápidas.
    n_regions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Cuántas veces un fresh topology del mismo hash divergió del cache.
    # No es el número de corridas — es el número de divergencias detectadas.
    divergence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Para trazabilidad: qué quote produjo este topology.
    source_quote_id: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
