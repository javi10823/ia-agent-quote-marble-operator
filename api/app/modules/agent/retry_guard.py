"""Retry counter para tool calls fallidas en el loop agéntico.

**Por qué este módulo existe (PR #423, Issue #422):**

Caso DYSCON observado en producción (28/04/2026, logs `9da51080-...`):

```
1. validator rebota: "material_m2=48.584 no coincide con suma=45.55"
2. Sonnet decide "lo arreglo yo" → llama calculate_quote DE NUEVO
   con m2_override en cada pieza inventando valores.
3. pasa 845.03 m² (1755% del valor real). guardrail-B aborta. ✓
```

Sonnet NO le preguntó al operador. Intentó auto-fixear inventando
valores. El guardrail-B (específico al m² total) lo agarró ESE caso.
Cualquier validator nuevo que metamos reabre el riesgo: si Sonnet
inventa valores que NO triggerean guardrail-B, el PDF se genera con
números fabricados por la IA, no por el operador.

**Estrategia (review feedback):** retry counter en `agent.py`.

> El system prompt es demasiado frágil en conversaciones largas, ya
> lo vimos en esta sesión donde Valentina ignoró varias instrucciones
> del brief. Un contador en agent.py es un cambio de 10 líneas que da
> garantía real.

Las 2 micro-funciones de este módulo están aisladas para que sean
unit-testable sin tener que mockear la API de Anthropic. La integración
en `agent.py` es trivial — 3 líneas — y el test integration vive en
el módulo del bucle agéntico.

**Convenciones:**

- Threshold por defecto = 2: 1 ejecución original + 1 retry permitido +
  3er intento bloqueado. `count >= 2 → block` antes de ejecutar la 3ra.
- Por nombre de tool. Tool A fallando 2x no bloquea tool B.
- NO hay reset por éxito intermedio. `count` acumula errores totales
  por tool en el turno del operador (un turno = una llamada a
  `stream_chat`). Reset implícito al siguiente turno.
"""
from __future__ import annotations

from typing import Any

# Threshold default. Importable y override-able por tests.
DEFAULT_RETRY_THRESHOLD = 2


def is_tool_failure(result: Any) -> bool:
    """¿Este tool result cuenta como fallo para el retry counter?

    Reglas:
    - `dict` con `ok: False` → fallo.
    - `dict` con `error` truthy (string no vacío, etc.) → fallo.
    - Cualquier otro `dict` (sin esos campos) → éxito.
    - Lista (read_plan con content blocks de imagen+texto) → éxito.
    - None / no-dict → éxito (defensivo, no lo penalizamos al agente).

    NO clasifica el error por severidad — un warning con campo `error`
    cuenta igual que un crash. El threshold (2 fallos) absorbe el ruido
    de errores transitorios sin penalizar al primer error.
    """
    if not isinstance(result, dict):
        return False
    if result.get("ok") is False:
        return True
    err = result.get("error")
    # Truthy check: string vacío o None → no es fallo. String con
    # contenido o cualquier otro truthy → fallo.
    if err:
        return True
    return False


def build_retry_block_result(tool_name: str, prior_failures: int) -> dict:
    """Construye el `tool_result` sintético cuando se bloquea un retry.

    El mensaje fuerza a Sonnet a parar y consultar al operador. NO le
    da pistas para "fixearlo" — explícitamente le dice que NO reintente
    con valores distintos sin confirmación. El flag `_retry_blocked`
    es para que callers downstream (logs, telemetría) sepan que este
    result fue sintético, no del tool real.
    """
    return {
        "ok": False,
        "error": (
            f"⛔ Bloqueé este tool ({tool_name}) después de "
            f"{prior_failures} intentos fallidos. NO puedo resolver "
            f"esto automáticamente. Pedile al operador que revise los "
            f"datos antes de continuar — NO reintentes con valores "
            f"distintos sin su confirmación explícita."
        ),
        "_retry_blocked": True,
    }


def should_block_retry(
    tool_name: str,
    counter: dict[str, int],
    threshold: int = DEFAULT_RETRY_THRESHOLD,
) -> bool:
    """¿Hay que bloquear esta tool antes de ejecutarla?

    True si la tool ya falló `threshold` veces o más en este turno.
    Pure función — no muta `counter` ni `threshold`.
    """
    return counter.get(tool_name, 0) >= threshold


def increment_failure(
    tool_name: str,
    counter: dict[str, int],
) -> int:
    """Incrementa el contador para la tool y devuelve el nuevo valor.

    Muta `counter` in-place. Helper único para que el caller no tenga
    que recordar la fórmula `counter.get(name, 0) + 1`.
    """
    counter[tool_name] = counter.get(tool_name, 0) + 1
    return counter[tool_name]
