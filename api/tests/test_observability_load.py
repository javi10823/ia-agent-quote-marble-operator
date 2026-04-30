"""GATE de Phase 2 — test de carga del helper `log_event`.

Acordado con el operador:

> "Test de carga: simular 10 inserts seguidos en CI, assertear p95
> total < 100ms. Si falla, PARAR y avisar antes de implementar
> batching/async writer."

Justificación del threshold:

- Worst case medido en el diagnóstico: chat con 4 tool calls →
  1 (stream_started) + 4 (tool_called) + 4 (tool_result) +
  1 (chat.message_sent) ≈ 10 inserts.
- 100ms total p95 es el techo aceptable para no degradar la
  percepción del operador (los SSE chunks tardan más que eso).
- Si el helper sostenido excede 100ms con SQLite in-memory,
  Postgres en Railway con red de por medio va a ser peor → no
  vale la pena seguir con el plan síncrono. PR pausa y se evalúa
  el plan B (logger async por archivo).

Si este test falla:
1. NO mergear el PR.
2. Avisar al operador con el p95 medido.
3. Implementar plan B (`events.jsonl` per-quote + worker).
"""
from __future__ import annotations

import time

import pytest

from app.modules.observability import log_event


@pytest.mark.asyncio
async def test_log_event_p95_under_100ms_for_10_inserts(db_session):
    """10 inserts seguidos en SQLite in-memory deben totalizar
    < 100ms p95 sobre 5 corridas. Si SQLite ya pega contra el techo,
    Postgres no va a ser mejor — gate del plan síncrono."""
    runs = []
    for _ in range(5):
        start = time.perf_counter()
        for i in range(10):
            await log_event(
                db_session,
                event_type=f"test.event_{i % 3}",
                source="test",
                summary=f"Load test event {i}",
                quote_id=f"quote-{i}",
                payload={"index": i, "data": "x" * 100},
            )
        await db_session.commit()
        runs.append((time.perf_counter() - start) * 1000)

    runs.sort()
    p95 = runs[-1]  # con n=5, el peor es ≈ p95
    median = runs[len(runs) // 2]

    print(
        f"\n[load-test] runs_ms={[round(r, 2) for r in runs]} "
        f"median={median:.2f}ms p95={p95:.2f}ms"
    )

    assert p95 < 100.0, (
        f"p95 {p95:.2f}ms exceeds 100ms threshold — STOP and consider "
        f"plan B (async writer to events.jsonl + flush worker). "
        f"All runs (ms): {runs}"
    )
