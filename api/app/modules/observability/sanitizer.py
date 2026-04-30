"""Sanitización + truncado de payloads para `audit_events`.

Dos transformaciones independientes:

1. `redact_sensitive(payload)` — reemplaza valores de keys "negras"
   por `"<redacted>"`. Se aplica recursivamente en dicts y listas.
   Keys negras: PII (phone, address, dni), credenciales (password,
   token, api_key), headers de auth (authorization, cookie).

   No se filtra por valor (no buscamos "patrones de teléfono"). Solo
   por nombre de key. Si el operador agrega un campo libre con un
   teléfono adentro, queda. Trade-off explícito: simplicidad >
   completitud heurística.

2. `truncate_payload(payload, max_bytes)` — si la serialización
   JSON supera `max_bytes` (default 8 KB), reemplaza por un shape
   sin valores: `{key: "<truncated>"}`. La UI muestra
   `payload_truncated=True` y el operador sabe que hay que mirar
   los logs raw para el detalle.

Ambas se exponen como helpers puros: el caller los compone en
`log_event()`.
"""
from __future__ import annotations

import json
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Sanitización
# ─────────────────────────────────────────────────────────────────────

# Lista negra de keys. Match case-insensitive sobre el nombre exacto
# y sobre substring (ej. "client_phone" matchea por contener "phone").
# Mantener corta y explícita — agregar acá si aparece un campo nuevo
# que no debería salir en logs.
_REDACT_KEY_SUBSTRINGS = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "phone",
    "telefono",
    "whatsapp",
    "address",
    "direccion",
    "dni",
    "cuit",
    "email",  # client_email, user_email — todos PII
)

_REDACTED = "<redacted>"


def _key_is_sensitive(key: str) -> bool:
    if not isinstance(key, str):
        return False
    lower = key.lower()
    return any(s in lower for s in _REDACT_KEY_SUBSTRINGS)


def redact_sensitive(value: Any) -> Any:
    """Reemplaza recursivamente valores de keys negras por
    `"<redacted>"`. No muta el input — devuelve copia.

    Reglas:
    - dict → recursar en values; si la key matchea, valor reemplazado
      sin entrar en el contenido (no inspeccionamos los hijos de un
      campo ya redactado).
    - list / tuple → recursar en cada elemento.
    - cualquier otro tipo → devolver tal cual.
    """
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _key_is_sensitive(k):
                out[k] = _REDACTED
            else:
                out[k] = redact_sensitive(v)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    return value


# ─────────────────────────────────────────────────────────────────────
# Truncado
# ─────────────────────────────────────────────────────────────────────

# 2 KB default. Override 4 KB para eventos con payload estructurado
# pesado (`quote.calculated`, `docs.generated`). Razón: con 13 event
# types × 50 quotes/día × 365 días ≈ 237K rows/año, 2 KB → ~480 MB/año
# vs 8 KB → ~1.9 GB/año. Si un payload realmente excede 2 KB, sale
# `payload_truncated=True` con shape — el bundle copy igual está
# capeado a 4000 chars, no necesita el detalle full acá.
DEFAULT_MAX_BYTES = 2 * 1024  # 2 KB serializado
LARGE_PAYLOAD_MAX_BYTES = 4 * 1024  # 4 KB — para quote.calculated, docs.generated


def _serialize(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(payload)


def truncate_payload(
    payload: Any,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[Any, bool]:
    """Devuelve `(payload_final, truncated_flag)`.

    Si la serialización del payload original supera `max_bytes`,
    reemplaza valores por `"<truncated>"` preservando la estructura
    superficial (top-level keys). Esto permite a la UI mostrar
    "payload truncado, keys: [a, b, c]" sin perder el shape.

    Para payloads complejos anidados, mantenemos solo el primer nivel.
    Si el operador necesita el detalle, debe ir a los logs raw.
    """
    if payload is None:
        return {}, False
    serialized = _serialize(payload)
    size = len(serialized.encode("utf-8"))
    if size <= max_bytes:
        return payload, False

    # Shape-only fallback: top-level keys, valores reemplazados.
    if isinstance(payload, dict):
        truncated = {k: "<truncated>" for k in payload.keys()}
        return truncated, True
    if isinstance(payload, list):
        return [f"<truncated: list of {len(payload)} items>"], True
    return {"_value": "<truncated>"}, True


# ─────────────────────────────────────────────────────────────────────
# Composición
# ─────────────────────────────────────────────────────────────────────


def sanitize_for_audit(
    payload: Any,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[Any, bool]:
    """Pipeline completo: redact → truncate.

    Orden importa: redactamos primero (puede achicar el payload si
    los valores sensibles eran grandes), después truncamos si sigue
    siendo grande.
    """
    redacted = redact_sensitive(payload)
    return truncate_payload(redacted, max_bytes)
