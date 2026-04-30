"""Observability module — auditoría operativa consultable.

Diferencia de scope con `app.modules.agent._trace`:

- `_trace.py` → debug técnico fino, prefijos textuales en `logger.info`
  (string libre), grepable en Railway pero efímero. Útil para debugging
  inmediato del flow agéntico.

- `observability/` → historia operativa **persistida** en `audit_events`.
  Queryable cross-quote ("todos los regenerate_docs por usuario X en
  los últimos 7 días") y por timeline de un quote específico ("¿qué
  pasó con el quote DYSCON?"). Sirve a la UI `/quotes/:id/audit`.

Reglas de uso (acordadas con el operador):

1. **Síncrono.** Sin background tasks. El INSERT corre dentro del
   request del operador.
2. **Fail-safe.** Si la DB falla, el flow del operador NO se rompe —
   el evento se pierde y se loggea un warning.
3. **Sanitizado.** Lista negra de keys (phone, address, password,
   token, etc.) → `<redacted>`. Aplicado recursivamente.
4. **Truncado.** Payload > 8 KB serializado → `payload_truncated=True`,
   se guarda shape sin valores.
5. **No backfill.** Quotes pre-deploy no tienen eventos. Empty state
   explícito en la UI.
"""
from app.modules.observability.helper import log_event
from app.modules.observability.models import AuditEvent

__all__ = ["log_event", "AuditEvent"]
