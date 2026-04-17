"""Card editor — permite al operador modificar el dual_read_result desde el chat.

Flujo:
    1. Operador sube plano → dual_read emite card
    2. Sin confirmar, escribe en chat: "te falto un zócalo 0.5 × 0.07 en tramo 2"
    3. `is_card_modification_message()` detecta por keywords
    4. `extract_card_patch()` llama a Claude para parsear el texto → ops JSON
    5. `apply_card_patch()` aplica las ops al dict del dual_read_result
    6. El caller re-emite la card actualizada + un mensaje textual con el resumen

PR #79.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# 1) Detección de mensaje de modificación (heurística por keywords)
# ─────────────────────────────────────────────────────────────────────

_ACTION_KEYWORDS = (
    "falt",       # falto, faltó, falta, falte
    "agreg",      # agregá, agrega, agregar
    "sumá", "sumar", "añad", "poné", "poner",
    "sac", "remov", "quit", "borr", "elimin",
    "modific", "cambi", "correg", "edit", "ajust", "rectific",
)

_NOUN_KEYWORDS = (
    "zócal", "zocal",
    "mesada", "tramo", "pieza", "sector",
    "bacha", "pileta",  # para agregar/quitar MO asociada (scope limitado)
)


def is_card_modification_message(msg: str) -> bool:
    """¿El mensaje parece pedir una modificación del card no confirmado?

    Heurística barata por keywords. Debe combinar una ACCIÓN + un SUSTANTIVO
    de pieza para calificar. Ej:
        "te falto un zocalo" → True (falt + zocal)
        "agregá una mesada nueva" → True
        "¿cuánto sale?" → False (ningún keyword)
    """
    if not msg or not msg.strip():
        return False
    m = msg.lower()
    has_action = any(kw in m for kw in _ACTION_KEYWORDS)
    has_noun = any(kw in m for kw in _NOUN_KEYWORDS)
    return has_action and has_noun


# ─────────────────────────────────────────────────────────────────────
# 2) Parseo NL → ops (via LLM chico)
# ─────────────────────────────────────────────────────────────────────

_EXTRACTOR_SYSTEM = """Sos un extractor de operaciones de edición para un card de presupuesto
de marmolería. El operador describe en texto libre un cambio al despiece
detectado automáticamente. Devolvé JSON con las operaciones a aplicar.

Operaciones válidas:
- add_zocalo: {"op": "add_zocalo", "sector_id": "X", "tramo_id": "Y",
              "lado": "trasero|lateral_izq|lateral_der|frontal|<custom>",
              "ml": <number>, "alto_m": <number>}
- remove_zocalo: {"op": "remove_zocalo", "sector_id": "X", "tramo_id": "Y",
                  "lado": "<lado>"}
- edit_zocalo_ml: {"op": "edit_zocalo_ml", "sector_id": "X", "tramo_id": "Y",
                   "lado": "<lado>", "ml": <number>}
- edit_zocalo_alto: {"op": "edit_zocalo_alto", "sector_id": "X",
                     "tramo_id": "Y", "lado": "<lado>", "alto_m": <number>}
- add_tramo: {"op": "add_tramo", "sector_id": "X",
              "descripcion": "...", "largo_m": <number>, "ancho_m": <number>}
- remove_tramo: {"op": "remove_tramo", "sector_id": "X", "tramo_id": "Y"}
- edit_tramo: {"op": "edit_tramo", "sector_id": "X", "tramo_id": "Y",
               "field": "largo_m|ancho_m|m2", "value": <number>}

Reglas:
- Usá `sector_id` y `tramo_id` tal como aparecen en el dual_read actual
  (te lo paso adjunto).
- Si el operador no especifica sector pero hay uno solo → usá ese.
- Si el operador dice "tramo 2" o "segundo tramo" → mapeá al tramo_id
  por posición (primer tramo = tramos[0], segundo = tramos[1], etc.).
- Si el operador dice medidas en cm, convertilas a m (50 cm → 0.50).
- Si no hay suficiente info para una op concreta, devolvé operación
  `ask_operator` con el campo faltante:
  {"op": "ask_operator", "reason": "..."}

