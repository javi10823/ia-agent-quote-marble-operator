"""Observability helpers for the agent flow.

Scope (PR #385 — acordado con el operador):
    1. entrada HTTP del chat
    2. entrada de stream_chat
    3. mutaciones de quote_breakdown con diff + snapshot de keys críticas
    4. tool calls con input y output real
    5. helpers deterministas críticos (apply_answers, build_commercial_attrs,
       build_verified_context, build_derived_isla_pieces)
    6. endpoints reopen-measurements y reopen-context
    7. persistencia de messages
    8. SSE chunks estructurales (dual_read_result, action, done, context_analysis —
       no cada text chunk del stream)

Default: snapshots compactos + hashes + valores numéricos explícitos.
Full dump de payloads grandes bajo `DEBUG_AGENT_PAYLOADS=1`.

Regla del operador: "Si para entender el bug necesitás preguntarme qué
botón apreté y en qué orden, entonces primero faltan logs." Este módulo
existe para que no vuelva a pasar.

Uso:
    from app.modules.agent._trace import (
        log_http_enter, log_stream_enter, log_bd_mutation,
        log_tool_call, log_tool_result, log_helper_io,
        log_reopen, log_messages_persist, log_sse_structural,
    )
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger("agent.trace")


# ─────────────────────────────────────────────────────────────────────
# Toggle
# ─────────────────────────────────────────────────────────────────────


def _full_dump_enabled() -> bool:
    """`DEBUG_AGENT_PAYLOADS=1` → los helpers imprimen los payloads
    completos, no solo el fingerprint compacto. Se lee cada vez para
    que el operador pueda prenderlo en prod sin restart."""
    return os.getenv("DEBUG_AGENT_PAYLOADS", "0") == "1"


# ─────────────────────────────────────────────────────────────────────
# Fingerprints / snapshots
# ─────────────────────────────────────────────────────────────────────


def _fp(obj: Any) -> str:
    """Hash estable + largo para cualquier objeto serializable. Permite
    comparar dos snapshots sin imprimir el contenido entero."""
    try:
        blob = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = str(obj)
    h = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10]
    return f"sha={h} len={len(blob)}"


def _num(field: Any) -> float | None:
    """Extrae el valor numérico de un FieldValue (dict con 'valor') o
    número crudo. `None` si no se puede."""
    if isinstance(field, dict):
        v = field.get("valor")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    if field is None:
        return None
    try:
        return float(field)
    except (TypeError, ValueError):
        return None


def snapshot_dual_read(dr: dict | None) -> dict:
    """Snapshot compacto del dual_read / verified_measurements. Una línea
    por tramo con (sector_id, tramo_id, largo, ancho, m2).

    Lo que queda fuera del snapshot (pero está en el payload real): status
    per-field, opus/sonnet valores, zócalos, frentines, alzada, manual
    flags. Todo visible con `DEBUG_AGENT_PAYLOADS=1`.
    """
    if not dr:
        return {"sectores": 0, "dimensions": []}
    sectores = dr.get("sectores") or []
    dims = []
    for s in sectores:
        sid = s.get("id", "?")
        stype = s.get("tipo", "?")
        for t in s.get("tramos") or []:
            tid = t.get("id", "?")
            largo = _num(t.get("largo_m"))
            ancho = _num(t.get("ancho_m"))
            m2 = _num(t.get("m2"))
            dims.append({
                "sector": sid, "tipo": stype, "tramo": tid,
                "largo": largo, "ancho": ancho, "m2": m2,
            })
    return {
        "sectores": len(sectores),
        "tramos_total": len(dims),
        "dimensions": dims,
    }


def snapshot_commercial_attrs(attrs: dict | None) -> dict:
    """Extrae los campos clave + source de cada uno. El shape de
    `commercial_attrs` es `{field: {"value": ..., "source": ...}}`.
    """
    if not attrs:
        return {}
    keys = (
        "anafe_count", "pileta_simple_doble", "isla_presence",
        "isla_profundidad", "isla_patas", "isla_patas_alto",
        "colocacion", "alzada", "zocalos",
        "material", "localidad",
    )
    out = {}
    for k in keys:
        v = attrs.get(k)
        if isinstance(v, dict):
            out[k] = {"value": v.get("value"), "source": v.get("source")}
        elif v is not None:
            out[k] = {"value": v, "source": "?"}
    # Divergences si hay
    divs = attrs.get("divergences")
    if divs:
        out["_divergences"] = len(divs)
    return out


def snapshot_derived_pieces(pieces: list | None) -> list[dict]:
    """Resumen compacto de las piezas derivadas (patas de isla, etc.)."""
    if not pieces:
        return []
    return [
        {
            "descripcion": p.get("description") or p.get("descripcion"),
            "largo": p.get("largo"),
            "prof": p.get("prof"),
            "m2": p.get("m2"),
            "source": p.get("source"),
        }
        for p in pieces
    ]


# ─────────────────────────────────────────────────────────────────────
# Breakdown diff
# ─────────────────────────────────────────────────────────────────────

# Keys del breakdown que siempre imprimimos explícitamente cuando mutan
# (resto queda como "added"/"removed" sin valor).
_CRITICAL_BD_KEYS = (
    "verified_measurements", "verified_context", "verified_commercial_attrs",
    "verified_derived_pieces", "verified_context_analysis",
    "dual_read_result", "context_analysis_pending",
    "material_name", "total_ars", "total_usd",
)


def _critical_value_snapshot(key: str, value: Any) -> Any:
    """Para las keys críticas, devolver algo útil en lugar del blob."""
    if key in ("dual_read_result", "verified_measurements"):
        return snapshot_dual_read(value)
    if key == "verified_commercial_attrs":
        return snapshot_commercial_attrs(value)
    if key == "verified_derived_pieces":
        return snapshot_derived_pieces(value)
    if key == "verified_context":
        # Texto grande — solo fingerprint.
        return _fp(value)
    if key == "context_analysis_pending":
        return {
            "data_known": len((value or {}).get("data_known") or []),
            "pending_questions": len((value or {}).get("pending_questions") or []),
        }
    if key == "verified_context_analysis":
        return {"answers": len((value or {}).get("answers") or [])}
    return value  # primitives: total_ars, total_usd, material_name


def diff_breakdown(pre: dict | None, post: dict | None) -> dict:
    """Computa qué cambió entre dos breakdowns. Retorna:
        {
            "added":    [list of keys nuevas],
            "removed":  [list of keys borradas],
            "modified": {key: {"before": ..., "after": ...}, ...}
        }
    Para las keys críticas el before/after es un snapshot. Para las demás
    es un fingerprint (para no inflar logs).
    """
    pre = pre or {}
    post = post or {}
    pre_keys = set(pre.keys())
    post_keys = set(post.keys())
    added = sorted(post_keys - pre_keys)
    removed = sorted(pre_keys - post_keys)
    modified = {}
    for k in sorted(pre_keys & post_keys):
        if pre[k] != post[k]:
            if k in _CRITICAL_BD_KEYS:
                modified[k] = {
                    "before": _critical_value_snapshot(k, pre[k]),
                    "after": _critical_value_snapshot(k, post[k]),
                }
            else:
                modified[k] = {"before_fp": _fp(pre[k]), "after_fp": _fp(post[k])}
    return {"added": added, "removed": removed, "modified": modified}


# ─────────────────────────────────────────────────────────────────────
# Log helpers — entrypoints del flow
# ─────────────────────────────────────────────────────────────────────


def log_http_enter(quote_id: str, endpoint: str, **kwargs) -> None:
    """Request HTTP entrante al agente (chat, reopen-*, rehydrate-*)."""
    parts = [f"{k}={v}" for k, v in kwargs.items()]
    logger.info(f"[trace:http:{quote_id}] {endpoint} {' '.join(parts)}")


def log_stream_enter(
    quote_id: str,
    user_message: str | None,
    plan_bytes: bytes | None,
    extra_files: list | None,
    bd_pre: dict | None,
) -> None:
    """Entrada del loop agéntico: lo que recibe, el estado del breakdown
    al arrancar (qué confirmaciones ya tiene)."""
    msg_preview = (user_message or "")[:200].replace("\n", " ")
    bd = bd_pre or {}
    bd_state = {
        "has_dual_read_result": bool(bd.get("dual_read_result")),
        "has_verified_context": bool(bd.get("verified_context")),
        "has_verified_context_analysis": bool(bd.get("verified_context_analysis")),
        "has_context_analysis_pending": bool(bd.get("context_analysis_pending")),
        "has_verified_measurements": bool(bd.get("verified_measurements")),
        "has_verified_derived_pieces": bool(bd.get("verified_derived_pieces")),
        "material_name": bd.get("material_name"),
        "total_ars": bd.get("total_ars"),
    }
    logger.info(
        f"[trace:stream:{quote_id}] enter "
        f"msg={msg_preview!r} "
        f"plan_bytes={len(plan_bytes) if plan_bytes else 0} "
        f"extra_files={len(extra_files or [])} "
        f"bd_state={bd_state}"
    )


# ─────────────────────────────────────────────────────────────────────
# Log helpers — mutación de DB
# ─────────────────────────────────────────────────────────────────────


def log_bd_mutation(
    quote_id: str,
    flow: str,
    pre: dict | None,
    post: dict | None,
) -> None:
    """Diff explícito del breakdown entre pre/post. Sin diff → no log.

    `flow` es un handle para ubicar la mutación en el código:
    `context-confirmed`, `dual-read-confirmed`, `card-editor`,
    `calculate-quote`, `reopen-measurements`, `reopen-context`, etc.
    """
    diff = diff_breakdown(pre, post)
    if not diff["added"] and not diff["removed"] and not diff["modified"]:
        return
    logger.info(
        f"[trace:bd-mutation:{quote_id}] flow={flow} "
        f"added={diff['added']} removed={diff['removed']} "
        f"modified_keys={list(diff['modified'].keys())}"
    )
    for k, change in diff["modified"].items():
        logger.info(f"[trace:bd-mutation:{quote_id}]   {k}: {change}")
    if _full_dump_enabled():
        logger.info(
            f"[trace:bd-mutation:{quote_id}] FULL pre={pre} post={post}"
        )


def log_messages_persist(
    quote_id: str,
    *,
    flow: str,
    added_turns: list[dict],
    total_count: int,
) -> None:
    """Cada vez que el backend persiste turns nuevos en `Quote.messages`."""
    previews = [
        {
            "role": t.get("role"),
            "content_fp": _fp(t.get("content")),
            "content_preview": (
                _content_preview(t.get("content"))
            ),
        }
        for t in added_turns
    ]
    logger.info(
        f"[trace:messages-persist:{quote_id}] flow={flow} "
        f"added={len(added_turns)} total={total_count}"
    )
    for p in previews:
        logger.info(
            f"[trace:messages-persist:{quote_id}]   "
            f"role={p['role']} fp={p['content_fp']} preview={p['content_preview']!r}"
        )


def _content_preview(content: Any) -> str:
    """Primer texto útil del content (str o list de blocks). Max 120 chars."""
    if isinstance(content, str):
        return content[:120]
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return (block.get("text") or "")[:120]
    return ""


# ─────────────────────────────────────────────────────────────────────
# Log helpers — SSE estructural
# ─────────────────────────────────────────────────────────────────────


# Los tipos de chunk SSE que queremos loguear. NO logueamos "text"
# (stream char-by-char de Valentina) porque floodearía.
_STRUCTURAL_SSE = {
    "dual_read_result", "context_analysis", "zone_selector",
    "action", "done", "error", "image_tool",
}


def log_sse_structural(quote_id: str, event_type: str, content: Any) -> None:
    """Log para eventos SSE estructurales (cards emitidas, done, error).
    El `text` chunk del stream NO pasa por acá — sería ruido."""
    if event_type not in _STRUCTURAL_SSE:
        return
    if event_type == "dual_read_result" and isinstance(content, str):
        try:
            parsed = json.loads(content)
            snap = snapshot_dual_read(parsed)
            logger.info(
                f"[trace:sse:{quote_id}] type={event_type} "
                f"snap={snap} fp={_fp(content)}"
            )
            return
        except (json.JSONDecodeError, ValueError):
            pass
    preview = (content if isinstance(content, str) else str(content))[:120]
    logger.info(
        f"[trace:sse:{quote_id}] type={event_type} preview={preview!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# Log helpers — tool I/O
# ─────────────────────────────────────────────────────────────────────


def log_tool_call(quote_id: str, tool_name: str, tool_input: Any) -> None:
    """Tool call — se loguea el input completo (hasta 2000 chars).
    Ya existía parcial en agent.py; acá lo centralizamos."""
    try:
        blob = json.dumps(tool_input, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        blob = str(tool_input)
    logger.info(
        f"[trace:tool-call:{quote_id}] {tool_name} input={blob[:2000]}"
    )


def log_tool_result(
    quote_id: str,
    tool_name: str,
    result: Any,
) -> None:
    """Tool result — loguea el output REAL (antes agent.py solo imprimía
    un subset de keys `ok/total_ars/...` → aparecía `{}` cuando el tool
    devolvía catálogos o estructuras).
    """
    # Dict → imprimir keys + valores primitivos + fingerprint de valores complejos
    if isinstance(result, dict):
        flat = {}
        for k, v in result.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                flat[k] = v
            else:
                flat[k] = _fp(v)
        logger.info(
            f"[trace:tool-result:{quote_id}] {tool_name} keys={list(result.keys())} "
            f"summary={flat}"
        )
        if _full_dump_enabled():
            try:
                blob = json.dumps(result, ensure_ascii=False, default=str)
                logger.info(
                    f"[trace:tool-result:{quote_id}] {tool_name} FULL={blob[:10000]}"
                )
            except (TypeError, ValueError):
                pass
    elif isinstance(result, list):
        logger.info(
            f"[trace:tool-result:{quote_id}] {tool_name} "
            f"list_len={len(result)} fp={_fp(result)}"
        )
    else:
        logger.info(
            f"[trace:tool-result:{quote_id}] {tool_name} "
            f"value={str(result)[:500]}"
        )


# ─────────────────────────────────────────────────────────────────────
# Log helpers — helpers deterministas críticos
# ─────────────────────────────────────────────────────────────────────


def log_apply_answers(
    quote_id: str,
    *,
    flow: str,
    dual_before: dict | None,
    dual_after: dict | None,
    answers: list | None,
) -> None:
    """`apply_answers(dual_result, answers)` — muestra qué respuesta
    (id+value) se aplicó y cómo cambió el dual_read."""
    answers = answers or []
    logger.info(
        f"[trace:apply-answers:{quote_id}] flow={flow} "
        f"answers_count={len(answers)}"
    )
    for a in answers:
        logger.info(
            f"[trace:apply-answers:{quote_id}]   "
            f"id={a.get('id')} value={a.get('value')} label={a.get('label')}"
        )
    before_snap = snapshot_dual_read(dual_before)
    after_snap = snapshot_dual_read(dual_after)
    if before_snap != after_snap:
        logger.info(
            f"[trace:apply-answers:{quote_id}] dual_read changed — "
            f"tramos before={before_snap['tramos_total']} "
            f"after={after_snap['tramos_total']}"
        )


def log_build_commercial_attrs(
    quote_id: str,
    *,
    flow: str,
    result: dict,
) -> None:
    """Output de `build_commercial_attrs` — los campos con su source."""
    snap = snapshot_commercial_attrs(result)
    logger.info(
        f"[trace:commercial-attrs:{quote_id}] flow={flow} attrs={snap}"
    )


def log_build_derived_isla_pieces(
    quote_id: str,
    *,
    flow: str,
    pieces: list,
    warnings: list,
) -> None:
    """Output de `build_derived_isla_pieces` — piezas + warnings."""
    snap = snapshot_derived_pieces(pieces)
    logger.info(
        f"[trace:derived-pieces:{quote_id}] flow={flow} "
        f"count={len(pieces or [])} pieces={snap}"
    )
    for w in warnings or []:
        logger.info(f"[trace:derived-pieces:{quote_id}] warning: {w}")


def log_build_verified_context(
    quote_id: str,
    *,
    flow: str,
    text: str,
) -> None:
    """Output de `build_verified_context` — fingerprint del texto inyectado
    en el system prompt. Full dump con `DEBUG_AGENT_PAYLOADS=1`."""
    logger.info(
        f"[trace:verified-context:{quote_id}] flow={flow} "
        f"chars={len(text or '')} fp={_fp(text)}"
    )
    if _full_dump_enabled():
        logger.info(f"[trace:verified-context:{quote_id}] FULL=\n{text}")


# ─────────────────────────────────────────────────────────────────────
# Log helpers — endpoints reopen
# ─────────────────────────────────────────────────────────────────────


def log_reopen(
    quote_id: str,
    *,
    kind: str,  # "measurements" | "context"
    bd_pre: dict | None,
    bd_post: dict | None,
    msgs_count_pre: int,
    msgs_count_post: int,
    truncate_matched: bool,
) -> None:
    """Snapshot completo del reopen. Para cada endpoint vemos:
    - Qué había en el breakdown pre-reset (incluyendo verified_measurements).
    - Qué quedó post-reset (incluyendo el nuevo dual_read_result).
    - Cuántos turns se eliminaron del chat.
    - Si el truncate encontró la card o no (clave: si un quote legacy no
      tiene el marker `__DUAL_READ__` en DB, el corte no pasa).
    """
    diff = diff_breakdown(bd_pre, bd_post)
    logger.info(
        f"[trace:reopen:{quote_id}] kind={kind} "
        f"msgs={msgs_count_pre}→{msgs_count_post} "
        f"truncate_matched={truncate_matched}"
    )
    logger.info(
        f"[trace:reopen:{quote_id}] breakdown "
        f"added={diff['added']} removed={diff['removed']} "
        f"modified={list(diff['modified'].keys())}"
    )
    for k, change in diff["modified"].items():
        logger.info(f"[trace:reopen:{quote_id}]   {k}: {change}")