Devolvé SOLO JSON. Si son múltiples ops, array. Sin texto extra.
Ejemplo de output:
```json
[{"op": "add_zocalo", "sector_id": "cocina", "tramo_id": "tramo_2",
  "lado": "trasero", "ml": 0.5, "alto_m": 0.07}]
```
"""


async def extract_card_patch(msg: str, current_dr: dict) -> list[dict]:
    """Llama a Claude para extraer las operaciones de edición del texto libre.

    Si Claude devuelve `ask_operator`, el caller debe formular la pregunta.
    Si JSON parse falla o respuesta vacía → devuelve lista vacía (caller
    hace fallback a pregunta genérica).
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    # Context para el extractor: solo la estructura relevante del card.
    compact_state = {
        "sectores": [
            {
                "id": s.get("id", ""),
                "tipo": s.get("tipo", ""),
                "tramos": [
                    {
                        "id": t.get("id", ""),
                        "descripcion": t.get("descripcion", ""),
                        "largo_m": _num(t.get("largo_m")),
                        "ancho_m": _num(t.get("ancho_m")),
                        "zocalos": [
                            {"lado": z.get("lado", ""), "ml": z.get("ml", 0),
                             "alto_m": z.get("alto_m", 0)}
                            for z in t.get("zocalos", [])
                        ],
                    }
                    for t in s.get("tramos", [])
                ],
            }
            for s in current_dr.get("sectores", [])
        ],
    }
    user_text = (
        f"CARD ACTUAL:\n```json\n{json.dumps(compact_state, ensure_ascii=False, indent=2)}\n```\n\n"
        f"TEXTO DEL OPERADOR:\n```\n{msg}\n```\n\n"
        "Extraé las operaciones como array JSON."
    )
    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1500,
            system=_EXTRACTOR_SYSTEM,
            messages=[{"role": "user", "content": user_text}],
        )
    except Exception as e:
        logger.warning(f"[card-editor] LLM extract failed: {e}")
        return []

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text
    text = text.strip()
    # Strip markdown fences si las hay
    import re
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        ops = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"[card-editor] JSON parse failed: {e}; raw={text[:200]}")
        return []
    if isinstance(ops, dict):
        ops = [ops]
    if not isinstance(ops, list):
        return []
    return ops


def _num(field: Any) -> float:
    """Extrae el valor numérico de un FieldValue (dict con 'valor') o número crudo."""
    if isinstance(field, dict):
        return float(field.get("valor", 0) or 0)
    try:
        return float(field or 0)
    except (TypeError, ValueError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────
# 3) Aplicar patch al dict del dual_read_result
# ─────────────────────────────────────────────────────────────────────


def _find_sector(dr: dict, sector_id: str) -> dict | None:
    for s in dr.get("sectores", []):
        if s.get("id") == sector_id:
            return s
    # Fallback: single sector → devolver ese
    if len(dr.get("sectores", [])) == 1:
        return dr["sectores"][0]
    return None


def _find_tramo(sector: dict, tramo_id: str) -> dict | None:
    for t in sector.get("tramos", []):
        if t.get("id") == tramo_id:
            return t
    return None


def _find_zocalo(tramo: dict, lado: str) -> tuple[int, dict] | tuple[None, None]:
    for i, z in enumerate(tramo.get("zocalos", [])):
        if z.get("lado") == lado:
            return i, z
    return None, None


def apply_card_patch(dr: dict, ops: list[dict]) -> tuple[dict, list[str], list[str]]:
    """Aplica las operaciones al dict del dual_read_result.

    Retorna (dr_modificado, mensajes_aplicados, mensajes_de_error).
    Las operaciones inválidas se ignoran y se reportan en errores.
    """
    applied: list[str] = []
    errors: list[str] = []
    for op in ops:
        try:
            kind = op.get("op")
            if kind == "add_zocalo":
                s = _find_sector(dr, op.get("sector_id", ""))
                if not s:
                    errors.append(f"sector '{op.get('sector_id')}' no encontrado")
                    continue
                t = _find_tramo(s, op.get("tramo_id", ""))
                if not t:
                    errors.append(f"tramo '{op.get('tramo_id')}' no encontrado")
                    continue
                t.setdefault("zocalos", []).append({
                    "lado": op.get("lado", "trasero"),
                    "ml": float(op.get("ml", 0) or 0),
                    "alto_m": float(op.get("alto_m", 0.07) or 0.07),
                    "status": "CONFIRMADO",
                    "opus_ml": None,
                    "sonnet_ml": None,
                    "_manual": True,
                })
                applied.append(
                    f"agregué zócalo {op.get('lado')} {op.get('ml')}ml × {op.get('alto_m')}m en {t.get('id')}"
                )
            elif kind == "remove_zocalo":
                s = _find_sector(dr, op.get("sector_id", ""))
                if not s:
                    errors.append(f"sector '{op.get('sector_id')}' no encontrado")
                    continue
                t = _find_tramo(s, op.get("tramo_id", ""))
                if not t:
                    errors.append(f"tramo '{op.get('tramo_id')}' no encontrado")
                    continue
                idx, _ = _find_zocalo(t, op.get("lado", ""))
                if idx is None:
                    errors.append(f"zócalo {op.get('lado')} no existe en {t.get('id')}")
                    continue
                t["zocalos"].pop(idx)
                applied.append(f"removí zócalo {op.get('lado')} de {t.get('id')}")
            elif kind == "edit_zocalo_ml":
                s = _find_sector(dr, op.get("sector_id", ""))
                t = _find_tramo(s, op.get("tramo_id", "")) if s else None
                idx, z = _find_zocalo(t, op.get("lado", "")) if t else (None, None)
                if z is None:
                    errors.append(f"zócalo {op.get('lado')} no encontrado para editar ml")
                    continue
                z["ml"] = float(op.get("ml", 0) or 0)
                applied.append(f"edité zócalo {op.get('lado')} de {t.get('id')}: ml={z['ml']}")
            elif kind == "edit_zocalo_alto":
                s = _find_sector(dr, op.get("sector_id", ""))
                t = _find_tramo(s, op.get("tramo_id", "")) if s else None
                idx, z = _find_zocalo(t, op.get("lado", "")) if t else (None, None)
                if z is None:
                    errors.append(f"zócalo {op.get('lado')} no encontrado para editar alto")
                    continue
                z["alto_m"] = float(op.get("alto_m", 0) or 0)
                applied.append(
                    f"edité zócalo {op.get('lado')} de {t.get('id')}: alto={z['alto_m']}m"
                )
            elif kind == "add_tramo":
                s = _find_sector(dr, op.get("sector_id", ""))
                if not s:
                    errors.append(f"sector '{op.get('sector_id')}' no encontrado")
                    continue
                new_id = f"manual_{len(s.get('tramos', [])) + 1}"
                largo = float(op.get("largo_m", 0) or 0)
                ancho = float(op.get("ancho_m", 0.60) or 0.60)
                s.setdefault("tramos", []).append({
                    "id": new_id,
                    "descripcion": op.get("descripcion", f"Tramo adicional {new_id}"),
                    "largo_m": {"valor": largo, "status": "CONFIRMADO", "opus": None, "sonnet": None},
                    "ancho_m": {"valor": ancho, "status": "CONFIRMADO", "opus": None, "sonnet": None},
                    "m2": {"valor": round(largo * ancho, 2), "status": "CONFIRMADO", "opus": None, "sonnet": None},
                    "zocalos": [],
                    "frentin": [],
                    "regrueso": [],
                    "_manual": True,
                })
                applied.append(
                    f"agregué tramo '{op.get('descripcion', new_id)}' "
                    f"{largo}×{ancho} en sector {s.get('id')}"
                )
            elif kind == "remove_tramo":
                s = _find_sector(dr, op.get("sector_id", ""))
                if not s:
                    errors.append(f"sector '{op.get('sector_id')}' no encontrado")
                    continue
                tid = op.get("tramo_id", "")
                before = len(s.get("tramos", []))
                s["tramos"] = [t for t in s.get("tramos", []) if t.get("id") != tid]
                if len(s["tramos"]) == before:
                    errors.append(f"tramo '{tid}' no encontrado")
                    continue
                applied.append(f"removí tramo {tid} de sector {s.get('id')}")
            elif kind == "edit_tramo":
                s = _find_sector(dr, op.get("sector_id", ""))
                t = _find_tramo(s, op.get("tramo_id", "")) if s else None
                if t is None:
                    errors.append(f"tramo '{op.get('tramo_id')}' no encontrado")
                    continue
                field = op.get("field", "")
                value = float(op.get("value", 0) or 0)
                if field not in ("largo_m", "ancho_m", "m2"):
                    errors.append(f"field inválido: {field}")
                    continue
                t[field]["valor"] = value
                # Si cambió largo o ancho, recomputar m2 automático.
                if field in ("largo_m", "ancho_m") and "m2" in t:
                    lm = _num(t.get("largo_m"))
                    am = _num(t.get("ancho_m"))
                    t["m2"]["valor"] = round(lm * am, 2)
                applied.append(f"edité {t.get('id')}: {field}={value}")
            elif kind == "ask_operator":
                # El extractor pidió más info — no aplicamos, el caller lo usa
                # para formular la pregunta.
                errors.append(f"ask_operator: {op.get('reason', 'info faltante')}")
            else:
                errors.append(f"op desconocida: {kind}")
        except Exception as e:
            errors.append(f"error aplicando {op.get('op', '?')}: {e}")
    return dr, applied, errors


def format_patch_summary(applied: list[str], errors: list[str]) -> str:
    """Genera el mensaje textual que Valentina le devuelve al operador."""
    lines: list[str] = []
    if applied:
        lines.append("✅ Card actualizado:")
        for a in applied:
            lines.append(f"  • {a}")
    if errors:
        lines.append("⚠️ No pude aplicar:")
        for e in errors:
            lines.append(f"  • {e}")
        lines.append(
            "\nSi querés, aclaramelo con más detalle (ej: qué tramo, qué lado, "
            "largo y alto exactos)."
        )
    if not applied and not errors:
        lines.append(
            "No pude interpretar el cambio. ¿Podés detallar qué pieza "
            "(zócalo/mesada/sector) y qué medidas?"
        )
    return "\n".join(lines)
