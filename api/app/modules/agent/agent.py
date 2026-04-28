import anthropic
import asyncio
import json
import base64
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select

from app.core.config import settings
from app.models.quote import Quote, QuoteStatus
from app.modules.agent.tools.catalog_tool import catalog_lookup, catalog_batch_lookup, check_stock, check_architect, get_ai_config
from app.modules.agent.tools.plan_tool import read_plan, save_plan_to_temp
from app.modules.agent.tools.document_tool import generate_documents
from app.modules.agent.tools.drive_tool import upload_to_drive
from app.modules.quote_engine.calculator import calculate_quote, list_pieces
from app.modules.agent.tools.validation_tool import validate_despiece

BASE_DIR = Path(__file__).parent.parent.parent.parent

# Materials that MUST have merma
from app.core.company_config import get as _cfg
_SYNTHETIC_MATERIALS = _cfg("materials.sinteticos", ["silestone", "dekton", "neolith", "puraprima", "purastone", "laminatto"])


def _validate_quote_data(qdata: dict) -> tuple[list[str], list[str]]:
    """Pre-flight checklist before PDF generation. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # ── Errors (block generation) ──
    if not qdata.get("client_name"):
        errors.append("Falta nombre del cliente")
    if not qdata.get("material_name"):
        errors.append("Falta material")
    # PR #36 — también reemplazar valores "vagos" como 'A confirmar',
    # 'A CONVENIR', 'N/A', '-' con el plazo del config. Antes solo se
    # reemplazaba cuando estaba vacío, pero el LLM a veces pasaba
    # 'A confirmar' cuando no estaba seguro → terminaba en el PDF.
    _VAGUE_DELIVERY = {"", "a confirmar", "a convenir", "n/a", "n/d", "-", "—", "."}
    _current_delivery = (qdata.get("delivery_days") or "").strip()
    if _current_delivery.lower() in _VAGUE_DELIVERY:
        try:
            _cfg_raw = json.loads((BASE_DIR / "catalog" / "config.json").read_text(encoding="utf-8"))
            qdata["delivery_days"] = _cfg_raw.get("delivery_days", {}).get("display", "30 dias desde la toma de medidas")
        except Exception:
            qdata["delivery_days"] = "30 dias desde la toma de medidas"
    if not qdata.get("total_ars") and not qdata.get("total_usd"):
        errors.append("Totales en $0 — verificar cálculo")
    sectors = qdata.get("sectors", [])
    if not sectors or not any(s.get("pieces") for s in sectors):
        errors.append("Sin piezas definidas")
    if not qdata.get("mo_items"):
        errors.append("Sin ítems de mano de obra")

    # ── Warnings (alert but allow) ──
    mat = (qdata.get("material_name") or "").lower()
    merma = qdata.get("merma") or {}

    # Negro Brasil NEVER has merma
    if "negro brasil" in mat and merma.get("aplica"):
        warnings.append("Negro Brasil NUNCA lleva merma — verificar")

    # Synthetic materials SHOULD have merma
    if any(s in mat for s in _SYNTHETIC_MATERIALS) and not merma.get("aplica"):
        warnings.append(f"Material sintético ({qdata.get('material_name')}) debería llevar merma")

    # MO items with $0 price
    for mo in qdata.get("mo_items", []):
        if mo.get("unit_price", 0) == 0 and mo.get("description"):
            warnings.append(f"MO ítem '{mo['description']}' tiene precio $0")

    # Check if pileta was likely requested but missing from MO
    mo_descriptions = " ".join(m.get("description", "").lower() for m in qdata.get("mo_items", []))
    sinks = qdata.get("sinks", [])
    has_pileta_in_quote = (
        "pileta" in mo_descriptions or "pegado" in mo_descriptions
        or "johnson" in mo_descriptions or len(sinks) > 0
    )
    if not has_pileta_in_quote:
        warnings.append("No hay pileta/bacha en el presupuesto — verificar si el operador la pidió")

    return errors, warnings


def _validate_plan_pieces(pieces: list[dict]) -> list[str]:
    """PR #25 — validar piezas de list_pieces cuando hay plano adjunto.

    Enforza tipado + coherencia dimensional para evitar los errores típicos
    de lectura de planos:
    - confundir vista en elevación de mesada con pieza de material aparte
    - confundir zócalo con mesada chica
    - confundir alzada con zócalo alto

    PR #54: hard gate adicional contra drift del modelo — si Valentina agrega
    zócalos con alto=0.05 exacto (default silencioso sin leer plano ni
    preguntar al operador), bloquear con error explícito. Ver rules/
    plan-reading.md §REGLA — ZÓCALOS AMBIGUOS.

    Retorna lista de mensajes de error; vacía si todo OK.
    Gated a has_plan en el caller — briefs de texto puro NO pasan por acá.
    """
    errors: list[str] = []
    if not isinstance(pieces, list) or not pieces:
        return errors

    has_any_zocalo = False
    zocalo_altos: list[float] = []
    for idx, p in enumerate(pieces):
        if not isinstance(p, dict):
            errors.append(f"Pieza #{idx}: formato inválido")
            continue
        desc = p.get("description", f"pieza #{idx}")
        tipo = (p.get("tipo") or "").strip().lower()
        largo = p.get("largo") or 0
        prof = p.get("prof") or 0
        alto = p.get("alto") or 0

        if not tipo:
            errors.append(
                f"'{desc}': falta el campo `tipo` (mesada/zocalo/alzada/frentin). "
                "Cuando hay plano adjunto el tipo es obligatorio."
            )
            continue

        if tipo == "mesada":
            if prof and prof < 0.30:
                errors.append(
                    f"'{desc}' marcada como mesada pero prof={prof} < 0.30 m. "
                    "Puede ser un zócalo mal tipado — releer el plano."
                )
            if alto and alto > 0.15:
                errors.append(
                    f"'{desc}' marcada como mesada pero alto={alto} > 0.15 m "
                    "(una mesada no tiene campo `alto`, solo prof)."
                )
        elif tipo == "zocalo":
            has_any_zocalo = True
            if alto:
                zocalo_altos.append(float(alto))
            if not alto:
                errors.append(
                    f"'{desc}' marcada como zócalo pero falta `alto`. "
                    "Un zócalo se mide como largo (ml) × alto."
                )
            elif alto > 0.60:
                # PR #42 — límite subido de 0.15 a 0.60. Existen zócalos
                # tipo splashback de hasta 50 cm (baños penitenciarios,
                # lavaderos industriales). Solo rechazar si > 60 cm (ahí
                # sí es alzada o revestimiento, no zócalo).
                errors.append(
                    f"'{desc}' marcada como zócalo pero alto={alto} > 0.60 m. "
                    "Ese alto ya corresponde a alzada/revestimiento, no a zócalo."
                )
            if prof and prof >= 0.30:
                errors.append(
                    f"'{desc}' marcada como zócalo pero prof={prof} ≥ 0.30 m. "
                    "Un zócalo no tiene profundidad — releer el plano."
                )
        elif tipo == "alzada":
            if alto and alto < 0.30:
                errors.append(
                    f"'{desc}' marcada como alzada pero alto={alto} < 0.30 m. "
                    "Una alzada es una pieza vertical de material (≥ 30 cm)."
                )
        elif tipo == "frentin":
            if alto and alto > 0.30:
                errors.append(
                    f"'{desc}' marcada como frentín pero alto={alto} > 0.30 m. "
                    "Un frentín típico tiene 5–15 cm. Si es más alto, revisar."
                )
        else:
            errors.append(
                f"'{desc}': tipo '{tipo}' inválido. "
                "Válidos: mesada, zocalo, alzada, frentin."
            )

    # PR #54 — Hard gate contra drift del prompt: si TODOS los zócalos tienen
    # alto=0.05 exacto (default silencioso), asumimos que Valentina no leyó
    # el alto del plano ni preguntó al operador. Bloquear y forzar
    # re-lectura/pregunta.
    #
    # El default 5cm solo es legítimo cuando:
    #   - el plano no muestra NINGÚN alto y
    #   - el operador lo confirmó explícitamente
    # Como el validator no puede saber si preguntó, adoptamos la regla
    # conservadora: "alto=0.05 exacto en ≥1 zócalo y plano adjunto" ⇒ error.
    # Para los casos legítimos, Valentina puede pasar un alto ligeramente
    # distinto (ej: 0.050 con 3+ decimales es el valor real, no el default)
    # o actualizar tras confirmación del operador.
    if zocalo_altos and all(round(a, 4) == 0.05 for a in zocalo_altos):
        errors.append(
            "⛔ ZÓCALOS CON ALTO=0.05 (DEFAULT). El plano no mostró el alto "
            "explícito (leyenda H=Xcm, cota 0.05-0.50m en borde, o rotulado) "
            "y no registrás haber preguntado al operador. Antes de seguir: "
            "(1) releer el plano buscando H=Xcm / cotas de alto en bordes; "
            "(2) si no hay, PREGUNTAR al operador '¿Lleva zócalos? Alto y "
            "contra qué paredes'. Una vez confirmado, re-emitir con ese valor. "
            "Ver rules/plan-reading.md §REGLA — ZÓCALOS AMBIGUOS."
        )

    return errors


async def _run_dual_read(
    db,
    quote_id: str,
    draw_bytes: bytes,
    *,
    crop_label: str = "plano",
    planilla_m2: float | None = None,
    cotas_text: str | None = None,
    extracted_cota_values: list[float] | None = None,
    extracted_cotas: list | None = None,  # list[Cota] — optional full objects for multi-crop
    user_message: str = "",
    plan_filename: str = "",
    plan_hash: str | None = None,
) -> tuple[bool, list[dict]]:
    """PR #55 — Corre dual_read sobre cualquier plano y devuelve chunks SSE.

    Antes: dual_read solo corría cuando había tabla de Planilla de Cómputo
    parseada (_planilla_data con table_x0 > 0). Imágenes sueltas y PDFs sin
    planilla se saltaban la card → operador perdía la verificación visual
    del Opus+Sonnet en la mayoría de casos residenciales.

    Esta helper centraliza el flujo para llamarse desde los 3 paths:
    (1) planilla PDF, (2) imagen suelta, (3) PDF sin planilla.

    Args:
        draw_bytes: bytes JPEG del plano a analizar. El caller debe
            rasterizar/convertir PNG/WebP/PDF antes de llamar.
        crop_label: etiqueta para el crop (ubicación de planilla si existe,
            sino "plano" / "cocina").
        planilla_m2: m² declarado por planilla si existe. None si no.
        cotas_text: texto de cotas pre-extraído del PDF (si aplica).

    Returns:
        (handled, chunks) donde:
            handled=True → el caller debe yield los chunks y return (turn done)
            handled=False → el caller sigue el flujo normal (Claude)
    """
    import json as _json
    import hashlib as _hashlib
    chunks: list[dict] = []

    # PR #63 + #64 — dedup hash-based. El plan_bytes persiste entre turnos
    # (frontend lo re-envía con cada mensaje mientras la conversación tenga
    # un plano adjunto). Sin dedup, cada turno que el operador responda en
    # chat re-corre dual_read → card aparece N veces.
    #
    # PR #64: el hash debe computarse sobre los BYTES CRUDOS del plano
    # (plan_bytes que subió el operador), NO sobre draw_bytes (rasterizado
    # + re-encoded JPEG). Estas transformaciones pueden ser NO
    # deterministas (PIL quality, pdf2image, crop offset), y el hash
    # cambiaba turno a turno → cache miss → card re-aparece.
    #
    # Los callers pasan plan_hash computado sobre plan_bytes crudo. Si no
    # lo pasan, fallback a hashear draw_bytes (comportamiento PR #63).
    #
    # Lógica:
    #   1. Si existe dual_read_plan_hash en breakdown y coincide → SAME PLAN:
    #        - Si hay verified_context → operador ya confirmó, skip.
    #        - Si hay dual_read_result → re-emit (SSE retry / reload).
    #        - Sino → skip (dual_read corrió antes, estamos en follow-up).
    #   2. Si el hash cambió (o no existe) → NEW PLAN:
    #        - Limpiar state stale.
    #        - Correr dual_read fresh.
    #        - Guardar hash nuevo.
    _plan_hash = plan_hash or _hashlib.sha256(draw_bytes).hexdigest()[:16]
    try:
        _dr_check_q = await db.execute(select(Quote).where(Quote.id == quote_id))
        _dr_check_quote = _dr_check_q.scalar_one_or_none()
        _dr_bd = (_dr_check_quote.quote_breakdown or {}) if _dr_check_quote else {}
        _stored_hash = _dr_bd.get("dual_read_plan_hash")
        _same_plan = _stored_hash == _plan_hash
        _existing_dr = _dr_bd.get("dual_read_result")
        _already_confirmed = bool(
            _dr_bd.get("verified_context") or _dr_bd.get("measurements_confirmed")
        )
    except Exception:
        _dr_bd = {}
        _stored_hash = None
        _same_plan = False
        _existing_dr = None
        _already_confirmed = False

    # Case 1: same plan + already confirmed → follow-up chat, no card.
    if _same_plan and _already_confirmed:
        logging.info(
            f"[dual-read] skip (same plan, already confirmed) for {quote_id} "
            f"hash={_plan_hash}"
        )
        return (False, chunks)

    # Case 1b (PR #66) — compat retroactivo: quotes viejos que confirmaron
    # medidas ANTES de que existiera el hash no tienen `dual_read_plan_hash`
    # en breakdown. En esos casos, si ya hay verified_context, tratamos como
    # "mismo plano" porque esa es la intención — el operador ya verificó.
    # Guardamos el hash ahora para convertir el quote legacy a nuevo esquema.
    if _stored_hash is None and _already_confirmed:
        logging.info(
            f"[dual-read] legacy quote {quote_id} without hash + already "
            "confirmed → skip + backfill hash."
        )
        try:
            _bd_backfill = dict(_dr_bd)
            _bd_backfill["dual_read_plan_hash"] = _plan_hash
            await db.execute(
                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd_backfill)
            )
            await db.commit()
        except Exception as _e_bf:
            logging.warning(f"[dual-read] Failed to backfill hash: {_e_bf}")
        return (False, chunks)

    # Case 2: same plan + we have a dual_read_result → SSE retry or reload.
    # Re-emit from DB instead of calling the API again.
    _has_valid_existing = (
        _same_plan and bool(_existing_dr) and not _existing_dr.get("error")
    )
    if _has_valid_existing:
        # Re-emit saved card + persist turn
        logging.info(f"[dual-read] re-emit saved result for quote {quote_id}")
        try:
            _um_q = await db.execute(select(Quote).where(Quote.id == quote_id))
            _um_quote = _um_q.scalar_one_or_none()
            if _um_quote:
                _user_entry = {
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": (user_message or "").strip() or f"(adjuntó plano: {plan_filename})",
                    }],
                }
                # PR #379 — Persistir el JSON real de la card (no un marker
                # vacío). El frontend ya sabe renderizar `__DUAL_READ__<json>`
                # como card. Así al reabrir el quote el chat reconstruye el
                # estado real — no quedan placeholders crudos `_SHOWN_`.
                _asst_entry = {
                    "role": "assistant",
                    "content": f"__DUAL_READ__{_json.dumps(_existing_dr, ensure_ascii=False)}",
                }
                await db.execute(
                    update(Quote)
                    .where(Quote.id == quote_id)
                    .values(messages=list(_um_quote.messages or []) + [_user_entry, _asst_entry])
                )
                await db.commit()
        except Exception as _e:
            logging.warning(f"[dual-read] Failed to persist turn: {_e}")
        chunks.append({"type": "dual_read_result", "content": _json.dumps(_existing_dr, ensure_ascii=False)})
        chunks.append({"type": "done", "content": ""})
        return (True, chunks)

    # Case 3: new plan (hash differs or no previous hash) → fresh run.
    # Si había state stale de un plano previo (Paso 2, verified_context de
    # un upload anterior), lo limpiamos ANTES del fresh run.
    if _stored_hash and not _same_plan:
        logging.info(
            f"[dual-read] New plan upload on quote {quote_id} "
            f"(old hash={_stored_hash}, new hash={_plan_hash}) — clearing stale state."
        )
        try:
            _bd_cleaned = dict(_dr_bd)
            for _stale in (
                "verified_context", "verified_measurements", "measurements_confirmed",
                "dual_read_result", "material_name", "material_m2",
                "material_price_unit", "material_currency", "discount_amount",
                "discount_pct", "total_ars", "total_usd", "mo_items", "sectors",
                "sinks", "piece_details", "mo_discount_amount", "mo_discount_pct",
                "total_mo_ars", "sobrante_m2", "sobrante_total", "paso1_pieces",
                "paso1_total_m2",
            ):
                _bd_cleaned.pop(_stale, None)
            await db.execute(
                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd_cleaned)
            )
            await db.commit()
        except Exception as _e_clean:
            logging.warning(f"[dual-read] Failed to clean stale state: {_e_clean}")

    try:
        from app.modules.quote_engine.dual_reader import dual_read_crop
        _dual_enabled = get_ai_config().get("dual_read_enabled", True)
        _multi_crop_enabled = get_ai_config().get("multi_crop_enabled", False)
        chunks.append({"type": "action", "content": "📐 Leyendo medidas del plano..."})

        _dual_result = None
        # Multi-crop path (fase 1: topología global + fase 2: medidas por región).
        # Feature flag apagado por default; cuando se enciende, cae al pipeline
        # legacy si la fase global falla (sin resultado o timeout).
        if _multi_crop_enabled:
            try:
                from app.modules.quote_engine.multi_crop_reader import read_plan_multi_crop
                _multi_result = await read_plan_multi_crop(
                    draw_bytes,
                    cotas=extracted_cotas or [],
                    brief_text=user_message,
                    plan_hash=_plan_hash,
                    quote_id=quote_id,
                    db=db,
                )
                if not _multi_result.get("error"):
                    _dual_result = _multi_result
                    logging.info(f"[multi-crop] used multi_crop pipeline, source={_multi_result.get('source')}")
                else:
                    logging.warning(
                        f"[multi-crop] failed ({_multi_result.get('error')}) — "
                        "fallback to legacy dual_read pipeline"
                    )
            except Exception as _e_mc:
                logging.warning(f"[multi-crop] exception ({_e_mc}) — fallback to legacy")

        # Legacy dual_read path (Sonnet + Opus fallback), usado cuando
        # multi-crop está off o devolvió error.
        if _dual_result is None:
            _dual_result = await dual_read_crop(
                draw_bytes,
                crop_label=crop_label,
                planilla_m2=planilla_m2,
                dual_enabled=_dual_enabled,
                cotas_text=cotas_text,
                brief_text=user_message,
            )
        if _dual_result.get("error"):
            logging.warning(f"[dual-read] Error: {_dual_result.get('error')}")
            return (False, chunks)

        # Anchor validator — rechaza medidas que el VLM emitió sin respaldo
        # en el text layer del PDF. Caso Bernardi: "1.75" y "2.35" inventados
        # (no existen en las cotas extraídas con pdfplumber). Quedan marcadas
        # UNANCHORED y el operador las corrige con dbl-click en la card.
        if extracted_cota_values:
            try:
                from app.modules.quote_engine.plan_anchor_validator import annotate_anchoring
                annotate_anchoring(_dual_result, extracted_cota_values)
                _un = sum(
                    1 for s in _dual_result.get("sectores") or []
                    for t in s.get("tramos") or []
                    for f in ("largo_m", "ancho_m")
                    if (t.get(f) or {}).get("status") == "UNANCHORED"
                )
                if _un:
                    logging.info(
                        f"[dual-read] anchor validator flagged {_un} unanchored "
                        f"fields ({len(extracted_cota_values)} cotas in text layer)"
                    )
            except Exception as _e_av:
                logging.warning(f"[dual-read] anchor validator failed (non-fatal): {_e_av}")

        # Pending questions — "preguntar antes de asumir". Si el brief no
        # menciona zócalos (u otros datos) y el plano tampoco los aclara,
        # emitimos preguntas que bloquean el Confirmar hasta que el operador
        # responda. Evita que Valentina asuma defaults silenciosos.
        try:
            from app.modules.quote_engine.pending_questions import detect_pending_questions
            # Cargamos snapshot del quote para que los detectores de campos
            # obligatorios (material, localidad) puedan ver datos ya salvos.
            _quote_snapshot = None
            try:
                _pq_q = await db.execute(select(Quote).where(Quote.id == quote_id))
                _pq_quote = _pq_q.scalar_one_or_none()
                if _pq_quote:
                    _quote_snapshot = {
                        "material": _pq_quote.material,
                        "localidad": _pq_quote.localidad,
                        "client_name": _pq_quote.client_name,
                        "project": _pq_quote.project,
                    }
            except Exception:
                pass
            _pending = detect_pending_questions(user_message or "", _dual_result, quote=_quote_snapshot)
            if _pending:
                _dual_result["pending_questions"] = _pending
                logging.info(
                    f"[dual-read] {len(_pending)} pending question(s): "
                    f"{[q['id'] for q in _pending]}"
                )
        except Exception as _e_pq:
            logging.warning(f"[dual-read] pending_questions detection failed (non-fatal): {_e_pq}")

        # Save crop for Opus retry
        try:
            from app.core.static import OUTPUT_DIR as _OUT
            _crop_dir = _OUT / quote_id
            _crop_dir.mkdir(parents=True, exist_ok=True)
            _crop_path = _crop_dir / "dual_read_crop.jpg"
            _crop_path.write_bytes(draw_bytes)
            _dual_result["_crop_path"] = str(_crop_path)
        except Exception as e:
            logging.warning(f"[dual-read] Failed to save crop: {e}")

        # PR G — gate: antes de emitir el dual_read_result al frontend,
        # chequeamos si tenemos "context confirmado". Si NO hay
        # verified_context_analysis guardado en el breakdown, primero
        # emitimos un chunk `context_analysis` (la card de análisis previa)
        # y guardamos el dual_read_result en DB para levantarlo cuando el
        # operador confirme el contexto.
        _context_already_confirmed = False
        _ck_quote = None
        _ck_bd: dict = {}
        try:
            _ck_q = await db.execute(select(Quote).where(Quote.id == quote_id))
            _ck_quote = _ck_q.scalar_one_or_none()
            _ck_bd = (_ck_quote.quote_breakdown or {}) if _ck_quote else {}
            _context_already_confirmed = bool(_ck_bd.get("verified_context_analysis"))
        except Exception as _e_ctx_q:
            logging.warning(f"[context-analysis] quote lookup failed: {_e_ctx_q}")

        if not _context_already_confirmed:
            # Construir y emitir context_analysis
            try:
                from app.modules.quote_engine.context_analyzer import build_context_analysis
                from app.modules.agent.tools.catalog_tool import get_ai_config as _get_ai
                _cfg_defaults = {
                    "default_zocalo_height": (_get_ai() or {}).get("default_zocalo_height", 0.07),
                    "default_payment": "Contado",
                    "default_delivery_days": "30 días",
                }
                _ctx_quote = {
                    "client_name": _ck_quote.client_name if _ck_quote else None,
                    "project": _ck_quote.project if _ck_quote else None,
                    "material": _ck_quote.material if _ck_quote else None,
                    "localidad": _ck_quote.localidad if _ck_quote else None,
                    "is_building": _ck_quote.is_building if _ck_quote else False,
                } if _ck_quote else None
                _context = await build_context_analysis(
                    user_message or "", _ctx_quote, _dual_result, _cfg_defaults
                )
                # Persistimos el dual_read_result en DB (para levantarlo al
                # confirmar contexto) pero NO lo emitimos aún al frontend.
                try:
                    _bd2 = dict(_ck_bd)
                    _bd2["dual_read_result"] = _dual_result
                    _bd2["dual_read_plan_hash"] = _plan_hash
                    _bd2["dual_read_planilla_m2"] = planilla_m2
                    _bd2["dual_read_crop_label"] = crop_label
                    _bd2["context_analysis_pending"] = _context
                    # PR #374 — Persistir análisis crudo del brief para que
                    # el handler DUAL_READ_CONFIRMED arme commercial_attrs
                    # con precedencia brief > dual_read (sin re-correr
                    # analyze_brief que es una llamada LLM extra).
                    _brief_raw = _context.get("_brief_analysis_raw")
                    if _brief_raw:
                        _bd2["brief_analysis"] = _brief_raw
                    # PR #375 — Persistir temprano client_name / project /
                    # material / localidad en las columnas dedicadas de Quote
                    # para que el quote aparezca en el listado del dashboard
                    # desde el turno 1 (sin esperar al while loop de Claude).
                    # Antes: _run_dual_read hace return early con la card
                    # emitida, nunca llega al save del while loop donde
                    # corría `_extract_quote_info` — la columna `client_name`
                    # quedaba vacía aunque el breakdown tuviera el valor, y
                    # el filtro del listado (que consulta la columna) lo
                    # trataba como empty draft.
                    #
                    # Reglas:
                    # - Sólo completar columnas que están vacías ("" o None).
                    #   NO pisar valores previos del operador.
                    # - Sanitizar (trim, strip markdown, truncate 450 chars).
                    # - Tolerante a fallos: si `analysis` o `quote` no están,
                    #   se sigue igual (el comportamiento pre-#375).
                    _col_updates = _extract_column_updates_from_analysis(
                        _brief_raw or {}, _ck_quote,
                    )
                    if _col_updates:
                        await db.execute(
                            update(Quote)
                            .where(Quote.id == quote_id)
                            .values(quote_breakdown=_bd2, **_col_updates)
                        )
                        logging.info(
                            f"[context-analysis] early column persist for "
                            f"{quote_id}: fields={list(_col_updates.keys())}"
                        )
                    else:
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd2)
                        )
                    await db.commit()
                except Exception as _e_px:
                    logging.warning(f"[context-analysis] persist pending failed: {_e_px}")
                chunks.append({
                    "type": "context_analysis",
                    "content": _json.dumps(_context, ensure_ascii=False),
                })
                chunks.append({"type": "done", "content": ""})
                # Persistir el turno en messages (igual que Case 2 re-emit).
                # Sin esto, el fetchQuote post-stream no trae el turno y el
                # frontend re-renderea sin la card → aparece el retry spurio.
                try:
                    _user_entry = {
                        "role": "user",
                        "content": [{
                            "type": "text",
                            "text": (user_message or "").strip() or f"(adjuntó plano: {plan_filename})",
                        }],
                    }
                    # PR #379 — JSON real en el content (no `_SHOWN_` marker)
                    # para que el chat se reconstruya al reabrir el quote.
                    _asst_entry = {
                        "role": "assistant",
                        "content": f"__CONTEXT_ANALYSIS__{_json.dumps(_context, ensure_ascii=False)}",
                    }
                    if _ck_quote:
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                messages=list(_ck_quote.messages or []) + [_user_entry, _asst_entry]
                            )
                        )
                        await db.commit()
                except Exception as _e_pm:
                    logging.warning(f"[context-analysis] persist turn failed: {_e_pm}")
                logging.info(
                    f"[context-analysis] emitted for {quote_id}: "
                    f"{len(_context.get('data_known') or [])} known, "
                    f"{len(_context.get('assumptions') or [])} assumptions, "
                    f"{len(_context.get('pending_questions') or [])} questions"
                )
                return (True, chunks)
            except Exception as _e_ctx:
                logging.warning(f"[context-analysis] build failed, fallback a dual_read_result: {_e_ctx}")
                # Fallback: si falla el context analyzer, emitimos dual_read
                # como antes para no romper el flow.

        chunks.append({"type": "dual_read_result", "content": _json.dumps(_dual_result, ensure_ascii=False)})

        # Persist in DB — SIEMPRE guardar hash + result para dedup en turnos
        # siguientes. Sin el hash, el próximo turno re-corre dual_read aunque
        # sea el mismo plano (bug observado: card aparecía N veces).
        try:
            _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
            _q = _qr.scalar_one_or_none()
            if _q:
                _bd = dict(_q.quote_breakdown or {})
                _bd["dual_read_result"] = _dual_result
                _bd["dual_read_plan_hash"] = _plan_hash
                _bd["dual_read_planilla_m2"] = planilla_m2
                _bd["dual_read_crop_label"] = crop_label
                await db.execute(update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd))
                await db.commit()
        except Exception as e:
            logging.warning(f"[dual-read] Failed to save result: {e}")

        logging.info(
            f"[dual-read] Result sent: source={_dual_result.get('source')}, "
            f"review={_dual_result.get('requires_human_review')}"
        )

        # Persist turn
        try:
            _um_q2 = await db.execute(select(Quote).where(Quote.id == quote_id))
            _um_quote2 = _um_q2.scalar_one_or_none()
            if _um_quote2:
                _user_entry2 = {
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": (user_message or "").strip() or f"(adjuntó plano: {plan_filename})",
                    }],
                }
                # PR #379 — JSON real en lugar de marker `_SHOWN_` vacío.
                _asst_entry2 = {
                    "role": "assistant",
                    "content": f"__DUAL_READ__{_json.dumps(_dual_result, ensure_ascii=False)}",
                }
                await db.execute(
                    update(Quote)
                    .where(Quote.id == quote_id)
                    .values(messages=list(_um_quote2.messages or []) + [_user_entry2, _asst_entry2])
                )
                await db.commit()
        except Exception as _e2:
            logging.warning(f"[dual-read] Failed to persist turn: {_e2}")

        chunks.append({"type": "done", "content": ""})
        return (True, chunks)

    except Exception as e:
        logging.error(f"[dual-read] Exception: {e}", exc_info=True)
        return (False, chunks)


def _backfill_material_price_base(quotes_data: list[dict]) -> None:
    """Populate `material_price_base` on each quote dict from the catalog.

    The `generate_documents` tool schema doesn't expose this field to the
    LLM, so it arrives as None. The validator's IVA check skips silently
    if unit is also None, but warns ("Falta material_price_base") when
    unit is set but base isn't. We look up the material by name and copy
    the catalog's base price (USD or ARS) into the dict in-place.

    Mutates `quotes_data` in place. Safe to call idempotently — quotes
    that already carry `material_price_base` are skipped.
    """
    from app.modules.quote_engine.calculator import _find_material

    for qdata in quotes_data:
        if qdata.get("material_price_base"):
            continue
        mname = qdata.get("material_name", "")
        if not mname:
            continue
        try:
            mr = _find_material(mname)
        except Exception as exc:
            logging.warning(
                f"[material_price_base] catalog lookup crashed for {mname!r}: {exc}"
            )
            continue
        if not mr.get("found"):
            continue
        cur = (qdata.get("material_currency") or mr.get("currency", "")).upper()
        if cur == "USD":
            base = mr.get("price_usd_base")
        else:
            base = mr.get("price_ars_base")
        if not base:
            continue
        # Only backfill when the catalog base is *consistent* with the
        # price_unit the agent passed in. If they diverge (stale fixture,
        # manual override, ARS price drift), leave base unset so the
        # validator silently skips the IVA check rather than flipping it
        # from a warning into a hard error that blocks document generation.
        unit = qdata.get("material_price_unit")
        if unit is not None:
            import math as _math_ivc
            from app.core.company_config import get as _ivc
            _iva = _ivc("iva.multiplier", 1.21)
            expected = (
                _math_ivc.floor(base * _iva) if cur == "USD" else round(base * _iva)
            )
            if unit != expected:
                logging.warning(
                    f"[material_price_base] catalog base {base} × {_iva} = {expected} "
                    f"≠ passed unit {unit} for {mname!r} — skipping backfill"
                )
                continue
        qdata["material_price_base"] = base


async def _canonicalize_quotes_data_from_db(
    quote_id: str, quotes_data: list[dict], db,
) -> None:
    """Replace LLM-constructed fields with canonical calc_result from DB.

    The `generate_documents` tool schema lets the LLM build `sectors`,
    `piece_details`, `mo_items`, totals, etc. directly. This is risky:
    Valentina sometimes mangles labels (truncates descriptions, rounds
    largos, deduplicates pieces with same dim2 ignoring different
    largos). Each calculate_quote call persists its full result into
    quote.quote_breakdown — that's the deterministic source of truth.

    For each quote in `quotes_data`, look up the matching persisted
    calc_result (by material_name match) and override the visual /
    monetary fields with the canonical values. Identification fields
    (client_name, project, date, delivery_days) are left untouched.

    Mutates `quotes_data` in place.
    """
    from sqlalchemy import select as _sqsel
    # Collect all candidate calc_results visible from this conversation:
    # the current quote + any sibling quotes for the same client.
    cur_res = await db.execute(_sqsel(Quote).where(Quote.id == quote_id))
    cur = cur_res.scalar_one_or_none()
    candidates: list[dict] = []
    if cur and isinstance(cur.quote_breakdown, dict):
        candidates.append(cur.quote_breakdown)
    if cur and cur.client_name:
        sib_res = await db.execute(
            _sqsel(Quote).where(Quote.client_name == cur.client_name)
        )
        for sib in sib_res.scalars().all():
            if sib.id == quote_id:
                continue
            if isinstance(sib.quote_breakdown, dict):
                candidates.append(sib.quote_breakdown)

    if not candidates:
        return

    # Fields to copy verbatim from the canonical calc into the LLM dict.
    # These determine what the PDF/Excel renders.
    _VISUAL_FIELDS = (
        "sectors", "piece_details",
        "material_m2", "material_price_unit", "material_price_base",
        "material_total", "material_currency",
        "discount_pct", "discount_amount",
        "mo_items", "mo_discount_pct", "mo_discount_amount",
        "total_ars", "total_usd", "total_mo_ars",
        "thickness_mm",
        # PR #41 — canonicalizar también el producto pileta.
        # Antes la LLM podía dejar `sinks` con una pileta fantasma que el
        # calc_result ya había eliminado (ej: operador dijo "sacar pileta"
        # pero la LLM olvidó limpiar sinks de su payload). El resultado
        # era PILETAS block en el PDF con producto que no estaba en la
        # quote recalculada.
        "sinks",
    )

    for qdata in quotes_data:
        mat = (qdata.get("material_name") or "").strip().upper()
        if not mat:
            continue
        # Find best matching calc_result by material name (substring match
        # in either direction to tolerate slight variations like " 20mm").
        best = None
        for c in candidates:
            cmat = (c.get("material_name") or "").strip().upper()
            if not cmat:
                continue
            if cmat == mat or mat in cmat or cmat in mat:
                best = c
                break
        if not best:
            continue
        for f in _VISUAL_FIELDS:
            if f in best and best[f] is not None:
                qdata[f] = best[f]
        logging.info(
            f"[canonical-sectors] Replaced LLM fields with canonical "
            f"calc_result for material {mat!r} in quote {quote_id}"
        )


# ── BUILDING DETECTION (unified — delegates to edificio_parser) ──────────────

def _detect_building(user_message: str) -> bool:
    """Keyword-based building detection for system prompt selection.
    Uses detect_edificio() with empty tables as single source of truth.
    """
    try:
        from app.modules.quote_engine.edificio_parser import detect_edificio
        result = detect_edificio(user_message, [])
        return result["is_edificio"]
    except Exception:
        return False


# ── EXAMPLE SELECTION ────────────────────────────────────────────────────────

# Feature keywords → tags mapping for example selection
_FEATURE_TAGS = {
    # Material types
    "silestone": "silestone",
    "dekton": "dekton",
    "neolith": "neolith",
    "purastone": "purastone",
    "puraprima": "puraprima",
    "pura prima": "puraprima",
    "laminatto": "laminatto",
    "granito": "granito_importado",
    "negro brasil": "granito_importado",
    "gris mara": "granito_nacional",
    "negro boreal": "granito_nacional",
    # Work features
    "isla": "isla",
    "anafe": "anafe",
    "hornalla": "anafe",
    "pileta": "pileta_empotrada",
    "bacha": "pileta_empotrada",
    "apoyo": "pileta_apoyo",
    "johnson": "pileta_johnson",
    "alzada": "alzas",
    "alza": "alzas",
    "frentin": "faldon",
    "faldón": "faldon",
    "faldon": "faldon",
    "corte 45": "corte45",
    "inglete": "corte45",
    "zócalo": "zocalo",
    "zocalo": "zocalo",
    "toma": "tomas",
    "regrueso": "regrueso",
    "pulido": "pulido",
    "descuento": "descuento",
    "arquitecta": "descuento_arquitecta",
    "sobrante": "sobrante",
    # Context
    "edificio": "building",
    "departamento": "building",
    "baño": "pileta_apoyo",
    "toilette": "pileta_apoyo",
}


def _extract_features(user_message: str, is_building: bool) -> set:
    """Extract feature tags from user message for example matching."""
    text = user_message.lower()
    tags = set()
    if is_building:
        tags.add("building")
    else:
        tags.add("residential")
    for keyword, tag in _FEATURE_TAGS.items():
        if keyword in text:
            tags.add(tag)
    return tags


def _load_example_index() -> list:
    """Load examples/index.json once."""
    index_path = BASE_DIR / "examples" / "index.json"
    if not index_path.exists():
        return []
    import json
    with open(index_path) as f:
        return json.load(f)


_EXAMPLE_INDEX = _load_example_index()

# Pre-build a map of example ID → file path to avoid glob() on every request
_EXAMPLE_FILE_MAP: dict[str, Path] = {}
_examples_dir = BASE_DIR / "examples"
if _examples_dir.exists():
    for md_file in _examples_dir.glob("*.md"):
        _EXAMPLE_FILE_MAP[md_file.stem.split("-")[0] + "-" + md_file.stem.split("-")[1] if "-" in md_file.stem else md_file.stem] = md_file
    # Rebuild with proper ID matching from index
    _EXAMPLE_FILE_MAP.clear()
    for md_file in _examples_dir.glob("*.md"):
        for entry in _EXAMPLE_INDEX:
            if md_file.name.startswith(entry["id"]):
                _EXAMPLE_FILE_MAP[entry["id"]] = md_file
                break


# Examples already included in the cached stable block — skip them in dynamic selection
_CACHED_EXAMPLE_IDS = {"quote-013", "quote-003", "quote-004", "quote-010", "quote-030"}


def select_examples(user_message: str, is_building: bool, max_examples: int = None) -> list:
    if max_examples is None:
        max_examples = get_ai_config().get("max_examples", 1)
    """
    Select the most relevant examples based on tag overlap with the current case.
    Skips examples already in the cached stable block.
    Returns list of example file paths (sorted by relevance, most relevant first).
    """
    features = _extract_features(user_message, is_building)
    examples_dir = BASE_DIR / "examples"

    # Score each example by tag overlap — skip cached ones
    scored = []
    for entry in _EXAMPLE_INDEX:
        if entry["id"] in _CACHED_EXAMPLE_IDS:
            continue  # Already in stable cache, don't pay twice
        entry_tags = set(entry.get("tags", []))
        # ⛔ Context filter: edificio quotes must NOT pull residential examples,
        # and vice-versa. Cross-contamination causes the agent to invent data
        # (e.g. Ventus edificio rendered as "Alejandro particular").
        if is_building and ("particular" in entry_tags or "residential" in entry_tags):
            continue
        if not is_building and ("building" in entry_tags or "edificio" in entry_tags):
            continue
        overlap = len(features & entry_tags)
        # Bonus: exact material match
        material = entry.get("material", "").lower()
        if material and material in user_message.lower():
            overlap += 3
        scored.append((overlap, entry["id"], entry))

    # Sort by score descending, then by ID for stability
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Pick top N, ensuring diversity (not all same material type)
    selected = []
    seen_materials = set()
    for score, eid, entry in scored:
        if len(selected) >= max_examples:
            break
        mat = entry.get("material", "")
        if len(selected) < 1 or mat not in seen_materials:
            selected.append(eid)
            seen_materials.add(mat)

    # Resolve to file paths using pre-built map (no filesystem glob)
    paths = []
    for eid in selected:
        if eid in _EXAMPLE_FILE_MAP:
            paths.append(_EXAMPLE_FILE_MAP[eid])

    logging.info(f"Example selection: features={features}, selected={selected}")
    return paths


# ── EXPLICIT REQUIREMENT DETECTION ────────────────────────────────────────────
# Scans all user messages for explicit requirements that MUST appear in the quote.
# Returns a reminder block injected at the END of the system prompt (recency bias).

_REQUIREMENT_PATTERNS: list[tuple[list[str], str, str]] = [
    # (keywords, requirement_id, human_label)
    (["bacha", "pileta", "sink", "compra la bacha", "compra bacha", "compra pileta", "la compra en", "la pide"], "pileta", "PILETA/BACHA — el operador pidió cotizar pileta. DEBE aparecer en el presupuesto. Si no se definió tipo, presupuestar Johnson por defecto."),
    (["anafe", "hornalla"], "anafe", "ANAFE — el operador mencionó anafe. Incluir agujero de anafe en MO."),
    (["zócalo", "zocalo"], "zocalo", "ZÓCALO — el operador mencionó zócalo. Incluir en piezas y MO."),
    (["frentín", "frentin"], "frentin", "FRENTÍN — el operador mencionó frentín. Incluir como pieza (suma m²) + FALDON/CORTE45 en MO."),
    (["regrueso"], "regrueso", "REGRUESO — el operador mencionó regrueso. Incluir REGRUESO por ml en MO."),
    (["pulido"], "pulido", "PULIDO — el operador mencionó pulido de cantos. Incluir PUL en MO."),
    (["colocación", "colocacion", "con colocacion", "instalación", "instalacion"], "colocacion", "COLOCACIÓN — el operador pidió colocación. Incluir en MO."),
]


def _build_requirement_reminder(user_message: str, conversation_history: list | None) -> str | None:
    """Scan all user messages and build a reminder of explicit requirements."""
    # Collect all user text from conversation
    all_user_text = user_message.lower()
    if conversation_history:
        for msg in conversation_history:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    all_user_text += " " + content.lower()
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            all_user_text += " " + block.get("text", "").lower()

    # Detect requirements
    detected = []
    for keywords, req_id, label in _REQUIREMENT_PATTERNS:
        if any(kw in all_user_text for kw in keywords):
            detected.append(label)

    if not detected:
        return None

    lines = "\n".join(f"- {d}" for d in detected)
    return (
        f"\n\n⚠️ RECORDATORIO — REQUERIMIENTOS EXPLÍCITOS DEL OPERADOR:\n"
        f"Los siguientes requerimientos fueron mencionados explícitamente en la conversación. "
        f"TODOS deben estar reflejados en el presupuesto. NO omitir ninguno.\n\n"
        f"{lines}\n\n"
        f"Si alguno de estos no está incluido en tu cálculo actual, DETENETE y agregalo antes de continuar."
    )




# ── SYSTEM PROMPT CACHE ───────────────────────────────────────────────────────
# Stable text (CONTEXT.md + core rules) doesn't change between requests.
# Cache in memory to avoid 6+ disk reads per request.
_stable_text_cache: str | None = None
_conditional_file_cache: dict[str, str] = {}


def _get_stable_text() -> str:
    global _stable_text_cache
    if _stable_text_cache is not None:
        return _stable_text_cache

    context = (BASE_DIR / "CONTEXT.md").read_text(encoding="utf-8")
    rules_dir = BASE_DIR / "rules"
    core_files = [
        "calculation-formulas.md",
        "commercial-conditions.md",
        "materials-guide.md",
        "pricing-variables.md",
        "quote-process-general.md",
    ]
    core_rules = []
    for name in core_files:
        path = rules_dir / name
        if path.exists():
            core_rules.append(f"## {path.stem}\n\n{path.read_text(encoding='utf-8')}")

    # OPT-01: Include top 5 most universal examples in the cached block
    # These cover ~80% of cases and pay 10% price when cached vs full price as conditional
    core_rules.append(
        "## ⛔ NOTA SOBRE LOS EJEMPLOS ⛔\n\n"
        "Los ejemplos que siguen muestran SOLO el formato de salida correcto (tablas, estructura, orden de secciones). "
        "NO muestran el flujo de confirmación. **El flujo de 3 pasos de la REGLA #1 SIEMPRE aplica** — "
        "nunca calcular todo en un solo mensaje como muestran estos ejemplos. "
        "Primero piezas + m² → esperar confirmación → después precios + MO → esperar confirmación → después generar docs."
    )
    _CACHED_EXAMPLES = ["quote-013", "quote-003", "quote-004", "quote-010", "quote-030"]
    examples_dir = BASE_DIR / "examples"
    for eid in _CACHED_EXAMPLES:
        matches = list(examples_dir.glob(f"{eid}*.md"))
        if matches:
            core_rules.append(f"## Ejemplo: {matches[0].stem}\n\n{matches[0].read_text(encoding='utf-8')}")

    # Inject config.json values so Valentina has the real defaults (not hardcoded)
    try:
        import json as _json
        _config = _json.loads((BASE_DIR / "catalog" / "config.json").read_text(encoding="utf-8"))
        _delivery = _config.get("delivery_days", {}).get("display", "30 dias desde la toma de medidas")
        config_block = f"## Valores actuales de config.json\n\n- **Plazo de entrega default:** {_delivery}\n- SIEMPRE usar este valor cuando el operador no especifica plazo. NUNCA inventar otro."
        core_rules.append(config_block)
    except Exception:
        pass

    _stable_text_cache = "\n\n---\n\n".join([context] + core_rules)
    logging.info(f"System prompt stable text cached ({len(_stable_text_cache)} chars, includes 5 core examples)")
    return _stable_text_cache


def _read_cached_file(path) -> str:
    """Read file with in-memory cache."""
    key = str(path)
    if key not in _conditional_file_cache:
        _conditional_file_cache[key] = path.read_text(encoding="utf-8")
    return _conditional_file_cache[key]


def build_system_prompt(has_plan: bool = False, is_building: bool = False, user_message: str = "", conversation_history: list | None = None) -> list:
    """
    Build system prompt as a list of content blocks with cache_control.
    Stable core content is cached in memory + Anthropic prompt cache (5 min TTL).
    """
    stable_text = _get_stable_text()
    rules_dir = BASE_DIR / "rules"

    # Conditional content — loaded based on context
    conditional_parts = []

    if is_building:
        bldg_path = rules_dir / "quote-process-buildings.md"
        if bldg_path.exists():
            conditional_parts.append(f"## {bldg_path.stem}\n\n{_read_cached_file(bldg_path)}")

    if has_plan:
        # PR #25 — plan-reader-v1.md es el prompt canónico de lectura de
        # planos (4 pasadas, placa vs zócalo ml, esquinas L/U sin doble
        # superficie, OCR rules, output JSON). Se incluye SIEMPRE antes
        # que el legacy plan-reading.md para que el agente use las nuevas
        # reglas como source of truth.
        reader_v1 = rules_dir / "plan-reader-v1.md"
        if reader_v1.exists():
            conditional_parts.append(f"## plan-reader-v1\n\n{_read_cached_file(reader_v1)}")
        plan_path = rules_dir / "plan-reading.md"
        if plan_path.exists():
            conditional_parts.append(f"## {plan_path.stem}\n\n{_read_cached_file(plan_path)}")

    # Examples — select 2 most relevant (5 core examples already in stable block)
    example_paths = select_examples(user_message, is_building, max_examples=2)
    for ep in example_paths:
        conditional_parts.append(f"## Ejemplo: {ep.stem}\n\n{_read_cached_file(ep)}")

    # Build system content blocks with cache_control on stable block
    blocks = [
        {
            "type": "text",
            "text": stable_text,
            "cache_control": {"type": "ephemeral"},
        },
    ]

    if conditional_parts:
        conditional_text = "\n\n---\n\n".join(conditional_parts)
        blocks.append({
            "type": "text",
            "text": conditional_text,
        })

    # ── Requirement reminder — scan ALL user messages for explicit requests ──
    reminder = _build_requirement_reminder(user_message, conversation_history)
    if reminder:
        blocks.append({"type": "text", "text": reminder})

    stable_chars = len(stable_text)
    cond_chars = sum(len(p) for p in conditional_parts)
    logging.info(
        f"System prompt blocks: {len(blocks)}, "
        f"stable chars: {stable_chars}, "
        f"conditional chars: {cond_chars}, "
        f"total chars: {stable_chars + cond_chars}"
    )
    return blocks


# ── TOOL DEFINITIONS ──────────────────────────────────────────────────────────

TOOLS = [
    {"name": "list_pieces", "description": "PASO 1 OBLIGATORIO: lista piezas con formato correcto + total m². Usar SIEMPRE en Paso 1 para mostrar piezas. Zócalos salen en ml. El total incluye zócalos. ⛔ Cuando hay plano (imagen/PDF adjunto), cada pieza DEBE llevar `tipo`: mesada/zocalo/alzada/frentin — ver plan-reader-v1.md.", "input_schema": {"type": "object", "properties": {"pieces": {"type": "array", "items": {"type": "object", "properties": {"description": {"type": "string"}, "largo": {"type": "number"}, "prof": {"type": "number"}, "alto": {"type": "number"}, "tipo": {"type": "string", "enum": ["mesada", "zocalo", "alzada", "frentin"], "description": "Tipo de pieza. OBLIGATORIO cuando hay plano adjunto. Opcional en briefs de texto puro."}}, "required": ["description", "largo"]}}}, "required": ["pieces"]}},
    {"name": "catalog_lookup", "description": "Busca precio de 1 SKU en catálogo.", "input_schema": {"type": "object", "properties": {"catalog": {"type": "string"}, "sku": {"type": "string"}}, "required": ["catalog", "sku"]}},
    {"name": "catalog_batch_lookup", "description": "Busca múltiples SKUs. Preferir sobre catalog_lookup para 2+.", "input_schema": {"type": "object", "properties": {"queries": {"type": "array", "items": {"type": "object", "properties": {"catalog": {"type": "string"}, "sku": {"type": "string"}}, "required": ["catalog", "sku"]}}}, "required": ["queries"]}},
    {"name": "check_stock", "description": "Verifica retazos en stock.", "input_schema": {"type": "object", "properties": {"material_sku": {"type": "string"}}, "required": ["material_sku"]}},
    {"name": "check_architect", "description": "Verifica si cliente es arquitecta con descuento.", "input_schema": {"type": "object", "properties": {"client_name": {"type": "string"}}, "required": ["client_name"]}},
    {"name": "read_plan", "description": "AUXILIAR — zoom táctico en zonas de un plano. NO usar para análisis inicial (usá visión nativa sobre el PDF/imagen adjunto). Solo para: cotas chicas, detalles ilegibles, subregiones específicas. LÍMITE: máximo 2 crops por llamada. Si necesitás más, analizá los primeros 2 y después llamá de nuevo.", "input_schema": {"type": "object", "properties": {"filename": {"type": "string"}, "crop_instructions": {"type": "array", "maxItems": 2, "items": {"type": "object", "properties": {"label": {"type": "string"}, "x1": {"type": "integer"}, "y1": {"type": "integer"}, "x2": {"type": "integer"}, "y2": {"type": "integer"}}}}}, "required": ["filename"]}},
    {"name": "generate_documents", "description": "Genera PDF+Excel. 1 quote por material.", "input_schema": {"type": "object", "properties": {"quotes": {"type": "array", "items": {"type": "object", "properties": {"client_name": {"type": "string"}, "project": {"type": "string"}, "date": {"type": "string"}, "delivery_days": {"type": "string"}, "material_name": {"type": "string"}, "material_m2": {"type": "number"}, "material_price_unit": {"type": "number"}, "material_currency": {"type": "string", "enum": ["USD", "ARS"]}, "discount_pct": {"type": "number"}, "sectors": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "pieces": {"type": "array", "items": {"type": "string"}}}}}, "sinks": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "quantity": {"type": "integer"}, "unit_price": {"type": "number"}}}}, "mo_items": {"type": "array", "items": {"type": "object", "properties": {"description": {"type": "string"}, "quantity": {"type": "number"}, "unit_price": {"type": "number"}, "total": {"type": "number"}}}}, "total_ars": {"type": "number"}, "total_usd": {"type": "number"}}, "required": ["client_name", "material_name"]}}}, "required": ["quotes"]}},
    {"name": "update_quote", "description": "Actualiza client_name/project/status en DB.", "input_schema": {"type": "object", "properties": {"quote_id": {"type": "string"}, "updates": {"type": "object", "properties": {"client_name": {"type": "string"}, "project": {"type": "string"}, "material": {"type": "string"}, "total_ars": {"type": "number"}, "total_usd": {"type": "number"}, "status": {"type": "string", "enum": ["draft", "validated", "sent"]}}}}, "required": ["quote_id", "updates"]}},
    {"name": "calculate_quote", "description": "Calcula m², MO, totales. SIEMPRE usar para cálculos.", "input_schema": {"type": "object", "properties": {"client_name": {"type": "string"}, "project": {"type": "string"}, "material": {"type": "string"}, "pieces": {"type": "array", "items": {"type": "object", "properties": {"description": {"type": "string"}, "largo": {"type": "number"}, "prof": {"type": "number"}, "alto": {"type": "number"}, "quantity": {"type": "integer", "description": "Cantidad de unidades físicas de esta pieza (para edificios con tipologías repetidas). Default 1 si no se pasa."}, "m2_override": {"type": "number", "description": "Usar SOLO cuando el operador declara el m² de la pieza en una Planilla de Cómputo (ej: edificios con valores pre-calculados que incluyen zócalos/frentes). Si se pasa, el calculador NO computa largo×prof — usa directamente este valor. No activar 'fallback de profundidades inversas'."}}, "required": ["description", "largo"]}}, "localidad": {"type": "string"}, "colocacion": {"type": "boolean"}, "is_edificio": {"type": "boolean"}, "pileta": {"type": "string", "enum": ["empotrada_cliente", "empotrada_johnson", "apoyo"]}, "pileta_qty": {"type": "integer"}, "pileta_sku": {"type": "string"}, "anafe": {"type": "boolean"}, "anafe_qty": {"type": "integer", "description": "Cantidad de anafes (para edificios con N tipologías). Default 1."}, "frentin": {"type": "boolean"}, "frentin_ml": {"type": "number"}, "regrueso": {"type": "boolean"}, "regrueso_ml": {"type": "number"}, "inglete": {"type": "boolean"}, "pulido": {"type": "boolean"}, "tomas_qty": {"type": "integer", "description": "Agujeros de toma corriente. REQUIERE alzada en pieces + pedido explícito del operador ('Agujero de toma × N'). NO inferir por anafe/zócalo/revestimiento. Sin alzada el calculator lo ignora con warning."}, "skip_flete": {"type": "boolean", "description": "true SOLO si el cliente retira en fábrica. Default false — siempre cobrar flete."}, "flete_qty": {"type": "integer", "description": "Cantidad de fletes declarada por el operador (ej: '× 5 fletes'). Override del cálculo automático. Usar SOLO cuando el operador lo dice explícito en el enunciado."}, "plazo": {"type": "string"}, "discount_pct": {"type": "number"}, "mo_discount_pct": {"type": "number", "description": "Descuento comercial % sobre MO (excluye flete). Usar SOLO si operador lo pide explícito (ej: '5% sobre MO')."}}, "required": ["client_name", "project", "material", "pieces", "localidad", "plazo"]}},
    {"name": "patch_quote_mo", "description": "Modifica MO sin recalcular. Para agregar/quitar flete, colocación.", "input_schema": {"type": "object", "properties": {"remove_items": {"type": "array", "items": {"type": "string"}}, "add_colocacion": {"type": "boolean"}, "add_flete": {"type": "string"}}, "required": []}},
]


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _extract_column_updates_from_analysis(
    analysis: dict, current_quote,
) -> dict:
    """PR #375 — Arma el dict de update() para columnas dedicadas de Quote
    (client_name, project, material, localidad) desde el análisis del brief,
    respetando lo que ya existe.

    Usado por `_run_dual_read` para que el quote quede visible en el
    listado del dashboard desde el turno 1 (sin esperar a que el while
    loop de Claude corra `_extract_quote_info` — ese punto nunca se
    alcanza si el flujo emite `context_analysis` y hace return early).

    Reglas:
    - Sólo propone columnas que están vacías en el quote actual
      (`""` o `None`). NO pisa valores previos del operador.
    - Sanitiza: strip whitespace, remueve markdown bold (\\*\\*), y
      trunca a 450 chars (DB columns son VARCHAR(500)).
    - Si `analysis` es None/empty o `current_quote` es None, devuelve {}.
    - Si el `analysis` no tiene un campo, ese no se toca.

    Args:
        analysis: dict del brief_analyzer (puede contener client_name,
                  project, material, localidad como strings o None).
        current_quote: ORM Quote object con los valores actuales en DB.
                       Si es None, no se puede comparar → devuelve {}.

    Returns:
        Dict con las columnas a updatear (mapeable directo a values() del
        update). Vacío si no hay nada que actualizar.
    """
    import re as _re
    if not current_quote or not analysis:
        return {}
    _MAX_FIELD = 450

    def _clean(s) -> str:
        if not s or not isinstance(s, str):
            return ""
        s = _re.sub(r"[\r\n]+", " ", s)
        s = _re.sub(r"\*+", "", s)
        return s.strip()[:_MAX_FIELD]

    updates: dict = {}
    # Sólo tocamos columnas vacías. "" y None se consideran vacías.
    def _is_empty(v) -> bool:
        return v is None or v == ""

    candidates = [
        ("client_name", analysis.get("client_name")),
        ("project", analysis.get("project")),
        ("material", analysis.get("material")),
        ("localidad", analysis.get("localidad")),
    ]
    for field, raw_value in candidates:
        if not _is_empty(getattr(current_quote, field, None)):
            # Operador o flujo anterior ya seteó valor — no pisar.
            continue
        cleaned = _clean(raw_value)
        if cleaned:
            updates[field] = cleaned
    return updates


def _extract_quote_info(user_message: str) -> dict:
    """Extract client name, project (obra) and material from user message.

    Reconoce múltiples formatos típicos del operador:
      - "Cliente: X, Obra: Y"         (keywords explícitas)
      - "Munge, Obra: A1335"          (nombre + "obra:")
      - "Munge / A1335"               (separador simple cliente/obra)
      - "Pérez — obra Casa Laprida"   (dash)
      - "cliente X proyecto Y material Z"
      - "**CLIENTE:** X **OBRA:** Y"   (brief con Markdown bold)
    """
    import re
    info = {}
    msg = (user_message or "").strip()
    if not msg:
        return info
    # Strip Markdown bold/italic antes de regex-extraer. El operador a veces
    # pega un brief formateado ("**CLIENTE:** Luciana") y los asteriscos se
    # colaban dentro de los valores capturados ("** Luciana" en vez de
    # "Luciana"), además de romper el slicing del extractor de material.
    msg = re.sub(r"\*{1,3}", "", msg)

    # Delimitadores que señalan fin del nombre. "obra" y "proyecto" son
    # límite válido para cortar el nombre del cliente cuando vienen juntos.
    #
    # PR #410 — agregar `[:\s]` (acepta `OBRA:` o `OBRA `) en lugar de
    # solo `\s` (que requería espacio). Caso DYSCON: brief en una sola
    # línea `CLIENTE: DYSCON S.A. OBRA: Unidad...` no cortaba en `OBRA:`
    # porque después de OBRA hay `:` (no whitespace) → cliente absorbía
    # todo. Mismo bug aplica a `MATERIAL:`, `PROYECTO:`, etc.
    _DELIMITERS = (
        r"\s*,|\s+con\s|\s+en\s|\s+lleva|\s+sin\s"
        r"|\s+proyecto[:\s]|\s+obra[:\s]|\s+presupuesto[:\s]|\s+mesada\s|\s+cocina\s"
        r"|\s+ba[ñn]o\s|\s+departamento\s|\s+edificio\s|\s+cotizar\s"
        r"|\s+medidas\s|\s+colocacion\s|\s+colocación\s|\s+z[oó]calo\s"
        r"|\s+anafe\s|\s+bacha\s|\s+pileta\s|\s+flete\s|\s+demora\s"
        r"|\s+plazo\s|\s+material[:\s]|\s+isla\s|\s+lavadero\s|\s+vanitory\s"
        r"|\s+revestimiento\s|\s+frentin\s|\s+frent[ií]n\s|\s+regrueso\s"
        r"|\s+pulido\s|\s+descuento\s|\s+consultar\s"
    )

    # PR #410 helper — preservar capitalización del input cuando viene
    # 100% en mayúsculas (caso "DYSCON S.A."). `.title()` lo cambiaba
    # a "Dyscon S.A.", borrando convención del operador. Si el match
    # tiene letras y todas son mayúsculas, devolver tal cual; si no,
    # aplicar title como antes.
    def _preserve_case(text: str) -> str:
        stripped = text.strip()
        # Solo letras alfabéticas (excluye dígitos, espacios, puntos, &).
        letters = [c for c in stripped if c.isalpha()]
        if letters and all(c.isupper() for c in letters):
            return stripped
        return stripped.title()

    # 1) "Cliente: X" / "Clienta: X" explícito
    match = re.search(
        rf"(?:cliente|clienta)[:\s]+(.+?)(?:{_DELIMITERS}|\n|$)",
        msg, re.IGNORECASE,
    )
    if match:
        info["client_name"] = _preserve_case(match.group(1))

    # 2) "Proyecto: Y" / "Obra: Y" (ambos aceptados).
    # PR #410 — cortar también por `material:` (mismo bug de header
    # en una sola línea: `OBRA: ... MATERIAL: ...` no cortaba antes).
    proj_match = re.search(
        r"(?:proyecto|obra)[:\s]+(.+?)(?:\s+material[:\s]|\n|,|$)",
        msg, re.IGNORECASE,
    )
    if proj_match:
        info["project"] = _preserve_case(proj_match.group(1))

    # 3) Fallback cliente: si no hay keyword "cliente" pero hay estructura
    #    "X, Obra: Y" o "X — Obra Y" → X es el cliente.
    if not info.get("client_name"):
        m = re.match(
            r"\s*([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9\s\.'&]{1,80}?)\s*[,—\-]\s*(?:obra|proyecto)\b",
            msg, re.IGNORECASE,
        )
        if m:
            info["client_name"] = _preserve_case(m.group(1))

    # 4) Fallback adicional: "Nombre / Obra" — separador /
    if not info.get("client_name") and not info.get("project"):
        m2 = re.match(
            r"\s*([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ\s\.'&]{1,80}?)\s*/\s*(.+?)$",
            msg,
        )
        if m2:
            info["client_name"] = _preserve_case(m2.group(1))
            info["project"] = _preserve_case(m2.group(2))

    # Try to find material name — opera sobre `msg` (ya sin Markdown bold)
    # para que briefs formateados con "**MATERIAL:** Purastone..." extraigan
    # "Purastone Blanco Nube" limpio en vez de "TERIAL:** Purastone...".
    material_keywords = [
        "silestone", "dekton", "neolith", "purastone", "puraprima",
        "laminatto", "negro brasil", "blanco norte", "granito",
        "mármol", "marmol",
    ]
    msg_lower = msg.lower()
    for kw in material_keywords:
        if kw in msg_lower:
            # Find the full material name around the keyword
            idx = msg_lower.index(kw)
            # Grab surrounding words for context. Hard-cap both sides to
            # prevent runaway extraction when message has no comma/space.
            start = max(0, msg.rfind(" ", 0, idx) + 1)
            # Limit start to at most 10 chars before idx (avoid capturing
            # markdown headers like "**MATERIAL:**" or prior lines).
            start = max(start, idx - 10)
            # End: prefer newline/comma/" con ", fallback to +40 chars
            candidates = []
            for delim in ["\n", "\r", ",", " con ", " — ", " - "]:
                p = msg.find(delim, idx)
                if p != -1:
                    candidates.append(p)
            end = min(candidates) if candidates else min(len(msg), idx + 40)
            # Hard cap: material name never > 100 chars
            end = min(end, idx + 100)
            info["material"] = msg[start:end].strip()
            break

    return info


def _serialize_content(content) -> list:
    """Convert Anthropic SDK content blocks to JSON-serializable dicts."""
    result = []
    for block in content:
        if hasattr(block, "model_dump"):
            result.append(block.model_dump())
        elif isinstance(block, dict):
            result.append(block)
        else:
            result.append({"type": "text", "text": str(block)})
    return result


# ── TOOL RESULT COMPACTION ────────────────────────────────────────────────────
# After the agent processes a tool result, we don't need the full JSON in
# subsequent iterations. Compact it to save ~3,000-5,000 tokens per quote.

_COMPACT_KEYS = {
    "calculate_quote": ["ok", "material_name", "material_m2", "material_total", "material_currency",
                        "total_ars", "total_usd", "discount_pct", "merma"],
    "catalog_batch_lookup": None,  # Already compact, keep as-is
    "generate_documents": ["ok", "generated", "results"],
}


def _compact_tool_results(assistant_messages: list) -> list:
    """Compact old tool results in assistant_messages to reduce context size.
    Only compacts messages before the last assistant+user pair (keeps the most recent full)."""
    if len(assistant_messages) < 4:
        return assistant_messages  # Not enough history to compact

    compacted = []
    # Keep last 2 messages (latest assistant response + tool results) intact
    to_compact = assistant_messages[:-2]
    to_keep = assistant_messages[-2:]

    for msg in to_compact:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            new_content = []
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    try:
                        result = json.loads(block["content"])
                        # Compact known large results
                        compacted_result = _compact_single_result(result)
                        new_content.append({
                            **block,
                            "content": json.dumps(compacted_result),
                        })
                    except (json.JSONDecodeError, TypeError):
                        new_content.append(block)
                else:
                    new_content.append(block)
            compacted.append({**msg, "content": new_content})
        else:
            compacted.append(msg)

    return compacted + to_keep


def _compact_single_result(result: dict) -> dict:
    """Reduce a tool result to essential fields."""
    if not isinstance(result, dict):
        return result

    # For calculate_quote results (largest: ~2000 tokens)
    if result.get("ok") and result.get("piece_details"):
        return {
            "ok": True,
            "_compacted": True,
            "material_name": result.get("material_name"),
            "material_m2": result.get("material_m2"),
            "material_total": result.get("material_total"),
            "material_currency": result.get("material_currency"),
            "total_ars": result.get("total_ars"),
            "total_usd": result.get("total_usd"),
            "discount_pct": result.get("discount_pct"),
            "mo_count": len(result.get("mo_items", [])),
            "sinks_count": len(result.get("sinks", [])),
        }

    # For batch lookup results (moderate)
    if result.get("results") and result.get("count"):
        compact = {"count": result["count"], "results": {}}
        for k, v in result["results"].items():
            if isinstance(v, dict) and v.get("found"):
                compact["results"][k] = {
                    "found": True,
                    "sku": v.get("sku"),
                    "name": v.get("name", "")[:30],
                    "price": v.get("price_usd") or v.get("price_ars"),
                    "currency": v.get("currency"),
                }
            else:
                compact["results"][k] = v
        return compact

    return result


# ── RETRY CONFIG ─────────────────────────────────────────────────────────────

MAX_RETRIES = 5
RETRY_DELAYS = [5, 10, 15, 20, 30]
MAX_ITERATIONS = 15  # Safety limit — prevent infinite tool loops


# PR #402 — sentinel exception para escape limpio del bloque de merges
# en el handler de [CONTEXT_CONFIRMED] cuando el dual_read viene de
# texto (`source="TEXT"`). Evita corromper el despiece textual con
# merges de patas de isla / alzada que no aplican.
class _PR402SkipMerges(Exception):
    """Sentinel — no es un error, control de flow."""
    pass


# ── AGENT SERVICE ─────────────────────────────────────────────────────────────

class AgentService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            max_retries=0,  # Disable SDK internal retry — we handle it ourselves
            default_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )

    async def stream_chat(
        self,
        quote_id: str,
        messages: list,
        user_message: str,
        plan_bytes: Optional[bytes],
        plan_filename: Optional[str],
        extra_files: Optional[list] = None,
        db: AsyncSession = None,
    ) -> AsyncGenerator[dict, None]:
        # PR #385 — traza de entrada al loop agéntico. Sabemos qué llega
        # del frontend (mensaje, adjuntos) y qué estado del breakdown
        # tenemos al arrancar (gates de flow). Todo lo que pase después
        # se encadena a este entry point.
        from app.modules.agent._trace import (
            log_stream_enter,
            log_bd_mutation,
            log_sse_structural,
            log_tool_call,
            log_tool_result,
            log_apply_answers,
            log_build_commercial_attrs,
            log_build_derived_isla_pieces,
            log_build_verified_context,
            log_messages_persist,
        )
        try:
            _q_enter = await db.execute(select(Quote).where(Quote.id == quote_id))
            _bd_enter = (_q_enter.scalar_one_or_none() or Quote()).quote_breakdown or {}
        except Exception:
            _bd_enter = {}
        log_stream_enter(
            quote_id=quote_id,
            user_message=user_message,
            plan_bytes=plan_bytes,
            extra_files=extra_files,
            bd_pre=_bd_enter,
        )

        # ── PR #395 — Handle [SYSTEM_TRIGGER:process_saved_plan]
        # EARLY: reemplazamos el mensaje por un brief sintético armado
        # desde las columnas del Quote (client_name, material, localidad,
        # pileta, anafe, notes, etc.) ANTES de que el flow normal lo
        # procese. Efecto: el agente ve ese "brief" como si el operador
        # lo hubiera escrito + el plan_bytes ya fue restaurado desde
        # `source_files` por el endpoint `/chat` → multi_crop + context
        # analyzer corren normal → card de contexto sale llena.
        #
        # Sin este handler, el operador tendría que retipear los datos
        # que el chatbot web ya dejó en columnas para que el brief
        # analyzer los capture. Acá los sintetizamos.
        if user_message.startswith("[SYSTEM_TRIGGER:process_saved_plan]"):
            try:
                _q_ps_res = await db.execute(select(Quote).where(Quote.id == quote_id))
                _q_ps = _q_ps_res.scalar_one_or_none()
                if _q_ps is not None:
                    from app.modules.agent.synthetic_brief import (
                        build_brief_from_quote_columns,
                    )
                    user_message = build_brief_from_quote_columns(_q_ps)
                    logging.info(
                        f"[trace:process-saved-plan:{quote_id}] trigger replaced "
                        f"with synthetic brief ({len(user_message)} chars)"
                    )
            except Exception as _e_ps:
                logging.warning(
                    f"[process-saved-plan:{quote_id}] synthetic brief build failed: "
                    f"{_e_ps}. Falling back to raw trigger → flow puede no activarse."
                )

        # ── Handle CONTEXT_CONFIRMED EARLY (PR G): el operador confirmó la card
        # de análisis de contexto (datos + asunciones + preguntas). Aplicamos
        # las respuestas al dual_read_result guardado, emitimos el chunk de
        # despiece real, y terminamos turno. El próximo [DUAL_READ_CONFIRMED]
        # cerrará el flow.
        if user_message.startswith("[CONTEXT_CONFIRMED]"):
            try:
                _ctx_payload = json.loads(user_message[len("[CONTEXT_CONFIRMED]"):])
                _answers = _ctx_payload.get("answers") or []
                # PR #385 — payload recibido del frontend. `answers` es la
                # lista real que el operador respondió en la card de contexto.
                logging.info(
                    f"[trace:context-confirmed:{quote_id}] payload answers={len(_answers)}"
                )
                for _a in _answers:
                    logging.info(
                        f"[trace:context-confirmed:{quote_id}]   "
                        f"id={_a.get('id')} value={_a.get('value')} label={_a.get('label')}"
                    )
                _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
                _q_ctx = _qr.scalar_one_or_none()
                _bd_ctx_pre = dict((_q_ctx.quote_breakdown or {}) if _q_ctx else {})
                _bd_ctx = dict(_bd_ctx_pre)
                _saved_dual = dict(_bd_ctx.get("dual_read_result") or {})
                _dual_before = json.loads(json.dumps(_saved_dual, default=str))
                # PR #402 — Despiece desde texto: el brief lo cerró el
                # operador, los tramos están explícitos y completos. Las
                # mutaciones que vienen abajo (`apply_answers` para
                # frentin/regrueso/zocalos, merges de patas/alzada)
                # corromperían el despiece — pisarían los sectores
                # textuales con valores derivados o vacíos.
                #
                # Las respuestas top-level del contexto (localidad,
                # material, etc.) se preservan en `verified_context_analysis`
                # más abajo y el agente las consume desde ahí cuando arma
                # `calc_input` para `calculate_quote`. No se pierden.
                #
                # Detección: `parsed_pieces_to_card()` setea `source="TEXT"`
                # al top-level del dual_read (text_parser.py:202). Solo
                # tagueado por esa función — duals interactivos (Dual Read
                # del plano) traen otro source o nada.
                _is_text_dispiece = _saved_dual.get("source") == "TEXT"

                # Aplicar las respuestas al dual_read_result — solo para
                # duals interactivos. TEXT salta este bloque.
                if _answers and _saved_dual and not _is_text_dispiece:
                    from app.modules.quote_engine.pending_questions import apply_answers
                    apply_answers(_saved_dual, _answers)
                    # Limpiar pending_questions ya que están respondidas
                    _saved_dual.pop("pending_questions", None)
                elif _is_text_dispiece:
                    # Limpieza defensiva: si por alguna razón el dual TEXT
                    # tiene pending_questions (no debería), las descartamos.
                    _saved_dual.pop("pending_questions", None)
                log_apply_answers(
                    quote_id,
                    flow="context-confirmed",
                    dual_before=_dual_before,
                    dual_after=_saved_dual,
                    answers=_answers,
                )
                # PR #386 — materializar piezas derivadas (patas de isla) como
                # tramos reales del despiece. Antes las patas vivían solo en
                # `verified_derived_pieces` y en un bloque separado del system
                # prompt → el operador no las veía en la card. Ahora aparecen
                # como tramos del sector isla, editables, con flag `_derived`.
                # Idempotente: reconfirmar contexto reemplaza las viejas.
                #
                # PR #402 — Skip merges para despiece TEXT por la misma razón
                # que `apply_answers`: pisarían los sectores textuales.
                if _is_text_dispiece:
                    logging.info(
                        f"[trace:context-confirmed:{quote_id}] "
                        "skipping derived-merge (source=TEXT)"
                    )
                try:
                    if _is_text_dispiece:
                        raise _PR402SkipMerges()
                    from app.modules.quote_engine.dual_reader import (
                        build_derived_isla_pieces,
                        merge_derived_pieces_into_dual_read,
                        merge_alzada_tramos_into_dual_read,
                    )
                    _ctx_derived, _ctx_derived_warn = build_derived_isla_pieces(
                        operator_answers=_answers,
                        verified_measurements=_saved_dual,
                    )
                    log_build_derived_isla_pieces(
                        quote_id,
                        flow="context-confirmed",
                        pieces=_ctx_derived,
                        warnings=_ctx_derived_warn,
                    )
                    _saved_dual = merge_derived_pieces_into_dual_read(
                        _saved_dual, _ctx_derived,
                    )
                    # PR #388 — materializar alzada como tramo por sector
                    # (1 tramo: "Alzada cocina" largo=perímetro × alto).
                    # `apply_alzada_answer` ya escribió los campos top-level
                    # `alzada` / `alzada_alto_m` sobre `_saved_dual`. Este
                    # merge los lleva al despiece visible. Si el operador
                    # respondió "no" → `alzada=False` → el helper solo limpia
                    # alzadas previas (idempotencia al reconfirmar).
                    _alzada_active = bool(_saved_dual.get("alzada"))
                    _alzada_alto = _saved_dual.get("alzada_alto_m")
                    _saved_dual = merge_alzada_tramos_into_dual_read(
                        _saved_dual,
                        alto_m=_alzada_alto,
                        active=_alzada_active,
                    )
                    logging.info(
                        f"[trace:context-confirmed:{quote_id}] alzada "
                        f"active={_alzada_active} alto_m={_alzada_alto}"
                    )
                except _PR402SkipMerges:
                    # Path TEXT — escape limpio, no warn.
                    pass
                except Exception as _e_merge:
                    logging.warning(
                        f"[context-confirmed:{quote_id}] derived-merge failed: {_e_merge}",
                        exc_info=True,
                    )
                # Guardar verified_context_analysis (gate para no re-preguntar)
                _bd_ctx["verified_context_analysis"] = _ctx_payload
                _bd_ctx["dual_read_result"] = _saved_dual
                # PR #383 — NO pop `context_analysis_pending`. Se preserva
                # como snapshot para que el endpoint /reopen-context pueda
                # regenerar la card `__CONTEXT_ANALYSIS__` con los mismos
                # data_known + assumptions + pending_questions que el
                # operador vio al confirmar. El gate "ya se confirmó
                # contexto" usa `verified_context_analysis` (no
                # `context_analysis_pending`), por lo que preservarlo no
                # re-dispara la card a mitad del flujo.
                if _q_ctx:
                    await db.execute(
                        update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd_ctx)
                    )
                    await db.commit()
                log_bd_mutation(quote_id, "context-confirmed", _bd_ctx_pre, _bd_ctx)
                logging.info(
                    f"[context-confirmed] {quote_id} applied {len(_answers)} answers, "
                    "emitting dual_read_result"
                )
                # PR #404 — Re-emitir el chunk `dual_read_result` igual
                # que en el path interactivo. El skip que hizo PR #402
                # rompía el contrato con el frontend: ese chunk no es
                # solo "render la card", es el trigger de la transición
                # al estado "confirmar despiece". Sin re-emit, el
                # operador queda en una UI muerta sin botón "Confirmar
                # despiece" activo (la card original en `messages` es
                # texto histórico, no widget interactivo).
                #
                # Lo que SÍ se mantiene de PR #402 (más arriba en este
                # mismo handler) — eso solucionaba el bug real:
                #   1. `apply_answers` no corre cuando source=TEXT
                #      → los tramos textuales NO se mutan.
                #   2. `merge_derived_pieces_into_dual_read` y
                #      `merge_alzada_tramos_into_dual_read` no corren
                #      → los sectores no se pisan con derivados.
                # El re-emit de acá ahora sale con el `_saved_dual`
                # intacto (mismos sectores que el primer emit del brief),
                # así que ya no hay card fantasma.
                _dr_chunk = json.dumps(_saved_dual, ensure_ascii=False)
                log_sse_structural(quote_id, "dual_read_result", _dr_chunk)
                yield {"type": "dual_read_result", "content": _dr_chunk}
                log_sse_structural(quote_id, "done", "")
                yield {"type": "done", "content": ""}
                # PR #379 — Persistir el flujo real al DB:
                # - user turn: el `[CONTEXT_CONFIRMED]<json>` que mandó el
                #   frontend (el frontend lo detecta y renderiza como
                #   pill "Contexto confirmado ✅").
                # - assistant: `__DUAL_READ__<json>` con la card real.
                # Antes persistíamos un fake user "(contexto confirmado)"
                # + marker `_SHOWN_` sin data — ambos quedaban como texto
                # crudo al reabrir el quote.
                try:
                    _turn = [
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": user_message}],
                        },
                        {
                            "role": "assistant",
                            "content": f"__DUAL_READ__{json.dumps(_saved_dual, ensure_ascii=False)}",
                        },
                    ]
                    if _q_ctx:
                        _merged = list(_q_ctx.messages or []) + _turn
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                messages=_merged
                            )
                        )
                        await db.commit()
                        log_messages_persist(
                            quote_id,
                            flow="context-confirmed",
                            added_turns=_turn,
                            total_count=len(_merged),
                        )
                except Exception:
                    pass
                return
            except Exception as _e_ctx:
                logging.error(f"[context-confirmed] handler failed: {_e_ctx}", exc_info=True)
                yield {"type": "text", "content": "No se pudo procesar la confirmación del contexto. Reintentá."}
                yield {"type": "done", "content": ""}
                return

        # ── Handle DUAL_READ_CONFIRMED EARLY: save verified_context + replace
        # user_message BEFORE content is built. Si hacemos esto más tarde,
        # `content` ya tiene el JSON crudo y Claude lo ve como mensaje.
        # Además evitamos que el check de dual_read (más abajo) intercepte.
        _just_confirmed_dual_read = False
        if user_message.startswith("[DUAL_READ_CONFIRMED]"):
            _just_confirmed_dual_read = True
            try:
                _confirmed_json = json.loads(user_message[len("[DUAL_READ_CONFIRMED]"):])
                # PR #385 — payload crudo que llegó del frontend. Este es el
                # punto que el usuario ve en la card editable cuando aprieta
                # "Confirmar medidas". Si aquí el dual_read no refleja lo
                # editado → bug en el componente. Si aquí está bien pero
                # downstream Claude usa otro valor → bug en system prompt
                # injection o derived pieces.
                from app.modules.agent._trace import snapshot_dual_read as _snap_dr
                logging.info(
                    f"[trace:dual-read-confirmed:{quote_id}] payload received: "
                    f"snap={_snap_dr(_confirmed_json)}"
                )
                logging.info(
                    f"[trace:dual-read-confirmed:{quote_id}] pending_answers="
                    f"{len(_confirmed_json.get('pending_answers') or [])}"
                )
                # Aplicar respuestas de pending_questions (ej: zócalos agregados
                # determinísticamente cuando el operador eligió la opción default).
                # El confirmed_json viene con `pending_answers` si el frontend
                # las incluyó.
                try:
                    from app.modules.quote_engine.pending_questions import apply_answers
                    _answers = _confirmed_json.get("pending_answers") or []
                    if _answers:
                        _dr_before_apply = json.loads(json.dumps(_confirmed_json, default=str))
                        apply_answers(_confirmed_json, _answers)
                        log_apply_answers(
                            quote_id,
                            flow="dual-read-confirmed/pending",
                            dual_before=_dr_before_apply,
                            dual_after=_confirmed_json,
                            answers=_answers,
                        )
                except Exception as _e_ans:
                    logging.warning(f"[pending-questions] apply_answers failed: {_e_ans}")
                from app.modules.quote_engine.dual_reader import (
                    build_verified_context,
                    build_commercial_attrs,
                    build_derived_isla_pieces,
                )
                # PR #374 — Juntar atributos comerciales con precedencia
                # explícita (operator_answer > brief > dual_read > default)
                # para que el verified_context le diga al LLM qué wording
                # usar ("confirmado" solo si source=operator_answer). Antes
                # el LLM re-leía el plano y sobreafirmaba ("2 anafes
                # confirmados" cuando dual_read había detectado 1).
                _qr0 = await db.execute(select(Quote).where(Quote.id == quote_id))
                _q0 = _qr0.scalar_one_or_none()
                _bd0_pre = dict(_q0.quote_breakdown or {}) if _q0 else {}
                _bd0 = dict(_bd0_pre)
                _saved_dual = _bd0.get("dual_read_result") or {}
                # Reconstruir el analysis del brief (si está cacheado).
                # Fallback: diccionario vacío → reconcile se cae al dual_read.
                _ctx_analysis = _bd0.get("brief_analysis") or {}
                # Respuestas del operador a la card de contexto
                # (verified_context_analysis guarda `{"answers": [...]}`).
                _vca = _bd0.get("verified_context_analysis") or {}
                _op_answers_ctx = _vca.get("answers") or []
                # Sumar también las pending_answers aplicadas en este turno
                # (frontend las manda dentro del _confirmed_json).
                _op_answers_turn = _confirmed_json.get("pending_answers") or []
                _op_answers = list(_op_answers_ctx) + list(_op_answers_turn)
                # PR #385 — explicitar qué answers entran a los builders.
                logging.info(
                    f"[trace:dual-read-confirmed:{quote_id}] operator_answers "
                    f"ctx={len(_op_answers_ctx)} turn={len(_op_answers_turn)} total={len(_op_answers)}"
                )
                for _oa in _op_answers:
                    logging.info(
                        f"[trace:dual-read-confirmed:{quote_id}]   "
                        f"id={_oa.get('id')} value={_oa.get('value')} label={_oa.get('label')}"
                    )
                _commercial_attrs = build_commercial_attrs(
                    analysis=_ctx_analysis,
                    dual_result=_saved_dual,
                    operator_answers=_op_answers,
                )
                log_build_commercial_attrs(
                    quote_id, flow="dual-read-confirmed", result=_commercial_attrs,
                )
                # PR #393 — Re-aplicar answers del contexto sobre el
                # `_confirmed_json` final. Caso Bernardi 2026-04-24: el
                # parser dejó R1/R2 sin medir; el operador los editó en la
                # card; al confirmar medidas los derivados (alzada, frentín,
                # regrueso) quedaban con los ml/perímetros viejos (null).
                #
                # Orden acordado con el operador:
                #   1. apply_answers — rescribe frentin[]/regrueso[] con
                #      ml=largo_actual; re-escribe alzada/alzada_alto_m.
                #   2. merge_alzada_tramos_into_dual_read — regenera tramos
                #      "Alzada <sector>" con perímetro actual (no-derivados).
                #   3. build_derived_isla_pieces + merge — regenera patas
                #      con el largo de isla actual.
                #   4. build_verified_context — texto con todo materializado.
                #
                # "Replace, no merge blando": cada helper pisa el kind
                # correspondiente. Ninguno hace append. Answers son fuente
                # de verdad; si el operador editó item derivado (ej: alto
                # de pata), ese cambio se pierde — debe editar la answer
                # vía reopen-context.
                from app.modules.quote_engine.dual_reader import (
                    merge_derived_pieces_into_dual_read,
                    merge_alzada_tramos_into_dual_read,
                )
                if _op_answers_ctx:
                    try:
                        _dr_before_re = json.loads(json.dumps(_confirmed_json, default=str))
                        apply_answers(_confirmed_json, _op_answers_ctx)
                        log_apply_answers(
                            quote_id,
                            flow="dual-read-confirmed/re-apply-ctx",
                            dual_before=_dr_before_re,
                            dual_after=_confirmed_json,
                            answers=_op_answers_ctx,
                        )
                    except Exception as _e_re:
                        logging.warning(
                            f"[dual-read-confirmed:{quote_id}] re-apply ctx "
                            f"answers failed: {_e_re}"
                        )

                # Materializar alzada con los largos finales (replace por
                # `_derived_kind="alzada"`).
                _alzada_active_final = bool(_confirmed_json.get("alzada"))
                _alzada_alto_final = _confirmed_json.get("alzada_alto_m")
                _confirmed_json = merge_alzada_tramos_into_dual_read(
                    _confirmed_json,
                    alto_m=_alzada_alto_final,
                    active=_alzada_active_final,
                )
                logging.info(
                    f"[trace:dual-read-confirmed:{quote_id}] re-materialized "
                    f"alzada active={_alzada_active_final} alto_m={_alzada_alto_final}"
                )

                # Materializar patas de isla con el largo actual de la isla
                # y las answers finales (replace por `_derived_kind="isla_pata"`).
                # Llamamos siempre — incluso con _derived_pieces=[] el merge
                # limpia las patas viejas si el operador cambió a "no patas".
                _derived_pieces, _derived_warnings = build_derived_isla_pieces(
                    operator_answers=_op_answers,
                    verified_measurements=_confirmed_json,
                )
                log_build_derived_isla_pieces(
                    quote_id,
                    flow="dual-read-confirmed",
                    pieces=_derived_pieces,
                    warnings=_derived_warnings,
                )
                _confirmed_json = merge_derived_pieces_into_dual_read(
                    _confirmed_json, _derived_pieces,
                )
                # PR #386 — NO pasar `derived_pieces` a build_verified_context.
                # Las patas ya están como tramos del sector isla y se renderizan
                # naturalmente bajo `SECTOR: ISLA` en el verified_context text.
                # Si además pasáramos `derived_pieces`, Claude las vería dos
                # veces (tramos + bloque [PIEZAS DERIVADAS]) y las sumaría
                # doble al armar `calculate_quote.pieces`.
                _verified_ctx = build_verified_context(
                    _confirmed_json,
                    commercial_attrs=_commercial_attrs,
                    derived_pieces=None,
                )
                log_build_verified_context(
                    quote_id, flow="dual-read-confirmed", text=_verified_ctx,
                )
                if _q0:
                    _bd0["verified_measurements"] = _confirmed_json
                    _bd0["verified_context"] = _verified_ctx
                    # Guardar también los commercial_attrs estructurados
                    # para auditoría y uso futuro (ej: templates de docs).
                    _bd0["verified_commercial_attrs"] = _commercial_attrs
                    # PR #386 — `verified_derived_pieces` queda derivable del
                    # dual_read (tramos `_derived:true` del sector isla). No
                    # lo persistimos más para evitar doble source of truth.
                    _bd0.pop("verified_derived_pieces", None)
                    await db.execute(update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd0))
                    await db.commit()
                    log_bd_mutation(quote_id, "dual-read-confirmed", _bd0_pre, _bd0)
                logging.info(
                    f"[dual-read] Verified measurements + commercial attrs "
                    f"saved for {quote_id} (early handler). "
                    f"attrs_keys={list(_commercial_attrs.keys())}"
                )
                # Reemplazar el mensaje por un prompt que Claude entienda.
                # El verified_context entra al system prompt via build_system_prompt.
                # PR #75 — evitar que el regex de _extract_quote_info matchee
                # accidentalmente palabras en este texto. No usar "cliente"
                # ni "proyecto" literal (la regex matchea "cliente[:\s]+…"
                # y "proyecto[:\s]+…"). Fix A adicional: en este turno se
                # salta la extracción de todos modos (defensa en profundidad).
                user_message = (
                    "El operador acaba de confirmar las medidas del plano. "
                    "Tenés las medidas verificadas en tu system prompt. "
                    "Seguí con el flujo: si falta algún dato comercial, "
                    "pedilo; si ya están todos, avanzá al Paso 2 "
                    "(búsqueda de precios y cálculo)."
                )
                # NOTA: NO limpiamos plan_bytes — Claude necesita el plano +
                # planilla (material, pileta, ubicación) para el Paso 2. Sin
                # eso alucina (ej: reporta Silestone cuando el plano es
                # Purastone). La skip-lógica de dual_read previene re-emisión
                # de card porque verified_context ya quedó guardado arriba.
            except Exception as e:
                logging.error(f"[dual-read] Confirmation handler failed: {e}", exc_info=True)
                # Continuar con el mensaje original — Claude intentará responder

        # ── PR #79 — Handle chat-based modification of the dual_read card ──
        # Si existe un dual_read_result no confirmado + operador escribe
        # algo que parece pedir una edición (keywords agregar/sacar/modific +
        # zócalo/mesada/tramo) → procesar como patch y re-emitir la card.
        try:
            from app.modules.agent.card_editor import (
                is_card_modification_message,
                extract_card_patch,
                apply_card_patch,
                format_patch_summary,
            )
            if (
                not _just_confirmed_dual_read
                and user_message
                and is_card_modification_message(user_message)
            ):
                _cm_q = await db.execute(select(Quote).where(Quote.id == quote_id))
                _cm_quote = _cm_q.scalar_one_or_none()
                _cm_bd = (_cm_quote.quote_breakdown or {}) if _cm_quote else {}
                _existing_card = _cm_bd.get("dual_read_result")
                _already_confirmed_cm = bool(
                    _cm_bd.get("verified_context") or _cm_bd.get("measurements_confirmed")
                )
                if _existing_card and not _existing_card.get("error"):
                    # PR #80 — Cualquier modificación del despiece (pre o
                    # post-confirmación) aplica el patch. Si el quote ya
                    # había pasado a Paso 2 (verified_context + material
                    # guardados), lo REVERTIMOS a Paso 1: limpiamos state
                    # post-confirmación para que el operador re-confirme
                    # el nuevo despiece y Valentina regenere Paso 2.
                    _has_paso2 = bool(
                        _cm_bd.get("material_name")
                        or _cm_bd.get("total_ars")
                        or _cm_bd.get("mo_items")
                    )
                    _reverting_from_paso2 = _already_confirmed_cm or _has_paso2
                    logging.info(
                        f"[card-editor] Modification intent for {quote_id} "
                        f"(reverting_from_paso2={_reverting_from_paso2})"
                    )
                    yield {"type": "action", "content": "✏️ Aplicando cambios al card..."}
                    _ops = await extract_card_patch(user_message, _existing_card)
                    if not _ops:
                        # Parse falló o LLM no identificó ops — preguntar de vuelta.
                        _fallback = (
                            "No entendí bien el cambio. ¿Podés detallar qué pieza "
                            "(zócalo / mesada / sector), dónde (qué tramo) y qué "
                            "medidas? Ej: 'agregá zócalo lateral_der de 0.60 ml × "
                            "0.07 m en el tramo L-retorno'."
                        )
                        yield {"type": "text", "content": _fallback}
                        yield {"type": "done", "content": ""}
                        # Persist user turn + assistant reply en historial
                        try:
                            _turn = [
                                {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                {"role": "assistant", "content": _fallback},
                            ]
                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(
                                    messages=list(_cm_quote.messages or []) + _turn
                                )
                            )
                            await db.commit()
                        except Exception as _e_t:
                            logging.warning(f"[card-editor] persist turn failed: {_e_t}")
                        return

                    _patched_card, _applied, _errors = apply_card_patch(
                        dict(_existing_card), _ops
                    )
                    # Guardar el card patcheado + limpiar Paso 2 state si
                    # estamos revirtiendo. PR #378 — la lista de campos
                    # limpiar vive en `card_editor.reset_quote_to_paso1`
                    # (reutilizada por el endpoint reopen-measurements).
                    try:
                        if _reverting_from_paso2:
                            from app.modules.agent.card_editor import reset_quote_to_paso1
                            _cm_bd_new = reset_quote_to_paso1(_cm_bd)
                        else:
                            _cm_bd_new = dict(_cm_bd)
                        _cm_bd_new["dual_read_result"] = _patched_card
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                quote_breakdown=_cm_bd_new,
                                total_ars=None if _reverting_from_paso2 else _cm_quote.total_ars,
                                total_usd=None if _reverting_from_paso2 else _cm_quote.total_usd,
                            )
                        )
                        await db.commit()
                    except Exception as _e_s:
                        logging.warning(f"[card-editor] save patched card failed: {_e_s}")

                    _summary = format_patch_summary(_applied, _errors)
                    if _reverting_from_paso2:
                        _summary = (
                            "🔄 Volvimos a Paso 1 porque cambiaste el despiece. "
                            "El Paso 2 anterior fue descartado.\n\n"
                            + _summary
                            + "\n\nConfirmá las nuevas medidas en el card para "
                            "generar el nuevo Paso 2."
                        )
                    yield {"type": "text", "content": _summary}
                    yield {
                        "type": "dual_read_result",
                        "content": json.dumps(_patched_card, ensure_ascii=False),
                    }
                    yield {"type": "done", "content": ""}

                    # Persist turn
                    try:
                        _turn = [
                            {"role": "user", "content": [{"type": "text", "text": user_message}]},
                            {"role": "assistant", "content": _summary},
                        ]
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                messages=list(_cm_quote.messages or []) + _turn
                            )
                        )
                        await db.commit()
                    except Exception as _e_t2:
                        logging.warning(f"[card-editor] persist patched turn failed: {_e_t2}")
                    return
        except Exception as e:
            logging.warning(f"[card-editor] handler exception (non-fatal): {e}", exc_info=True)
            # Fall through al flujo normal de Claude.

        # ── Text-only brief → emit card editable ──
        # Si no hay archivos adjuntos pero el operador mandó texto con medidas,
        # parseamos el texto y emitimos la MISMA card que dual_read. Así el
        # despiece editable es SIEMPRE el puente obligatorio antes del cálculo,
        # independientemente de si el input fue visual (plano) o textual.
        #
        # Condiciones:
        # - No hay plan_bytes ni extra_files (input 100% texto)
        # - No es un trigger de sistema ([DUAL_READ_CONFIRMED], [SYSTEM_TRIGGER])
        # - No hay card previa ya emitida ni medidas confirmadas (dedup)
        # - El parser devuelve ≥1 mesada válida
        _is_system_trigger = user_message and user_message.strip().startswith("[")
        if (
            not _just_confirmed_dual_read
            and not plan_bytes
            and not (extra_files or [])
            and user_message
            and not _is_system_trigger
        ):
            try:
                _tp_q = await db.execute(select(Quote).where(Quote.id == quote_id))
                _tp_quote = _tp_q.scalar_one_or_none()
                _tp_bd = (_tp_quote.quote_breakdown or {}) if _tp_quote else {}
                _tp_has_card = bool(_tp_bd.get("dual_read_result"))
                _tp_confirmed = bool(
                    _tp_bd.get("verified_context") or _tp_bd.get("measurements_confirmed")
                )
            except Exception:
                _tp_quote = None
                _tp_bd = {}
                _tp_has_card = False
                _tp_confirmed = False

            if _tp_quote is not None and not _tp_has_card and not _tp_confirmed:
                try:
                    from app.modules.quote_engine.text_parser import parse_brief_to_card
                    _info_hint = _extract_quote_info(user_message)
                    yield {"type": "action", "content": "📐 Leyendo medidas del texto..."}
                    _text_card = await parse_brief_to_card(
                        user_message,
                        _info_hint.get("material", "") or "",
                        _info_hint.get("project", "") or "",
                    )
                except Exception as _e_tp:
                    logging.warning(f"[text-parse] parse_brief_to_card failed: {_e_tp}")
                    _text_card = None

                if _text_card:
                    # Apply metadata hints to Quote columns
                    _persist_update = {}
                    if _info_hint.get("client_name") and not _tp_quote.client_name:
                        _persist_update["client_name"] = _info_hint["client_name"]
                    if _info_hint.get("project") and not _tp_quote.project:
                        _persist_update["project"] = _info_hint["project"]
                    if _info_hint.get("material") and not _tp_quote.material:
                        _persist_update["material"] = _info_hint["material"]

                    # PR G (parity) — mismo gate que el flujo de plano: si no
                    # hay verified_context_analysis, emitir primero la card
                    # de contexto (datos detectados + asunciones + preguntas
                    # bloqueantes) y persistir el dual_read_result en DB para
                    # levantarlo cuando el operador confirme.
                    _context_already_confirmed_tp = bool(
                        _tp_bd.get("verified_context_analysis")
                    )
                    if not _context_already_confirmed_tp:
                        try:
                            from app.modules.quote_engine.context_analyzer import (
                                build_context_analysis,
                            )
                            from app.modules.agent.tools.catalog_tool import (
                                get_ai_config as _get_ai_tp,
                            )
                            _cfg_tp = {
                                "default_zocalo_height": (_get_ai_tp() or {}).get(
                                    "default_zocalo_height", 0.07
                                ),
                                "default_payment": "Contado",
                                "default_delivery_days": "30 días",
                            }
                            _ctx_quote_tp = {
                                "client_name": _persist_update.get("client_name")
                                    or _tp_quote.client_name,
                                "project": _persist_update.get("project")
                                    or _tp_quote.project,
                                "material": _persist_update.get("material")
                                    or _tp_quote.material,
                                "localidad": getattr(_tp_quote, "localidad", None),
                                "is_building": getattr(_tp_quote, "is_building", False),
                            }
                            _context_tp = await build_context_analysis(
                                user_message or "", _ctx_quote_tp, _text_card, _cfg_tp
                            )
                        except Exception as _e_ctx_tp:
                            logging.warning(
                                f"[text-parse] build_context_analysis failed: {_e_ctx_tp}"
                            )
                            _context_tp = None

                        if _context_tp:
                            try:
                                _persist_bd = dict(_tp_bd)
                                _persist_bd["dual_read_result"] = _text_card
                                _persist_bd["context_analysis_pending"] = _context_tp
                                _persist_update["quote_breakdown"] = _persist_bd
                                # PR #379 — JSON real en content para que el
                                # chat reconstruya la card al reabrir.
                                _persist_update["messages"] = list(
                                    _tp_quote.messages or []
                                ) + [
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": user_message}
                                        ],
                                    },
                                    {
                                        "role": "assistant",
                                        "content": f"__CONTEXT_ANALYSIS__{json.dumps(_context_tp, ensure_ascii=False)}",
                                    },
                                ]
                                await db.execute(
                                    update(Quote)
                                    .where(Quote.id == quote_id)
                                    .values(**_persist_update)
                                )
                                await db.commit()
                            except Exception as _e_pp_ctx:
                                logging.warning(
                                    f"[text-parse] persist context failed: {_e_pp_ctx}"
                                )
                            logging.info(
                                f"[text-parse] emitted context_analysis for {quote_id}"
                            )
                            yield {
                                "type": "context_analysis",
                                "content": json.dumps(_context_tp, ensure_ascii=False),
                            }
                            yield {"type": "done", "content": ""}
                            return

                    # Flujo legacy / fallback — sin context_analysis:
                    # emitimos el dual_read_result directo (igual que antes).
                    try:
                        _persist_bd = dict(_tp_bd)
                        _persist_bd["dual_read_result"] = _text_card
                        _persist_update["quote_breakdown"] = _persist_bd
                        # PR #379 — JSON real de la card para reconstrucción
                        # al reabrir el quote.
                        _persist_update["messages"] = list(_tp_quote.messages or []) + [
                            {"role": "user", "content": [{"type": "text", "text": user_message}]},
                            {
                                "role": "assistant",
                                "content": f"__DUAL_READ__{json.dumps(_text_card, ensure_ascii=False)}",
                            },
                        ]
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(**_persist_update)
                        )
                        await db.commit()
                    except Exception as _e_pp:
                        logging.warning(f"[text-parse] persist failed: {_e_pp}")
                    logging.info(
                        f"[text-parse] emitted card with {len(_text_card['sectores'][0]['tramos'])} "
                        f"tramos for {quote_id}"
                    )
                    yield {
                        "type": "dual_read_result",
                        "content": json.dumps(_text_card, ensure_ascii=False),
                    }
                    yield {"type": "done", "content": ""}
                    return
                # Si parsing devolvió None → sigue al flujo normal; el LLM
                # verá el mensaje y pedirá medidas con formato en su respuesta.

        # Build system prompt per request with contextual loading
        has_plan = plan_bytes is not None and plan_filename is not None

        # ── Building detection: DB flag (sticky) > history > current message ──
        # Once a quote enters building mode, it stays there for all turns.
        is_building = False
        _auto_advance_visual = False  # Set to True when page confirmed → skip to while loop
        try:
            _bq = await db.execute(select(Quote).where(Quote.id == quote_id))
            _bquote = _bq.scalar_one_or_none()
            if _bquote and _bquote.is_building:
                is_building = True
        except Exception:
            pass
        # If not in DB, detect from current message
        if not is_building:
            is_building = _detect_building(user_message)
        # If not in current message, scan conversation history
        if not is_building and messages:
            for msg in messages:
                if msg.get("role") == "user":
                    c = msg.get("content", "")
                    text_parts = []
                    if isinstance(c, str):
                        text_parts.append(c)
                    elif isinstance(c, list):
                        for blk in c:
                            if isinstance(blk, dict) and blk.get("type") == "text":
                                text_parts.append(blk.get("text", ""))
                    for part in text_parts:
                        if _detect_building(part) or "EDIFICIO PRE-CALCULADO" in part or "EDIFICIO — PASO 1" in part:
                            is_building = True
                            break
                if is_building:
                    break
        # Persist to DB so future turns don't need to re-scan
        if is_building:
            try:
                await db.execute(update(Quote).where(Quote.id == quote_id).values(is_building=True))
                await db.commit()
            except Exception:
                pass

        system_prompt = build_system_prompt(has_plan=has_plan, is_building=is_building, user_message=user_message, conversation_history=messages)

        # ── Operator web: 1 material / 1 presupuesto guardrail ──
        # If the fresh brief mentions 2+ distinct canonical materials (and the
        # quote has not locked a material yet), interrupt and ask which one to
        # use. The chatbot flow (/api/v1/quote) does NOT pass through here and
        # keeps its multi-material array support intact.
        #
        # Fail-open: detector only flags when it is sure (full canonical names
        # or valid SKUs). Partial words like "blanco"/"norte" do not trigger.
        try:
            from app.modules.agent.material_detector import detect_materials_in_brief

            _mm_quote_row = await db.execute(select(Quote).where(Quote.id == quote_id))
            _mm_q = _mm_quote_row.scalar_one_or_none()
            _mm_has_material = bool(_mm_q and (_mm_q.material or "").strip())
            _mm_has_calc = bool(
                _mm_q
                and isinstance(_mm_q.quote_breakdown, dict)
                and _mm_q.quote_breakdown.get("calc_results")
            )
            # Skip guardrail once a material or calc exists, or if in edificio
            # flow (edificio may legitimately have multiple materials per the
            # existing building parser and runs through its own state machine).
            if not is_building and not _mm_has_material and not _mm_has_calc:
                _detected = detect_materials_in_brief(user_message)
                if len(_detected) >= 2:
                    _materials_list = ", ".join(_detected[:5])
                    _first = _detected[0]
                    _reply = (
                        f"Detecté {len(_detected)} materiales en el brief: "
                        f"{_materials_list}.\n\n"
                        f"Regla: 1 material = 1 presupuesto.\n"
                        f"¿Procedo con **{_first}**? "
                        f"Para los demás materiales generá un presupuesto nuevo."
                    )
                    try:
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                messages=list(_mm_q.messages or []) + [
                                    {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                    {"role": "assistant", "content": [{"type": "text", "text": _reply}]},
                                ],
                            )
                        )
                        await db.commit()
                    except Exception as _e_persist:
                        logging.warning(f"[multi-material] failed to persist reply: {_e_persist}")
                    logging.info(
                        f"[multi-material] operator brief mentioned {len(_detected)} materials "
                        f"for quote {quote_id}: {_detected}"
                    )
                    yield {"type": "text", "content": _reply}
                    yield {"type": "done", "content": ""}
                    return
        except Exception as _e_mm:
            # Fail-open: never let the detector block a valid flow
            logging.warning(f"[multi-material] detector error (fail-open): {_e_mm}")

        # ── Inject verified measurements if available ──
        try:
            _qr_vm = await db.execute(select(Quote).where(Quote.id == quote_id))
            _q_vm = _qr_vm.scalar_one_or_none()
            if _q_vm and _q_vm.quote_breakdown and _q_vm.quote_breakdown.get("verified_context"):
                _vc = _q_vm.quote_breakdown["verified_context"]
                # Append to system prompt as additional context block
                system_prompt.append({"type": "text", "text": _vc, "cache_control": {"type": "ephemeral"}})
                logging.info(f"[dual-read] Injected verified measurements into system prompt ({len(_vc)} chars)")
        except Exception:
            pass

        # ── EDIFICIO STATE MACHINE: Paso 2, 3 — all server-side ──
        # "step1_review" → confirm → render Paso 2 → "step2_quote"
        # "step2_quote"  → confirm → generate documents → "step3_done"
        if is_building and not has_plan:
            try:
                _p2q = await db.execute(select(Quote).where(Quote.id == quote_id))
                _p2quote = _p2q.scalar_one_or_none()
                _bd = _p2quote.quote_breakdown if _p2quote else None
                _building_step = _bd.get("building_step") if isinstance(_bd, dict) else None
                _is_confirmation = len(user_message.strip()) < 200

                # ── Awaiting client name: capture and resume ──
                if _building_step == "awaiting_client_name" and user_message.strip():
                    new_name = user_message.strip()
                    try:
                        _bd["building_step"] = "step2_quote"  # Resume to Paso 3
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                client_name=new_name,
                                quote_breakdown=_bd,
                                messages=list(_p2quote.messages or []) + [
                                    {"role": "user", "content": [{"type": "text", "text": new_name}]},
                                    {"role": "assistant", "content": [{"type": "text", "text": f"Cliente: {new_name}. Generando presupuestos..."}]},
                                ],
                            )
                        )
                        await db.commit()
                        # Re-read quote with updated client_name
                        _p2q = await db.execute(select(Quote).where(Quote.id == quote_id))
                        _p2quote = _p2q.scalar_one_or_none()
                        _bd = _p2quote.quote_breakdown
                        _building_step = "step2_quote"
                        # Fall through to Paso 3 below
                    except Exception as e:
                        logging.error(f"Failed to save client name: {e}")
                        yield {"type": "text", "content": "Error al guardar el nombre del cliente."}
                        yield {"type": "done", "content": ""}
                        return

                # ── VISUAL EDIFICIO: Awaiting material choice or failed page confirmation ──
                if _building_step == "awaiting_material_choice" and user_message.strip():
                    from app.modules.quote_engine.edificio_parser import (
                        compute_edificio_aggregates, validate_edificio,
                    )
                    from app.modules.quote_engine.visual_edificio_parser import (
                        validate_material_choice, resolve_material_choice,
                        build_normalized_from_visual,
                        render_visual_edificio_paso1, render_visual_edificio_choices,
                        dismiss_failed_pages,
                    )

                    pages_data = _bd.get("visual_pages_raw", [])
                    pending_actions = _bd.get("pending_actions", [])
                    msg_lower = user_message.strip().lower()

                    # ── Action: operator confirms to proceed without failed pages ──
                    if any(kw in msg_lower for kw in ["continuar sin fallidas", "seguir sin fallidas", "ignorar fallidas"]):
                        dismissed = [p.get("_page_number") for p in pages_data if p.get("_extraction_failed")]
                        pages_data = dismiss_failed_pages(pages_data)
                        _bd["visual_pages_raw"] = pages_data
                        _bd["dismissed_failed_pages"] = dismissed
                        _bd["operator_accepted_partial_extraction"] = True
                        if "failed_pages_confirmation" in pending_actions:
                            pending_actions.remove("failed_pages_confirmation")

                    # ── Action: operator chooses material ──
                    has_material_blocker = any("Material ambiguo" in b for b in _bd.get("blockers", []))
                    if has_material_blocker and not any(kw in msg_lower for kw in ["continuar sin", "seguir sin", "ignorar"]):
                        # Validate material choice against detected options
                        ok, normalized_choice, available_options = validate_material_choice(pages_data, user_message.strip())
                        if not ok:
                            opts_str = " / ".join(f"({i+1}) {o}" for i, o in enumerate(available_options))
                            response = (
                                f"No pude mapear \"{user_message.strip()}\" a un material válido.\n\n"
                                f"Las opciones detectadas son:\n{opts_str}\n\n"
                                f"Indicá el material exacto o el número de opción."
                            )
                            try:
                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(
                                        quote_breakdown=_bd,
                                        messages=list(_p2quote.messages or []) + [
                                            {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                            {"role": "assistant", "content": [{"type": "text", "text": response}]},
                                        ],
                                    )
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"Failed to save invalid material choice: {e}")
                            yield {"type": "text", "content": response}
                            yield {"type": "done", "content": ""}
                            return
                        # Valid choice — resolve
                        pages_data = resolve_material_choice(pages_data, normalized_choice)
                        _bd["material_choice"] = normalized_choice
                        if "material_choice" in pending_actions:
                            pending_actions.remove("material_choice")

                    _bd["pending_actions"] = pending_actions

                    # Re-normalize and check remaining blockers
                    norm_data, visual_warnings, visual_blockers = build_normalized_from_visual(pages_data)

                    if visual_blockers:
                        # Still blockers
                        response = render_visual_edificio_choices(pages_data, visual_warnings, visual_blockers)
                        _bd["visual_pages_raw"] = pages_data
                        _bd["warnings"] = visual_warnings
                        _bd["blockers"] = visual_blockers
                    else:
                        # All clear → proceed to Paso 1 review
                        edif_summary = compute_edificio_aggregates(norm_data)
                        edif_validation = validate_edificio(norm_data, edif_summary)
                        material_choice = _bd.get("material_choice")
                        response = render_visual_edificio_paso1(
                            pages_data, norm_data, edif_summary, visual_warnings,
                            material_choice=material_choice,
                        )
                        response += "\n\n¿Confirmás las piezas y medidas?"

                        _bd["building_step"] = "step1_review"
                        _bd["summary"] = edif_summary
                        _bd["validation"] = dict(edif_validation)
                        _bd["normalized_pieces_flat"] = [dict(p) for s in norm_data.get("sections", []) for p in s.get("pieces", [])]
                        _bd["visual_pages_raw"] = pages_data
                        _bd["warnings"] = visual_warnings

                    try:
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                quote_breakdown=_bd,
                                messages=list(_p2quote.messages or []) + [
                                    {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                    {"role": "assistant", "content": [{"type": "text", "text": response}]},
                                ],
                            )
                        )
                        await db.commit()
                    except Exception as e:
                        logging.error(f"Failed to save material choice state: {e}")

                    yield {"type": "text", "content": response}
                    yield {"type": "done", "content": ""}
                    return

                # ── VISUAL PAGES: Operator drew zone rectangle (Fix G) ──
                if _building_step and _building_step.endswith("_zone_selector"):
                    # Zone was already set by POST /zone-select endpoint
                    # This message is the system_trigger from frontend
                    # Just continue to extraction — zone is in quote_breakdown
                    logging.info(f"[visual-pages] Zone selector confirmed, continuing extraction")
                    # Don't return — fall through to while loop for extraction

                # ── VISUAL PAGES: Operator confirming a page ──
                elif _building_step and _building_step.startswith("visual_page_") and _building_step.endswith("_confirm"):
                    from app.modules.quote_engine.visual_quote_builder import (
                        parse_page_confirmation,
                        apply_corrections,
                        compute_visual_geometry,
                        compute_field_confidence,
                        infer_visual_services,
                        build_visual_pending_questions,
                        render_page_confirmation,
                        render_final_paso1,
                        resolve_visual_materials,
                        MaterialResolution,
                        TipologiaGeometry,
                    )
                    import re as _re_page

                    _page_match = _re_page.search(r"visual_page_(\d+)_confirm", _building_step)
                    _conf_page = int(_page_match.group(1)) if _page_match else 1
                    _page_key = str(_conf_page)
                    _page_data = _bd.get("page_data", {})
                    _pd = _page_data.get(_page_key, {})
                    _tips = _pd.get("tipologias", [])
                    _zones = _pd.get("detected_zones", [])
                    _total_pages = _bd.get("total_pages", 1)

                    action_result = parse_page_confirmation(user_message, _tips, _zones)
                    action = action_result.get("action", "unclear")

                    if action == "confirm" or action == "value_correction":
                        if action == "value_correction":
                            _tips = apply_corrections(_tips, action_result["corrections"])
                            # Recalculate geometry
                            mat_res_d = _bd.get("material_resolution", {})
                            mat_res = MaterialResolution(**mat_res_d) if mat_res_d else resolve_visual_materials("")
                            geo = compute_visual_geometry(_tips, mat_res)
                            _pd["tipologias"] = _tips
                            _pd["geometries"] = [
                                {"id": g.id, "m2_unit": g.m2_unit, "m2_total": g.m2_total,
                                 "backsplash_ml_unit": g.backsplash_ml_unit,
                                 "backsplash_m2_total": g.backsplash_m2_total,
                                 "physical_pieces_total": g.physical_pieces_total}
                                for g in geo.tipologias
                            ]

                        _pd["confirmed"] = True
                        # Learn zone_default from first confirmed page
                        if not _bd.get("zone_default") and _pd.get("selected_zone"):
                            _bd["zone_default"] = _pd["selected_zone"]["name"]

                        _pages_completed = _bd.get("pages_completed", [])
                        if _conf_page not in _pages_completed:
                            _pages_completed.append(_conf_page)
                        _bd["pages_completed"] = _pages_completed
                        _page_data[_page_key] = _pd
                        _bd["page_data"] = _page_data

                        next_page = _conf_page + 1
                        if next_page <= _total_pages:
                            _bd["current_page"] = next_page
                            _bd["building_step"] = f"visual_page_{next_page}"
                            try:
                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"[visual-pages] Failed to persist: {e}")
                            yield {"type": "action", "content": f"✅ Página {_conf_page} confirmada. Procesando página {next_page}..."}
                            yield {"type": "action", "content": f"📐 Analizando página {next_page}/{_total_pages}..."}

                            # Auto-advance: directly process next page without waiting for operator
                            # Inject system instruction as user message → while loop calls Claude for zone detection
                            assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                                f"[SISTEMA] Página {_conf_page} confirmada. "
                                f"Analizar página {next_page}/{_total_pages} del PDF. "
                                f"Detectar zonas nombradas (PLANTA, CORTE, etc). Solo JSON de zones."
                            )}]})
                            _auto_advance_visual = True
                        else:
                            # ── ALL PAGES CONFIRMED → render final PASO 1 ──
                            # Build confirmed_tipologias from page_data (NOT by append)
                            all_tips = []
                            for pg in sorted(_page_data.keys(), key=lambda x: int(x)):
                                pd = _page_data[pg]
                                if pd.get("confirmed") and not pd.get("skipped"):
                                    all_tips.extend(pd.get("tipologias", []))

                            mat_res_d = _bd.get("material_resolution", {})
                            mat_res = MaterialResolution(**mat_res_d) if mat_res_d else resolve_visual_materials("")
                            geometry = compute_visual_geometry(all_tips, mat_res)
                            services = infer_visual_services(all_tips, geometry)
                            pending = build_visual_pending_questions(mat_res, services, all_tips)
                            final_text = render_final_paso1(geometry.tipologias, services, mat_res, pending)

                            _bd["building_step"] = "visual_all_confirmed"
                            _bd["confirmed_tipologias"] = all_tips
                            try:
                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"[visual-pages] Failed to persist final: {e}")

                            yield {"type": "text", "content": final_text}
                            yield {"type": "done", "content": ""}
                            return

                    elif action == "zone_correction":
                        new_zone = action_result["zone"]
                        _pd["selected_zone"] = new_zone
                        _pd["zone_was_auto"] = False
                        _bd["zone_default"] = new_zone["name"]
                        # Clear tipologias to force re-extraction with new zone
                        _pd.pop("tipologias", None)
                        _pd.pop("geometries", None)
                        _page_data[_page_key] = _pd
                        _bd["page_data"] = _page_data
                        _bd["building_step"] = f"visual_page_{_conf_page}"
                        try:
                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"[visual-pages] Failed to persist zone correction: {e}")
                        yield {"type": "text", "content": f"Zona cambiada a '{new_zone['name']}'. Re-analizando..."}
                        yield {"type": "done", "content": ""}
                        return

                    elif action == "skip":
                        _pd["confirmed"] = True
                        _pd["skipped"] = True
                        _pages_completed = _bd.get("pages_completed", [])
                        if _conf_page not in _pages_completed:
                            _pages_completed.append(_conf_page)
                        _bd["pages_completed"] = _pages_completed
                        _page_data[_page_key] = _pd
                        _bd["page_data"] = _page_data

                        next_page = _conf_page + 1
                        if next_page <= _total_pages:
                            _bd["current_page"] = next_page
                            _bd["building_step"] = f"visual_page_{next_page}"
                        else:
                            _bd["building_step"] = "visual_all_confirmed"

                        try:
                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"[visual-pages] Failed to persist skip: {e}")

                        if next_page <= _total_pages:
                            yield {"type": "action", "content": f"Página {_conf_page} salteada. Procesando página {next_page}..."}
                            assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                                f"[SISTEMA] Página {_conf_page} salteada. "
                                f"Analizar página {next_page}/{_total_pages}. Solo JSON de zones."
                            )}]})
                            _auto_advance_visual = True
                        # Fall through to render final if last page
                    else:
                        yield {"type": "text", "content": (
                            "No entendí la respuesta. Opciones:\n"
                            "- **Confirmar**: sí / ok / dale\n"
                            "- **Corregir medida**: `DC-02 profundidad = 0.65`\n"
                            "- **Cambiar zona**: `zona = CORTE 1-1`\n"
                            "- **Sin marmolería**: skip"
                        )}
                        yield {"type": "done", "content": ""}
                        return

                # ── Skip remaining pre-loop handlers if auto-advancing visual pages ──
                if _auto_advance_visual:
                    _visual_builder_done = False  # Reset for next page processing in while loop
                    logging.info(f"[visual-pages] Auto-advance: PDF in context = {plan_bytes is not None}, strip_disabled = True")
                    # Fall through to while True loop with injected system message

                # ── PASO 3: Generate documents ──
                elif _building_step == "step2_quote" and _bd.get("paso2_calc"):
                    # Validate client_name before generating
                    if not (_p2quote.client_name or "").strip():
                        # Save state and ask for client name
                        try:
                            _bd["building_step"] = "awaiting_client_name"
                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(
                                    quote_breakdown=_bd,
                                    messages=list(_p2quote.messages or []) + [
                                        {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                        {"role": "assistant", "content": [{"type": "text", "text": "Para generar los presupuestos necesito el nombre del cliente. Escribilo y continúo."}]},
                                    ],
                                )
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"Failed to save awaiting_client_name state: {e}")
                        yield {"type": "text", "content": "Para generar los presupuestos necesito el nombre del cliente. Escribilo y continúo."}
                        yield {"type": "done", "content": ""}
                        return

                    from app.modules.agent.tools.document_tool import generate_edificio_documents
                    yield {"type": "action", "content": "Generando presupuestos..."}

                    paso2_calc = _bd["paso2_calc"]
                    edif_summary = _bd.get("summary", {})

                    try:
                        doc_result = await generate_edificio_documents(
                            quote_id=quote_id,
                            paso2_calc=paso2_calc,
                            summary=edif_summary,
                            client_name=_p2quote.client_name or "",
                            project=_p2quote.project or f"Proyecto Edificio {_p2quote.client_name or ''}".strip(),
                            localidad=_p2quote.localidad or "Rosario",
                        )
                    except Exception as e:
                        logging.error(f"[edificio-paso3] generate_edificio_documents crashed: {e}", exc_info=True)
                        yield {"type": "text", "content": f"Error al generar documentos: {str(e)[:300]}"}
                        yield {"type": "done", "content": ""}
                        return

                    if doc_result.get("ok"):
                        from app.modules.agent.tools.drive_tool import upload_single_file_to_drive
                        from app.core.static import OUTPUT_DIR as _OUT

                        # ── Upload each file to Drive individually + build files_v2 ──
                        files_v2_items = []
                        subfolder = f"{_p2quote.client_name or 'Edificio'}"

                        for gen in doc_result["generated"]:
                            mat = gen.get("material", "")
                            is_resumen = "RESUMEN" in mat.upper()
                            mat_key = "resumen" if is_resumen else mat.replace(" ", "_").lower()[:30]

                            for kind, url_key in [("pdf", "pdf_url"), ("excel", "excel_url")]:
                                local_url = gen.get(url_key)
                                if not local_url:
                                    continue
                                # Derive local path from URL: /files/{qid}/filename → OUTPUT_DIR/{qid}/filename
                                local_path = str(_OUT / local_url.replace("/files/", "", 1)) if local_url.startswith("/files/") else ""
                                filename = local_url.split("/")[-1] if local_url else ""

                                # Upload to Drive
                                drive_info = {}
                                if local_path:
                                    try:
                                        dr = await upload_single_file_to_drive(local_path, subfolder)
                                        if dr.get("ok"):
                                            drive_info = {
                                                "file_id": dr["file_id"],
                                                "drive_url": dr["drive_url"],
                                                "drive_download_url": dr["drive_download_url"],
                                            }
                                            gen[f"drive_{kind}_url"] = dr["drive_url"]
                                    except Exception as e:
                                        logging.warning(f"Drive upload failed for {filename}: {e}")

                                scope = "parent" if is_resumen else "child"
                                file_key = f"parent:summary_{kind}" if is_resumen else f"{mat_key}:{kind}"

                                files_v2_items.append({
                                    "kind": f"summary_{kind}" if is_resumen else kind,
                                    "scope": scope,
                                    "file_key": file_key,
                                    "owner_quote_id": quote_id if is_resumen else None,  # filled per-child below
                                    "filename": filename,
                                    "local_path": local_path,
                                    "local_url": local_url or "",
                                    **({f"drive_{k}": v for k, v in drive_info.items()} if drive_info else {}),
                                })

                            # Set drive_url on gen (legacy compat — use first Drive URL found)
                            gen["drive_url"] = gen.get("drive_pdf_url") or gen.get("drive_excel_url") or ""

                        # ── Build response ──
                        lines = ["Documentos generados:\n"]
                        for gen in doc_result["generated"]:
                            lines.append(f"📄 **{gen['material']}**")
                            if gen.get("drive_pdf_url"):
                                lines.append(f"  - [PDF en Drive]({gen['drive_pdf_url']})")
                            elif gen.get("pdf_url"):
                                lines.append(f"  - [Descargar PDF]({gen['pdf_url']})")
                            if gen.get("drive_excel_url"):
                                lines.append(f"  - [Excel en Drive]({gen['drive_excel_url']})")
                            elif gen.get("excel_url"):
                                lines.append(f"  - [Descargar Excel]({gen['excel_url']})")
                        lines.append("")
                        lines.append(f"**Total ARS: ${doc_result['grand_total_ars']:,.0f}".replace(",", ".") + "**")
                        if doc_result["grand_total_usd"]:
                            lines.append(f"**Total USD: USD {doc_result['grand_total_usd']:,.0f}".replace(",", ".") + "**")
                        paso3_response = "\n".join(lines)

                        # ── Persist to DB ──
                        try:
                            _bd["building_step"] = "step3_done"
                            _bd["files_v2"] = {"items": files_v2_items}

                            # Match generated docs to children
                            children_result = await db.execute(
                                select(Quote).where(
                                    Quote.parent_quote_id == quote_id,
                                    Quote.quote_kind == "building_child_material",
                                )
                            )
                            children = {(c.material or "").upper(): c for c in children_result.scalars().all()}

                            resumen_gen = None
                            for gen in doc_result["generated"]:
                                mat_upper = (gen.get("material") or "").upper()
                                if "RESUMEN" in mat_upper:
                                    resumen_gen = gen
                                    continue
                                child = children.get(mat_upper)
                                if not child:
                                    for cmat, cq in children.items():
                                        if mat_upper in cmat or cmat in mat_upper:
                                            child = cq
                                            break
                                if child:
                                    # Build child's own files_v2
                                    child_files = [
                                        {**item, "owner_quote_id": child.id}
                                        for item in files_v2_items
                                        if item["scope"] == "child" and item.get("filename", "").startswith(gen.get("material", "XXX")[:15])
                                    ]
                                    # Simpler match: just grab items for this material
                                    mat_key = mat_upper.replace(" ", "_").lower()[:30]
                                    child_files = [item for item in files_v2_items if item.get("file_key", "").startswith(mat_key)]
                                    for cf in child_files:
                                        cf["owner_quote_id"] = child.id

                                    child_bd = child.quote_breakdown or {}
                                    child_bd["files_v2"] = {"items": child_files}

                                    await db.execute(
                                        update(Quote).where(Quote.id == child.id).values(
                                            pdf_url=gen.get("pdf_url"),
                                            excel_url=gen.get("excel_url"),
                                            drive_url=gen.get("drive_url"),
                                            drive_pdf_url=gen.get("drive_pdf_url"),
                                            drive_excel_url=gen.get("drive_excel_url"),
                                            quote_breakdown=child_bd,
                                            status=QuoteStatus.VALIDATED,
                                        )
                                    )

                            # Update parent
                            updated_msgs = list(_p2quote.messages or []) + [
                                {"role": "user", "content": [{"type": "text", "text": user_message}]},
                                {"role": "assistant", "content": [{"type": "text", "text": paso3_response}]},
                            ]
                            parent_update = {
                                "quote_breakdown": _bd,
                                "messages": updated_msgs,
                                "status": QuoteStatus.VALIDATED,
                            }
                            if resumen_gen:
                                parent_update["pdf_url"] = resumen_gen.get("pdf_url")
                                parent_update["excel_url"] = resumen_gen.get("excel_url")
                                parent_update["drive_url"] = resumen_gen.get("drive_url")

                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(**parent_update)
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"Failed to save edificio Paso 3: {e}", exc_info=True)

                        yield {"type": "text", "content": paso3_response}
                        yield {"type": "done", "content": ""}
                        return  # ← EXIT: edificio Paso 3 done
                    else:
                        yield {"type": "text", "content": f"Error al generar documentos: {doc_result.get('error', 'desconocido')}"}
                        yield {"type": "done", "content": ""}
                        return

                # ── PASO 2: Pricing ──
                if _building_step == "step1_review" and _is_confirmation:
                    from app.modules.quote_engine.edificio_parser import render_edificio_paso2
                    yield {"type": "action", "content": "Calculando precios por material..."}

                    edif_summary = _bd["summary"]
                    edif_localidad = _p2quote.localidad or "Rosario"

                    paso2_data = render_edificio_paso2(edif_summary, edif_localidad)
                    paso2_response = paso2_data["rendered"] + "\n¿Confirmás para generar los presupuestos?"

                    # Save calc results + advance state machine
                    try:
                        _bd["building_step"] = "step2_quote"  # Next confirmation → Paso 3 (generate)
                        _bd["paso2_calc"] = {
                            "calc_results": paso2_data["calc_results"],
                            "mo_items": paso2_data["mo_items"],
                            "mo_total": paso2_data["mo_total"],
                            "grand_total_ars": paso2_data["grand_total_ars"],
                            "grand_total_usd": paso2_data["grand_total_usd"],
                        }
                        updated_msgs = list(_p2quote.messages or []) + [
                            {"role": "user", "content": [{"type": "text", "text": user_message}]},
                            {"role": "assistant", "content": [{"type": "text", "text": paso2_response}]},
                        ]
                        await db.execute(
                            update(Quote).where(Quote.id == quote_id).values(
                                quote_breakdown=_bd,
                                messages=updated_msgs,
                                total_ars=paso2_data["grand_total_ars"],
                                total_usd=paso2_data["grand_total_usd"],
                            )
                        )
                        await db.commit()

                        # ── Create building_child_material quotes ──
                        from app.modules.quote_engine.edificio_parser import build_edificio_doc_context
                        import uuid as _uuid_mod
                        child_contexts = build_edificio_doc_context(
                            edif_summary, _bd["paso2_calc"],
                            _p2quote.client_name or "", _p2quote.project or "",
                        )
                        child_ids = []
                        for ctx in child_contexts:
                            child_id = str(_uuid_mod.uuid4())
                            mat_raw = ctx.get("_mat_name_raw", "")
                            child_quote = Quote(
                                id=child_id,
                                quote_kind="building_child_material",
                                parent_quote_id=quote_id,
                                client_name=_p2quote.client_name,
                                project=_p2quote.project or f"Proyecto Edificio {_p2quote.client_name or ''}".strip(),
                                material=ctx.get("material_name", mat_raw),
                                localidad=_p2quote.localidad,
                                is_building=True,
                                status=QuoteStatus.DRAFT,
                                source=_p2quote.source,
                                is_read=True,
                                total_ars=ctx.get("total_ars", 0),
                                total_usd=ctx.get("total_usd", 0),
                                quote_breakdown={
                                    k: v for k, v in ctx.items()
                                    if not k.startswith("_")
                                },
                            )
                            db.add(child_quote)
                            child_ids.append(child_id)
                            logging.info(f"[edificio] Created child {child_id} for {mat_raw}")
                        await db.commit()
                        logging.info(f"[edificio] Created {len(child_ids)} children for parent {quote_id}")

                    except Exception as e:
                        logging.error(f"Failed to save edificio Paso 2: {e}", exc_info=True)

                    yield {"type": "text", "content": paso2_response}
                    yield {"type": "done", "content": ""}
                    return  # ← EXIT: no Claude for edificio Paso 2
            except Exception as e:
                logging.warning(f"Edificio Paso 2 bypass failed, falling back to Claude: {e}")

        # Build user message content
        content = []
        pdf_has_images = False  # Track if PDF has drawings (needs vision pass)
        _expected_m2 = None  # Surface area from planilla (if found) for validation
        is_visual_building = False  # Track if this is a multipágina CAD building (Ventus-type)
        if plan_bytes and plan_filename:
            # Persist plan file to temp so read_plan tool can access it later
            save_plan_to_temp(plan_filename, plan_bytes)
            # PR #64 — hash estable del plano crudo (antes de cualquier
            # rasterización / JPEG re-encoding). Se pasa a _run_dual_read
            # para dedup entre turnos. Se computa una sola vez acá.
            import hashlib as _hashlib_main
            _raw_plan_hash = _hashlib_main.sha256(plan_bytes).hexdigest()[:16]
            ext = Path(plan_filename).suffix.lower()
            if ext == ".pdf":
                # Pasada 1: Extract text/tables from PDF with pdfplumber (exact, no hallucination)
                extracted_text = ""
                tables_all = []  # Collect all tables for summary
                num_pages = 0
                try:
                    import pdfplumber
                    import io as _io
                    _planilla_data = None  # Will hold parsed planilla if detected
                    with pdfplumber.open(_io.BytesIO(plan_bytes)) as pdf:
                        num_pages = len(pdf.pages)
                        for i, page in enumerate(pdf.pages):
                            # Extract tables first (structured data)
                            tables = page.extract_tables()
                            tables_all.extend(tables)

                            # Try to detect planilla layout (table on right side)
                            if not _planilla_data and tables:
                                try:
                                    from app.modules.quote_engine.planilla_parser import parse_planilla_table, detect_table_x_from_words
                                    table_objects = page.find_tables()
                                    _planilla_data = parse_planilla_table(
                                        tables, page_width=page.width, page_height=page.height,
                                        table_bboxes=table_objects
                                    )
                                    if _planilla_data:
                                        # Use word positions for accurate table x (bbox is unreliable)
                                        _word_x = detect_table_x_from_words(page)
                                        if _word_x > 0:
                                            _planilla_data.table_x0 = _word_x
                                        logging.info(f"[planilla] Detected: material={_planilla_data.material}, "
                                                     f"m2={_planilla_data.m2}, table_x0={_planilla_data.table_x0:.0f}")
                                        if _planilla_data.m2:
                                            _expected_m2 = _planilla_data.m2
                                except Exception as e:
                                    logging.warning(f"[planilla] Detection failed: {e}")

                            if tables:
                                for t_idx, table in enumerate(tables):
                                    extracted_text += f"\n--- Tabla {t_idx+1} (página {i+1}) ---\n"
                                    for row in table:
                                        cells = [str(c).strip() if c else "" for c in row]
                                        extracted_text += " | ".join(cells) + "\n"
                            # Also extract plain text (headers, notes, etc.)
                            page_text = page.extract_text()
                            if page_text:
                                extracted_text += f"\n--- Texto página {i+1} ---\n{page_text}\n"

                            # ── Vision detection: 3-condition heuristic ──
                            # Condition 1: Raster images > 200x200px
                            for img in (page.images or []):
                                w = img.get("width", 0) or img.get("x1", 0) - img.get("x0", 0)
                                h = img.get("height", 0) or img.get("top", 0) - img.get("bottom", 0)
                                if abs(w) > 200 and abs(h) > 200:
                                    pdf_has_images = True
                                    logging.info(f"Vision trigger: raster image {abs(w)}x{abs(h)} on page {i+1}")

                            # Condition 2: High vector density (CAD/architectural drawings)
                            VECTOR_LINES_THRESHOLD = 20
                            VECTOR_RECTS_THRESHOLD = 10
                            VECTOR_CURVES_THRESHOLD = 20
                            n_lines = len(page.lines or [])
                            n_rects = len(page.rects or [])
                            n_curves = len(page.curves or [])
                            if n_lines > VECTOR_LINES_THRESHOLD or n_rects > VECTOR_RECTS_THRESHOLD or n_curves > VECTOR_CURVES_THRESHOLD:
                                pdf_has_images = True
                                logging.info(f"Vision trigger: vector density on page {i+1} (lines={n_lines}, rects={n_rects}, curves={n_curves})")

                    # Condition 3: Low useful text + domain context (plano/obra keywords)
                    if not pdf_has_images and num_pages > 0:
                        avg_chars = len(extracted_text.strip()) / num_pages
                        PLAN_KEYWORDS = {"plano", "lámina", "lamina", "cocina", "obra", "escala", "corte", "planta", "tipología", "tipologia", "desarrollo", "mesada"}
                        text_lower = extracted_text.lower()
                        has_plan_context = any(kw in text_lower for kw in PLAN_KEYWORDS)
                        if avg_chars < 200 and has_plan_context:
                            pdf_has_images = True
                            logging.info(f"Vision trigger: low text ({avg_chars:.0f} chars/page avg) + plan keywords detected")
                    if extracted_text.strip():
                        # ── Extract M2 from planilla text (deterministic surface validator) ──
                        _expected_m2 = None
                        import re as _re_m2
                        # Match patterns like "M2  2,50 m2", "M2: 2.50m2", "2,50 m2 - Con zócalos"
                        _m2_patterns = [
                            r'(?:M2|m2|SUPERFICIE|superficie)\s*[:\|]?\s*(\d+[.,]\d+)\s*m2',
                            r'(\d+[.,]\d+)\s*m2\s*[-–—]\s*[Cc]on\s+z[oó]calos',
                            r'(\d+[.,]\d+)\s*m2',
                        ]
                        for _pat in _m2_patterns:
                            _m2_match = _re_m2.search(_pat, extracted_text)
                            if _m2_match:
                                _expected_m2 = float(_m2_match.group(1).replace(",", "."))
                                logging.info(f"[m2-validator] Extracted expected M2 from planilla: {_expected_m2}")
                                break

                        # Check if this is an edificio — use deterministic parser
                        from app.modules.quote_engine.edificio_parser import (
                            detect_edificio, parse_edificio_tables,
                            normalize_edificio_data, compute_edificio_aggregates,
                            validate_edificio, render_edificio_paso1,
                        )
                        detection = detect_edificio(user_message, tables_all)

                        if detection["is_edificio"]:
                            # ── EDIFICIO DETECTED ──
                            detection_mode = detection.get("detection_mode", "keyword")
                            logging.info(f"Edificio detected (confidence={detection['confidence']:.2f}, mode={detection_mode}): {detection['reasons']}")

                            # Try tabular path first
                            raw_data = parse_edificio_tables(tables_all)
                            has_tabular_data = bool(raw_data.get("sections"))

                            if has_tabular_data:
                                # ── PATH A: TABULAR EDIFICIO (existing, 100% server-side) ──
                                detection_mode = "tabular"
                                norm_data = normalize_edificio_data(raw_data)
                                edif_summary = compute_edificio_aggregates(norm_data)
                                edif_validation = validate_edificio(norm_data, edif_summary)
                                rendered_paso1 = render_edificio_paso1(norm_data, edif_summary)

                                logging.info(f"Edificio tabular path: {edif_summary.get('totals', {})}")
                                if not edif_validation["is_valid"]:
                                    logging.error(f"Edificio validation FAILED: {edif_validation['errors']}")

                                paso1_response = rendered_paso1 + "\n\n¿Confirmás las piezas y medidas?"
                                all_warns = edif_validation.get("warnings", [])
                                errors = edif_validation.get("errors", [])
                                if errors:
                                    err_list = "\n".join(f"❌ {e}" for e in errors)
                                    paso1_response = rendered_paso1 + f"\n\n**Errores a corregir:**\n{err_list}\n\n⛔ Corregir antes de confirmar."
                                elif all_warns:
                                    ubic_warns = [w for w in all_warns if "sin ubicación" in w.lower()]
                                    m2_warns = [w for w in all_warns if "m2" in w.lower() or "m²" in w.lower()]
                                    qty_warns = [w for w in all_warns if "cantidad" in w.lower()]
                                    other_warns = [w for w in all_warns if w not in ubic_warns + m2_warns + qty_warns]
                                    parts = []
                                    if ubic_warns:
                                        parts.append(f"{len(ubic_warns)} piezas sin ubicación en planilla")
                                    if m2_warns:
                                        parts.append(f"{len(m2_warns)} diferencias de m² entre planilla y cálculo")
                                    if qty_warns:
                                        parts.append(f"{len(qty_warns)} piezas con cantidad > 1")
                                    for w in other_warns:
                                        parts.append(w)
                                    summary_text = " · ".join(parts) if parts else f"{len(all_warns)} advertencias"
                                    paso1_response = rendered_paso1 + f"\n\n*Advertencias no bloqueantes ({len(all_warns)}): {summary_text}.*\n\n¿Confirmás las piezas y medidas?"

                                import json as _json
                                pre_calc = {
                                    "building_step": "step1_review",
                                    "building_detection_mode": detection_mode,
                                    "summary": edif_summary,
                                    "validation": dict(edif_validation),
                                    "normalized_pieces": [dict(p) for s in norm_data.get("sections", []) for p in s.get("pieces", [])],
                                }

                            elif pdf_has_images:
                                # ── PATH B: VISUAL CAD EDIFICIO (new, uses Claude vision) ──
                                detection_mode = "visual_auto" if detection_mode != "manual_override" else "manual_override"
                                logging.info(f"Edificio visual CAD path (mode={detection_mode}): no tabular data, PDF has images")
                                from app.modules.quote_engine.visual_edificio_parser import (
                                    extract_visual_edificio, build_normalized_from_visual,
                                    render_visual_edificio_paso1, render_visual_edificio_choices,
                                )

                                yield {"type": "text", "content": "Analizando planos CAD con visión artificial... (puede tomar 15-30 segundos)"}

                                pages_data = await extract_visual_edificio(self.client, plan_bytes)

                                if not pages_data:
                                    yield {"type": "text", "content": "No se pudieron extraer datos del PDF. ¿Podés enviar la planilla con las medidas?"}
                                    yield {"type": "done", "content": ""}
                                    return

                                norm_data, visual_warnings, visual_blockers = build_normalized_from_visual(pages_data)

                                import json as _json
                                if visual_blockers:
                                    # Blockers (material ambiguo / failed pages) → stop and ask
                                    paso1_response = render_visual_edificio_choices(pages_data, visual_warnings, visual_blockers)

                                    # Track what the operator needs to resolve
                                    pending_actions = []
                                    if any("Material ambiguo" in b for b in visual_blockers):
                                        pending_actions.append("material_choice")
                                    if any("fallaron" in b for b in visual_blockers):
                                        pending_actions.append("failed_pages_confirmation")

                                    pre_calc = {
                                        "building_step": "awaiting_material_choice",
                                        "building_detection_mode": detection_mode,
                                        "visual_pages_raw": pages_data,
                                        "warnings": visual_warnings,
                                        "blockers": visual_blockers,
                                        "pending_actions": pending_actions,
                                        "source": "visual_cad",
                                    }
                                else:
                                    # No blockers → proceed to Paso 1 review
                                    edif_summary = compute_edificio_aggregates(norm_data)
                                    edif_validation = validate_edificio(norm_data, edif_summary)
                                    paso1_response = render_visual_edificio_paso1(
                                        pages_data, norm_data, edif_summary, visual_warnings,
                                    )
                                    paso1_response += "\n\n¿Confirmás las piezas y medidas?"

                                    pre_calc = {
                                        "building_step": "step1_review",
                                        "building_detection_mode": detection_mode,
                                        "summary": edif_summary,
                                        "validation": dict(edif_validation),
                                        "normalized_pieces_flat": [dict(p) for s in norm_data.get("sections", []) for p in s.get("pieces", [])],
                                        "visual_pages_raw": pages_data,
                                        "warnings": visual_warnings,
                                        "source": "visual_cad",
                                    }
                            else:
                                # No tables, no images — ask for planilla
                                yield {"type": "text", "content": "Detecté que es un edificio, pero el PDF no tiene tablas ni planos visibles. ¿Podés enviar la planilla con las medidas en formato tabla (Excel o CSV)?"}
                                yield {"type": "done", "content": ""}
                                return

                            # ── Common save & emit for both tabular and visual paths ──
                            try:
                                # Extract client/project from message if quote doesn't have them yet
                                _update_vals = {
                                    "is_building": True,
                                    "quote_kind": "building_parent",
                                    "quote_breakdown": pre_calc,
                                }
                                _cur_q = await db.execute(select(Quote).where(Quote.id == quote_id))
                                _cur_quote = _cur_q.scalar_one_or_none()
                                if _cur_quote:
                                    extracted = _extract_quote_info(user_message)
                                    if not (_cur_quote.client_name or "").strip() and extracted.get("client_name"):
                                        _update_vals["client_name"] = extracted["client_name"]
                                    if not (_cur_quote.project or "").strip() and extracted.get("project"):
                                        _update_vals["project"] = extracted["project"]

                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(**_update_vals)
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"Failed to save edificio pre-calc: {e}")

                            clean_user_content = [{"type": "text", "text": user_message}]
                            if plan_bytes:
                                clean_user_content.insert(0, {"type": "text", "text": "(adjunto planos edificio)"})
                            assistant_msg = {"role": "assistant", "content": [{"type": "text", "text": paso1_response}]}
                            try:
                                updated_messages = list(messages) + [
                                    {"role": "user", "content": clean_user_content},
                                    assistant_msg,
                                ]
                                await db.execute(
                                    update(Quote).where(Quote.id == quote_id).values(messages=updated_messages)
                                )
                                await db.commit()
                            except Exception as e:
                                logging.error(f"Failed to save edificio conversation: {e}")

                            yield {"type": "text", "content": paso1_response}
                            yield {"type": "done", "content": ""}
                            return  # ← EXIT: no Claude loop for edificio Paso 1
                        else:
                            # Non-edificio PDF
                            if _planilla_data:
                                # Planilla detected — send structured context instead of raw table
                                from app.modules.quote_engine.planilla_parser import build_planilla_context
                                planilla_ctx = build_planilla_context(_planilla_data)
                                content.append({"type": "text", "text": planilla_ctx})
                                logging.info(f"[planilla] Sending structured context ({len(planilla_ctx)} chars) instead of raw table")
                            else:
                                # Regular PDF — send extracted text with safety instructions
                                content.append({"type": "text", "text": f"[TEXTO EXTRAÍDO DEL PDF — DATOS EXACTOS]\n⛔ Extraído con precisión 100%. USAR TAL CUAL. Celda \"-\" o vacía = NO APLICA. NUNCA inferir ni inventar.\n\n{extracted_text.strip()}"})

                        logging.info(f"Extracted {len(extracted_text)} chars of text from PDF ({len(plan_bytes)} bytes)")
                except Exception as e:
                    logging.warning(f"pdfplumber extraction failed: {e}")

                # Pasada 2: If PDF has drawings/images, also send as document for vision
                if pdf_has_images or not extracted_text.strip():
                    if _planilla_data and _planilla_data.table_x0 > 0:
                        # Planilla: send ONLY the drawing (left side), not the full PDF
                        try:
                            from pdf2image import convert_from_bytes as _cfb
                            from app.modules.quote_engine.planilla_parser import crop_drawing_from_page
                            _plan_dpi = (ai_cfg if 'ai_cfg' in dir() else get_ai_config()).get("plan_rasterization_dpi", 300)
                            _raster_pages = _cfb(plan_bytes, dpi=_plan_dpi, first_page=1, last_page=1)
                            if _raster_pages:
                                _drawing_img = crop_drawing_from_page(_raster_pages[0], _planilla_data, dpi=_plan_dpi)
                                # Convert to JPEG bytes
                                _draw_buf = _io.BytesIO()
                                _drawing_img.save(_draw_buf, format="JPEG", quality=85)
                                _draw_bytes = _draw_buf.getvalue()
                                content.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": base64.b64encode(_draw_bytes).decode(),
                                    },
                                })
                                logging.info(f"[planilla] Sending cropped drawing only ({_drawing_img.width}x{_drawing_img.height}, {len(_draw_bytes)} bytes)")

                                # ── COTAS + SPECS: extract dimensional text + leyenda from PDF ──
                                _cotas_text = None
                                try:
                                    from app.modules.quote_engine.cotas_extractor import (
                                        extract_cotas_from_drawing,
                                        extract_specs_from_table,
                                        format_cotas_and_specs,
                                    )
                                    _cotas = extract_cotas_from_drawing(
                                        page,
                                        table_x0=_planilla_data.table_x0,
                                        dpi=_plan_dpi,
                                    )
                                    _specs = extract_specs_from_table(
                                        page,
                                        table_x0=_planilla_data.table_x0,
                                    )
                                    if _cotas or _specs:
                                        _cotas_text = format_cotas_and_specs(_cotas, _specs)
                                        logging.info(
                                            f"[cotas+specs] Injecting {len(_cotas)} cotas + "
                                            f"{len(_specs)} specs into dual read"
                                        )
                                    else:
                                        logging.info("[cotas+specs] Nothing extractable from PDF text → fallback to vision-only")
                                except Exception as e:
                                    logging.warning(f"[cotas+specs] Extraction failed, falling back to vision-only: {e}")

                                # ── DUAL READ (planilla path) — via helper ──
                                # PR #62 — skip si este turno es la confirmación del
                                # card previo. Sin esto, el re-envío del plano en el
                                # turno de confirmación disparaba un segundo dual_read
                                # que pisaba el verified_context recién guardado.
                                if _just_confirmed_dual_read:
                                    logging.info(f"[dual-read] skip (confirmation turn) for {quote_id}")
                                    _handled = False
                                    _dr_chunks = []
                                else:
                                    _extracted_cota_values_pl = [c.value for c in _cotas] if _cotas else []
                                    _handled, _dr_chunks = await _run_dual_read(
                                        db,
                                        quote_id,
                                        _draw_bytes,
                                        crop_label=_planilla_data.ubicacion or "cocina",
                                        planilla_m2=_planilla_data.m2,
                                        cotas_text=_cotas_text,
                                        extracted_cota_values=_extracted_cota_values_pl,
                                        extracted_cotas=list(_cotas or []),
                                        user_message=user_message,
                                        plan_filename=plan_filename,
                                        plan_hash=_raw_plan_hash,
                                    )
                                for _c in _dr_chunks:
                                    yield _c
                                if _handled:
                                    return

                        except Exception as e:
                            logging.warning(f"[planilla] Drawing crop failed, falling back to full PDF: {e}")
                            content.append({
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": base64.b64encode(plan_bytes).decode(),
                                },
                            })
                    else:
                        content.append({
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.b64encode(plan_bytes).decode(),
                            },
                        })
                        logging.info(f"PDF has images/drawings — sending as document for vision pass")

                    # Detect visual building: multipágina CAD with building keywords
                    # Search in: extracted text + filename + user message (operator often says "edificio X")
                    _building_keywords = ["tipolog", "cantidad", "unidad", "piso", "fideicomiso",
                                          "edificio", "obra", "cocina", "desarrollo", "lamina", "lámina",
                                          "departamento", "depto", "dpto", "ventus", "montevideo"]
                    _all_searchable = (extracted_text + " " + plan_filename + " " + user_message).lower()
                    _keyword_hits = sum(1 for kw in _building_keywords if kw in _all_searchable)
                    if num_pages >= 3 and pdf_has_images and _keyword_hits >= 2:
                        is_visual_building = True
                        logging.info(f"Visual building detected: {num_pages} pages, {_keyword_hits} keyword hits in text+filename+message")
                    elif num_pages >= 5 and pdf_has_images:
                        # 5+ pages with vector density = almost certainly a building project
                        is_visual_building = True
                        logging.info(f"Visual building detected by page count: {num_pages} pages (keywords={_keyword_hits})")

                    # PR #55 — DUAL READ para PDF sin planilla (single-cocina flow).
                    # Rasteriza página 1 a JPEG y corre dual_read. Skipea visual
                    # buildings (usan pipeline propio).
                    if pdf_has_images and not is_visual_building and not _just_confirmed_dual_read:
                        try:
                            from pdf2image import convert_from_bytes as _cfb_nopl
                            import io as _io_nopl
                            _plan_dpi_nopl = get_ai_config().get("plan_rasterization_dpi", 200)
                            _pages_nopl = _cfb_nopl(plan_bytes, dpi=_plan_dpi_nopl, first_page=1, last_page=1)
                            if _pages_nopl:
                                _buf_nopl = _io_nopl.BytesIO()
                                _pages_nopl[0].save(_buf_nopl, format="JPEG", quality=85)
                                _draw_bytes_nopl = _buf_nopl.getvalue()
                                # Extraer cotas del text layer del PDF (single-cocina sin
                                # planilla). Antes solo se extraía en el path edificio;
                                # para una planta residencial simple el cotas_text quedaba
                                # None y el LLM trabajaba 100% desde la imagen → fuente
                                # principal de errores tipo "1.75 / 2.35 inventados".
                                _cotas_nopl_text = None
                                _cotas_nopl_values: list[float] = []
                                try:
                                    import pdfplumber as _pp_nopl
                                    from app.modules.quote_engine.cotas_extractor import (
                                        extract_cotas_from_drawing,
                                        format_cotas_for_prompt,
                                    )
                                    with _pp_nopl.open(_io_nopl.BytesIO(plan_bytes)) as _pdf_nopl:
                                        if _pdf_nopl.pages:
                                            _page_nopl = _pdf_nopl.pages[0]
                                            _page_w = float(getattr(_page_nopl, "width", 0) or 1e9)
                                            _cotas_nopl = extract_cotas_from_drawing(
                                                _page_nopl,
                                                table_x0=_page_w,  # full width — no planilla
                                                dpi=_plan_dpi_nopl,
                                            )
                                            if _cotas_nopl:
                                                _cotas_nopl_text = format_cotas_for_prompt(_cotas_nopl)
                                                _cotas_nopl_values = [c.value for c in _cotas_nopl]
                                                logging.info(
                                                    f"[cotas/single-cocina] extracted {len(_cotas_nopl)} cotas "
                                                    f"from text layer: {[c.value for c in _cotas_nopl][:20]}"
                                                )
                                except Exception as _e_cot:
                                    logging.warning(f"[cotas/single-cocina] extraction failed (non-fatal): {_e_cot}")
                                _handled_nopl, _chunks_nopl = await _run_dual_read(
                                    db,
                                    quote_id,
                                    _draw_bytes_nopl,
                                    crop_label="plano",
                                    planilla_m2=None,
                                    cotas_text=_cotas_nopl_text,
                                    extracted_cota_values=_cotas_nopl_values,
                                    extracted_cotas=list(_cotas_nopl or []) if '_cotas_nopl' in locals() else [],
                                    user_message=user_message,
                                    plan_filename=plan_filename,
                                    plan_hash=_raw_plan_hash,
                                )
                                for _cc in _chunks_nopl:
                                    yield _cc
                                if _handled_nopl:
                                    return
                        except Exception as _e_nopl:
                            logging.warning(f"[dual-read] PDF sin planilla: rasterize fallback failed: {_e_nopl}")
                else:
                    logging.info(f"PDF is text-only (no images) — skipping vision pass, using extracted text only")
            else:
                media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/webp" if ext == ".webp" else "image/png"
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(plan_bytes).decode(),
                    },
                })

                # PR #55 — DUAL READ para imagen suelta (PNG/JPG/WebP).
                # Convierte a JPEG si hace falta y corre dual_read.
                # PR #62 — skip si este turno es la confirmación del card previo.
                if _just_confirmed_dual_read:
                    logging.info(f"[dual-read] skip imagen (confirmation turn) for {quote_id}")
                else:
                    try:
                        from PIL import Image as _PILImg
                        import io as _io_img
                        _img = _PILImg.open(_io_img.BytesIO(plan_bytes))
                        if _img.mode != "RGB":
                            _img = _img.convert("RGB")
                        _buf_img = _io_img.BytesIO()
                        _img.save(_buf_img, format="JPEG", quality=85)
                        _draw_bytes_img = _buf_img.getvalue()
                        _handled_img, _chunks_img = await _run_dual_read(
                            db,
                            quote_id,
                            _draw_bytes_img,
                            crop_label="plano",
                            planilla_m2=None,
                            cotas_text=None,
                            user_message=user_message,
                            plan_filename=plan_filename,
                            plan_hash=_raw_plan_hash,
                        )
                        for _cc in _chunks_img:
                            yield _cc
                        if _handled_img:
                            return
                    except Exception as _e_img:
                        logging.warning(f"[dual-read] Imagen: conversión fallback failed: {_e_img}")
                # Also send a 90° rotated version to catch margin text (configurable)
                if get_ai_config().get("rotate_plan_images", True):
                    try:
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(plan_bytes))
                        rotated = img.rotate(90, expand=True)
                        buf = io.BytesIO()
                        rotated.save(buf, format="JPEG", quality=85)
                        content.append({"type": "text", "text": "El siguiente es el MISMO plano rotado 90° para facilitar la lectura del texto en los márgenes laterales. Leé el texto de esta versión rotada (material, zócalo, frentín, etc.):"})
                        content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.b64encode(buf.getvalue()).decode(),
                            },
                        })
                        logging.info(f"Added 90° rotated version of plan for margin text reading")
                    except Exception as e:
                        logging.warning(f"Could not create rotated plan version: {e}")
        # Attach extra files (additional images sent by operator)
        # Each image gets a 90° rotated version to catch vertical cotas
        if extra_files:
            from PIL import Image
            import io
            for file_bytes, filename in extra_files:
                ext_f = Path(filename).suffix.lower()
                if ext_f == ".pdf":
                    content.append({
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(file_bytes).decode()},
                    })
                else:
                    mt = "image/jpeg" if ext_f in [".jpg", ".jpeg"] else "image/webp" if ext_f == ".webp" else "image/png"
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(file_bytes).decode()},
                    })
                    # Add 90° rotated version for vertical cotas
                    try:
                        img = Image.open(io.BytesIO(file_bytes))
                        rotated = img.rotate(90, expand=True)
                        buf = io.BytesIO()
                        rotated.save(buf, format="JPEG", quality=85)
                        content.append({
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()},
                        })
                    except Exception:
                        pass
            content.append({"type": "text", "text": f"Las imágenes de arriba incluyen cada pieza en orientación original Y rotada 90°. Si una cota no se lee bien en una versión, leerla de la otra. Comparar ambas versiones para cada pieza."})
            logging.info(f"Attached {len(extra_files)} extra files + rotated versions to message")

        # Always include a text block — Anthropic rejects empty text content blocks
        text = user_message.strip() if user_message.strip() else "(adjunto plano)"
        content.append({"type": "text", "text": text})

        # Sanitize history — remove any empty text blocks from prior messages
        clean_messages = []
        for msg in messages:
            mc = msg.get("content", "")
            if isinstance(mc, list):
                filtered = [b for b in mc if not (isinstance(b, dict) and b.get("type") == "text" and not (b.get("text") or "").strip())]
                if filtered:
                    clean_messages.append({**msg, "content": filtered})
                else:
                    clean_messages.append({**msg, "content": [{"type": "text", "text": "."}]})
            elif isinstance(mc, str) and not mc.strip():
                clean_messages.append({**msg, "content": "."})
            else:
                clean_messages.append(msg)

        # PR #379 — `clean_user_content` es lo que persiste en DB como user
        # turn. Antes era `copy.deepcopy(content)` que arrastraba TODO lo
        # que va a Claude: el plan image binary, el bloque "[TEXTO
        # EXTRAÍDO DEL PDF — DATOS EXACTOS]..." con el dump completo del
        # PDF, y los bloques "[SISTEMA — ...]" que se inyectan más abajo.
        # Ese payload no pertenece al historial de chat del operador — es
        # input interno para Claude. Al reabrir el quote se mostraba como
        # si el operador hubiera escrito todo eso.
        #
        # Ahora: el user turn en DB es SOLO el texto que escribió el
        # operador (o un placeholder "(adjuntó plano: X)" si subió un
        # plano sin texto). El content completo sigue yendo a Claude
        # intacto — esto afecta solo la persistencia.
        _text_for_db = (user_message or "").strip() or (
            f"(adjuntó plano: {plan_filename})" if plan_filename else "(adjunto plano)"
        )
        clean_user_content = [{"type": "text", "text": _text_for_db}]

        # Inject context hint based on quote state
        try:
            _ctx_q = await db.execute(select(Quote).where(Quote.id == quote_id))
            _ctx_quote = _ctx_q.scalar_one_or_none()
            if _ctx_quote and _ctx_quote.quote_breakdown:
                bd = _ctx_quote.quote_breakdown
                is_validated = _ctx_quote.pdf_url or _ctx_quote.status in (QuoteStatus.VALIDATED, QuoteStatus.SENT)
                if is_validated:
                    # Strict patch mode — only MO changes via patch_quote_mo
                    ctx_hint = (
                        f"\n[SISTEMA — MODO PATCH ACTIVO]\n"
                        f"Este presupuesto YA tiene documentos generados (material: {bd.get('material_name')}, "
                        f"total_ars: {bd.get('total_ars')}, total_usd: {bd.get('total_usd')}). "
                        f"Estás en MODO PATCH. Usá patch_quote_mo para cambios de MO (flete, colocación). "
                        f"NO volver a preguntar datos ni piezas. NO usar calculate_quote para cambios de MO."
                    )
                else:
                    # Draft with breakdown but no docs — free edit mode
                    ctx_hint = (
                        f"\n[SISTEMA — EDICIÓN LIBRE]\n"
                        f"Este presupuesto tiene un cálculo previo (material: {bd.get('material_name')}, "
                        f"total_ars: {bd.get('total_ars')}, total_usd: {bd.get('total_usd')}) pero AÚN NO tiene documentos generados.\n"
                        f"- Cambios de MO (flete, colocación) → usá patch_quote_mo\n"
                        f"- Cambios de material, piezas, medidas → usá calculate_quote (recálculo completo)\n"
                        f"NO volver a preguntar datos que ya tenés. Aplicar el cambio directo."
                    )
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            block["text"] = block["text"] + ctx_hint
                            break
        except Exception:
            pass

        # Detect multiple materials in user message → inject hint
        _msg_lower = user_message.lower() if isinstance(user_message, str) else ""
        _multi_mat_patterns = [" y ", " o ", "opción 1", "opcion 1", "alternativa", "también en ", "tambien en "]
        _material_keywords = ["silestone", "dekton", "neolith", "puraprima", "purastone", "laminatto",
                              "granito", "mármol", "marmol", "negro brasil", "carrara"]
        _mat_count = sum(1 for mk in _material_keywords if mk in _msg_lower)
        if _mat_count >= 2 and any(p in _msg_lower for p in _multi_mat_patterns):
            multi_mat_hint = (
                "\n\n[SISTEMA — MÚLTIPLES MATERIALES DETECTADOS]\n"
                "El operador pidió presupuestar más de un material en este mensaje. "
                "Llamar calculate_quote UNA VEZ POR MATERIAL, con las mismas piezas y medidas para cada uno. "
                "Cada material genera un presupuesto independiente."
            )
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["text"] = block["text"] + multi_mat_hint
                        break

        # If SINGLE plan attached, inject instruction to request separate images when multiple pieces detected
        # If multiple files attached (2+), they ARE the separate captures — process them directly
        total_files = 1 + len(extra_files or []) if has_plan else 0
        if has_plan and total_files == 1:
            multi_hint = "\n\n[SISTEMA — INSTRUCCIÓN OBLIGATORIA SOBRE PLANOS]\n⛔ ANTES de leer medidas, contá cuántas piezas hay en cuadros/boxes separados.\n⛔ Si hay 3 o más piezas en cuadros separados: PARAR. NO leer medidas. Pedir al operador capturas individuales de cada cuadro.\n⛔ Decir EXACTAMENTE: 'Veo [N] piezas en cuadros separados. Para leer bien las medidas, necesito que me mandes una captura de cada cuadro por separado.'\n⛔ NO usar read_plan, NO intentar leer del plano general, NO calcular. Solo pedir las capturas y esperar.\n⛔ Si son 1-2 piezas, podés leerlas directo."
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["text"] = block["text"] + multi_hint
                        break
        elif has_plan and total_files > 1:
            multi_read_hint = f"\n\n[SISTEMA — CAPTURAS INDIVIDUALES RECIBIDAS]\nEl operador mandó {total_files} imágenes separadas. Cada imagen es UNA pieza/cuadro individual. Leé las medidas de CADA imagen por separado. Compará la versión original y la rotada para cada pieza. NO pidas más capturas — ya las tenés todas."
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["text"] = block["text"] + multi_read_hint
                        break

        # Append user message to history (injected for Claude, clean for DB)
        # System triggers are internal — don't pass them to Claude or save as user message
        _is_system_trigger = user_message.startswith("[SYSTEM_TRIGGER:")

        # Nota: [DUAL_READ_CONFIRMED] ya fue manejado al inicio de stream_chat
        # (reasigna user_message antes de construir content). Si por algún
        # motivo el prefijo llegó hasta acá, Claude lo procesa tal cual.

        if _is_system_trigger:
            new_messages = clean_messages  # No user message for Claude
            db_messages = clean_messages   # No user message in DB
            logging.info(f"[system-trigger] {user_message} — not added to message history")
        else:
            new_messages = clean_messages + [{"role": "user", "content": content}]
            db_messages = clean_messages + [{"role": "user", "content": clean_user_content}]

        # Agentic loop with tool use
        assistant_messages = []
        # OPT-05: Per-quote cost tracking
        _total_input_tokens = 0
        _total_output_tokens = 0
        _total_cache_read = 0
        _total_cache_write = 0
        _loop_iterations = 0
        # Notify operator about processing mode
        # Detect edificio for action message
        _is_edificio_mode = False
        if has_plan and not pdf_has_images:
            # Check if edificio was detected
            try:
                from app.modules.quote_engine.edificio_parser import detect_edificio as _det
                _det_result = _det(user_message, tables_all if 'tables_all' in dir() else [])
                _is_edificio_mode = _det_result.get("is_edificio", False)
            except Exception:
                pass
            if _is_edificio_mode:
                yield {"type": "action", "content": "🏗️ Modo edificio — datos extraídos y calculados por el sistema"}
            else:
                yield {"type": "action", "content": "📄 Modo texto — planilla detectada, extracción exacta (sin Opus)"}
        elif has_plan and pdf_has_images:
            yield {"type": "action", "content": "📐 Modo plano — dibujo detectado, usando Opus para lectura visual"}
        else:
            yield {"type": "action", "content": "Leyendo catálogos y calculando..."}

        _list_pieces_called = False  # Track if list_pieces was called (guardrail for Paso 1)
        _list_pieces_retry_done = False  # Prevent infinite retry
        _last_had_visual_tool = False  # Track if previous iteration used a visual tool (read_plan)
        _suppress_text = False        # Suppress streaming text during visual tool loops
        _read_plan_calls = 0          # Count read_plan calls to enforce limit
        MAX_READ_PLAN_CALLS = 3       # Hard limit: max 3 read_plan calls per conversation
        _visual_builder_done = False  # Track if visual builder already processed

        while True:
            if _loop_iterations >= MAX_ITERATIONS:
                logging.error(f"Agent exceeded MAX_ITERATIONS ({MAX_ITERATIONS}) for quote {quote_id}")
                yield {"type": "action", "content": f"⚠️ Se alcanzó el límite de iteraciones ({MAX_ITERATIONS}). Intentá con un enunciado más simple."}
                break

            full_text = ""
            tool_uses = []

            # Model selection:
            # - Opus: first iteration with plan, OR iteration after visual tool call
            # - Sonnet: everything else (prices, MO, docs)
            OPUS_MODEL = "claude-opus-4-6"
            VISUAL_TOOLS = {"read_plan"}  # Tools that need visual context preserved
            ai_cfg = get_ai_config()
            needs_vision = has_plan and pdf_has_images

            # Show a brief status for visual PDF processing (operator sees blank otherwise)
            if needs_vision and pdf_has_images and _loop_iterations == 0:
                yield {"type": "action", "content": "📐 Analizando plano..."}
            # Use Opus on first iteration OR when previous iteration used a visual tool
            use_opus = needs_vision and (_loop_iterations == 0 or _last_had_visual_tool) and ai_cfg.get("use_opus_for_plans", True)
            current_model = OPUS_MODEL if use_opus else settings.ANTHROPIC_MODEL
            if use_opus:
                logging.info(f"Using Opus for plan reading (iteration {_loop_iterations + 1}, visual_tool_prev={_last_had_visual_tool})")
            elif has_plan and _loop_iterations == 0 and not pdf_has_images:
                logging.info(f"PDF is text-only — using Sonnet (no Opus needed)")

            # Strip plan images from messages — BUT preserve if:
            # - previous iteration used a visual tool (read_plan)
            # - auto-advancing to next page (needs PDF for zone detection)
            _should_strip = _loop_iterations > 0 and has_plan and not _last_had_visual_tool and not _auto_advance_visual
            if _should_strip:
                msgs_for_api = []
                for msg in new_messages:
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        filtered = [b for b in content if not (isinstance(b, dict) and b.get("type") in ("image", "document"))]
                        if not filtered:
                            filtered = [{"type": "text", "text": "(plano ya leído en iteración anterior)"}]
                        msgs_for_api.append({**msg, "content": filtered})
                    else:
                        msgs_for_api.append(msg)
                logging.info(f"Stripped visual content from messages (iteration {_loop_iterations + 1})")
            else:
                msgs_for_api = new_messages
                if _loop_iterations > 0 and _last_had_visual_tool:
                    logging.info(f"Preserving visual content (iteration {_loop_iterations + 1} — previous used visual tool)")

            # Retry loop for rate limit errors
            for attempt in range(MAX_RETRIES + 1):
                try:
                    # Edificio: remove list_pieces from available tools —
                    # data comes from deterministic pipeline, not list_pieces
                    active_tools = [t for t in TOOLS if t["name"] != "list_pieces"] if is_building else TOOLS

                    # Visual building: remove read_plan on first iteration to force JSON extraction
                    # Claude must use native vision on the PDF document, not call read_plan
                    # read_plan comes back in later iterations if needed for corrections/zoom
                    if is_visual_building and not _visual_builder_done:
                        active_tools = [t for t in active_tools if t["name"] != "read_plan"]

                    # Dynamic max_tokens: higher for visual PDFs (7+ láminas need space for analysis + tool_use)
                    _max_tokens = 16384 if (needs_vision and pdf_has_images) else 8096

                    async with self.client.messages.stream(
                        model=current_model,
                        max_tokens=_max_tokens,
                        system=system_prompt,
                        messages=msgs_for_api + _compact_tool_results(assistant_messages),
                        tools=active_tools,
                    ) as stream:
                        async for event in stream:
                            if hasattr(event, "type"):
                                if event.type == "content_block_delta":
                                    if hasattr(event.delta, "text"):
                                        full_text += event.delta.text
                                        # For visual PDFs: buffer ALL text until we know if this
                                        # iteration has tool calls. If it does, text is monologue
                                        # and gets suppressed. If not, it's the final response
                                        # and gets flushed in the no-tool-calls branch below.
                                        if not (needs_vision and pdf_has_images):
                                            yield {"type": "text", "content": event.delta.text}
                                        # For non-visual flows, stream text normally
                                elif event.type == "content_block_start":
                                    if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                                        tool_uses.append({
                                            "id": event.content_block.id,
                                            "name": event.content_block.name,
                                            "input": {},
                                        })

                        final_message = await stream.get_final_message()

                    # Log and accumulate token usage
                    _loop_iterations += 1
                    if hasattr(final_message, "usage"):
                        usage = final_message.usage
                        cache_read = getattr(usage, "cache_read_input_tokens", 0)
                        cache_create = getattr(usage, "cache_creation_input_tokens", 0)
                        _total_input_tokens += usage.input_tokens
                        _total_output_tokens += usage.output_tokens
                        _total_cache_read += cache_read
                        _total_cache_write += cache_create
                        logging.info(
                            f"Token usage [iter {_loop_iterations}] — input: {usage.input_tokens}, "
                            f"cache_read: {cache_read}, "
                            f"cache_create: {cache_create}, "
                            f"output: {usage.output_tokens}"
                        )

                    break  # Success — exit retry loop

                except anthropic.RateLimitError:
                    if attempt == MAX_RETRIES:
                        logging.error("Rate limit exceeded after all retries")
                        yield {"type": "action", "content": "⚠️ Servicio temporalmente no disponible. Intentá de nuevo en un minuto."}
                        yield {"type": "done", "content": ""}
                        return
                    delay = RETRY_DELAYS[attempt]
                    logging.warning(f"Rate limit hit, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    yield {"type": "action", "content": f"⏳ Esperando disponibilidad... ({delay}s)"}
                    for _ in range(delay):
                        await asyncio.sleep(1)
                        yield {"type": "ping", "content": ""}

                except anthropic.APIStatusError as e:
                    is_overloaded = e.status_code == 529 or "overloaded" in str(e).lower()
                    if is_overloaded:
                        if attempt == MAX_RETRIES:
                            logging.error(f"API overloaded after all {MAX_RETRIES} retries for quote {quote_id}. Giving up.")
                            yield {"type": "action", "content": "⚠️ Servicio sobrecargado. Intentá de nuevo en unos minutos."}
                            yield {"type": "done", "content": ""}
                            return
                        delay = RETRY_DELAYS[attempt]
                        logging.warning(f"API overloaded, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})")
                        yield {"type": "action", "content": f"⏳ Servicio ocupado, reintentando... ({delay}s)"}
                        for _ in range(delay):
                            await asyncio.sleep(1)
                            yield {"type": "ping", "content": ""}
                    elif "usage limits" in str(e).lower() or "reached your specified" in str(e).lower():
                        logging.error(f"API usage limit reached: {e}")
                        yield {"type": "text", "content": "⚠️ Se alcanzó el límite de uso de la API de Anthropic. Contactá al administrador para revisar los límites en console.anthropic.com."}
                        yield {"type": "done", "content": ""}
                        return
                    else:
                        logging.error(f"Anthropic API error: {e}")
                        yield {"type": "action", "content": f"⚠️ Error del servicio. Intentá de nuevo en unos segundos."}
                        yield {"type": "done", "content": ""}
                        return

            # ── Plan verification (skip — Opus reads the plan directly now) ──
            if False and has_plan and _loop_iterations == 1:
                try:
                    # Gather all text Valentina produced (from text blocks + tool inputs)
                    verify_text = full_text
                    # Also extract measurements from any tool call inputs (catalog_batch_lookup, calculate_quote)
                    for block in final_message.content:
                        if block.type == "tool_use" and block.input:
                            verify_text += f"\n{json.dumps(block.input, ensure_ascii=False)}"

                    if verify_text and len(verify_text) > 30:
                        from app.modules.agent.plan_verifier import verify_plan_reading
                        yield {"type": "action", "content": "Verificando lectura del plano..."}
                        corrections = await verify_plan_reading(plan_bytes, plan_filename, verify_text)
                        if corrections and corrections.get("discrepancias"):
                            # Discard Valentina's tool calls — she had wrong measurements
                            correction_text = "CORRECCIÓN DE MEDIDAS — un revisor encontró errores en tu lectura del plano:\n\n"
                            for d in corrections["discrepancias"]:
                                correction_text += f"- {d.get('pieza', '?')} {d.get('dimension', '?')}: leíste {d.get('valor_valentina')}, pero el plano dice {d.get('valor_plano')}. {d.get('correccion', '')}\n"
                            if corrections.get("medidas_correctas"):
                                correction_text += f"\nMedidas correctas verificadas: {json.dumps(corrections['medidas_correctas'], ensure_ascii=False)}"
                            correction_text += "\n\nCORREGÍ tus medidas con estos valores y recalculá todo desde cero. Usá SOLO las medidas del revisor."
                            # Add Valentina's response + correction as new messages
                            assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
                            # If there were tool calls, add fake results so message history is valid
                            tool_use_blocks_verify = [b for b in final_message.content if b.type == "tool_use"]
                            if tool_use_blocks_verify:
                                fake_results = [{"type": "tool_result", "tool_use_id": b.id, "content": '{"ok": false, "error": "Medidas incorrectas — revisor corrigió, recalcular"}'} for b in tool_use_blocks_verify]
                                assistant_messages.append({"role": "user", "content": fake_results})
                            assistant_messages.append({"role": "user", "content": [{"type": "text", "text": correction_text}]})
                            yield {"type": "text", "content": "\n\n_Corrección de medidas aplicada por el revisor._\n"}
                            logging.info(f"[plan-verifier] Injected {len(corrections['discrepancias'])} corrections for {quote_id}")
                            await asyncio.sleep(0.1)
                            continue  # Restart loop — Valentina recalculates with correct measurements
                        else:
                            logging.info(f"[plan-verifier] No discrepancies found for {quote_id}")
                except Exception as e:
                    logging.warning(f"[plan-verifier] Verification skipped: {e}")

            # ── Handle max_tokens truncation ──
            # If response was cut off by token limit, the agent may have been mid-analysis
            # or about to emit a tool_use. Continue the loop so Claude can finish.
            if getattr(final_message, "stop_reason", None) == "max_tokens":
                logging.warning(f"[max_tokens] Response truncated at iteration {_loop_iterations} — continuing loop")
                assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
                assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                    "[SISTEMA] Tu respuesta se cortó por límite de tokens. "
                    "Continuá EXACTAMENTE donde quedaste. NO repitas lo que ya dijiste. "
                    "Si ibas a ejecutar una herramienta, ejecutala ahora."
                )}]})
                await asyncio.sleep(0.1)
                continue

            # Check if we need to handle tool calls
            tool_use_blocks = [b for b in final_message.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # No tool calls — this is the final response.

                # ── Visual building pipeline: page-by-page zone detection + extraction ──
                # Only for multipágina CAD buildings (Ventus-type), NOT simple images
                if is_visual_building and full_text and not _visual_builder_done:
                    from app.modules.quote_engine.visual_quote_builder import (
                        parse_visual_extraction,
                        parse_zone_detection,
                        auto_select_zone,
                        parse_page_confirmation,
                        resolve_visual_materials,
                        validate_visual_extraction,
                        compute_visual_geometry,
                        compute_field_confidence,
                        infer_visual_services,
                        build_visual_pending_questions,
                        get_tipologias_needing_second_pass,
                        merge_second_pass,
                        parse_focused_response,
                        render_page_confirmation,
                        render_final_paso1,
                        MaterialResolution,
                        TipologiaGeometry,
                    )
                    from app.modules.agent.tools.plan_tool import read_plan as _read_plan_fn
                    import copy as _copy

                    # Load or init page-by-page state from quote_breakdown
                    try:
                        _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
                        _qt = _qr.scalar_one_or_none()
                        _bd = (_qt.quote_breakdown if _qt and _qt.quote_breakdown else {}) or {}
                    except Exception:
                        _bd = {}

                    _step = _bd.get("building_step", "")
                    _current_page = _bd.get("current_page", 1)
                    _total_pages = _bd.get("total_pages", num_pages if 'num_pages' in dir() else 1)
                    _page_data = _bd.get("page_data", {})
                    _zone_default = _bd.get("zone_default")
                    _pages_completed = _bd.get("pages_completed", [])

                    # ── Init on first entry ──
                    if not _step or _step in ("awaiting_visual_confirmation", "visual_step1_shown"):
                        # First time or re-entry: detect material + init state
                        # Try to get material from the first extraction
                        _mat_text = ""
                        _parsed_init = parse_visual_extraction(full_text)
                        if _parsed_init:
                            _mat_text = _parsed_init.get("material_text", "")
                        mat_res = resolve_visual_materials(_mat_text)
                        _bd["material_resolution"] = mat_res.to_dict()
                        _bd["total_pages"] = _total_pages
                        _bd["current_page"] = 1
                        _bd["page_data"] = {}
                        _bd["pages_completed"] = []
                        _bd["pdf_filename"] = plan_filename if plan_filename else ""
                        _current_page = 1
                        _page_data = {}
                        _pages_completed = []
                        _step = f"visual_page_{_current_page}"
                        _bd["building_step"] = _step
                        logging.info(f"[visual-pages] Init: {_total_pages} pages, material={mat_res.mode} → {mat_res.resolved}")

                    # ── Process current page state ──
                    _page_key = str(_current_page)
                    _pd = _page_data.get(_page_key, {})

                    # STEP 0A: Text extraction from full page (page 1 only)
                    # Extract material, artefactos, zócalos, quantity from the text panel
                    # This info is the same on all láminas — only need it once
                    if _current_page == 1 and "page_text_info" not in _bd:
                        try:
                            _text_crop = await _read_plan_fn(
                                _bd.get("pdf_filename", plan_filename or ""), [], page=1
                            )
                            _text_content = list(_text_crop) if isinstance(_text_crop, list) else []
                            _text_content.append({
                                "type": "text",
                                "text": (
                                    "Extraer SOLO datos de MARMOLERÍA de esta lámina. "
                                    "Responder SOLO JSON compacto con este schema exacto:\n"
                                    '{"material_text": "texto exacto de material y espesor de la sección MESADAS", '
                                    '"pileta_codes": ["sa-01", "sa-02"], '
                                    '"griferia_codes": ["gr-01"], '
                                    '"zocalo_height_cm": 7.5, '
                                    '"cantidad_unidades": 2, '
                                    '"notas": ["movemos pileta", "lateral con mármol?"]}\n'
                                    "Solo códigos de artefactos, NO descripciones largas. "
                                    "Ignorar: muebles, carpintería, herrería, instalaciones."
                                ),
                            })
                            _text_resp = await self.client.messages.create(
                                model="claude-opus-4-6",
                                max_tokens=500,  # Compact schema — only codes, no descriptions
                                system="Extraer información textual de una lámina de plano CAD. Solo JSON.",
                                messages=[{"role": "user", "content": _text_content}],
                            )
                            _text_raw = _text_resp.content[0].text if _text_resp.content else ""
                            logging.info(f"[visual-pages] Page text extraction: {_text_raw[:300]}")

                            # Parse and persist — extract material_text even if JSON truncated
                            try:
                                _page_text_info = None
                                _text_json_match = re.search(r"```json\s*(.*?)```", _text_raw, re.DOTALL)
                                _raw_json_str = _text_json_match.group(1).strip() if _text_json_match else _text_raw
                                try:
                                    _page_text_info = json.loads(_raw_json_str)
                                except json.JSONDecodeError:
                                    # JSON truncated — try to find outermost object
                                    _text_brace_match = re.search(r"\{[\s\S]*\}", _raw_json_str)
                                    if _text_brace_match:
                                        try:
                                            _page_text_info = json.loads(_text_brace_match.group(0))
                                        except json.JSONDecodeError:
                                            pass

                                # Fallback: extract material_text by regex even from truncated JSON
                                _mat_text_extracted = None
                                if _page_text_info and _page_text_info.get("material_text"):
                                    _mat_text_extracted = _page_text_info["material_text"]
                                elif not _page_text_info:
                                    _mat_match = re.search(r'"material_text"\s*:\s*"([^"]+)"', _text_raw)
                                    if _mat_match:
                                        _mat_text_extracted = _mat_match.group(1)
                                        _page_text_info = {"material_text": _mat_text_extracted}
                                        logging.info(f"[visual-pages] Extracted material_text from truncated JSON: {_mat_text_extracted}")

                                if _page_text_info:
                                    _bd["page_text_info"] = _page_text_info
                                    # Use material_text for resolution if not already set
                                    if _mat_text_extracted and not _bd.get("material_resolution"):
                                        mat_res = resolve_visual_materials(_page_text_info["material_text"])
                                        _bd["material_resolution"] = mat_res.to_dict()
                                        logging.info(f"[visual-pages] Material from text panel: {mat_res.mode} → {mat_res.resolved}")
                            except (json.JSONDecodeError, Exception) as e:
                                logging.warning(f"[visual-pages] Text extraction parse failed: {e}")
                        except Exception as e:
                            logging.error(f"[visual-pages] Text extraction failed: {e}")

                    # STEP 0B: Zone detection (pasada 0) — separate Claude call
                    if _step == f"visual_page_{_current_page}" and "detected_zones" not in _pd:
                        # Get a crop of the full page for zone detection
                        from app.modules.agent.tools.plan_tool import read_plan as _read_plan_fn
                        _pdf_fn = _bd.get("pdf_filename", plan_filename or "")
                        try:
                            page_crop = await _read_plan_fn(_pdf_fn, [], page=_current_page)
                        except Exception as e:
                            logging.error(f"[visual-pages] Page {_current_page} crop failed: {e}")
                            page_crop = []

                        zone_content = list(page_crop) if isinstance(page_crop, list) else []
                        zone_content.append({
                            "type": "text",
                            "text": "Detectar todas las zonas nombradas de esta página. Solo JSON de zones.",
                        })

                        try:
                            zone_resp = await self.client.messages.create(
                                model="claude-opus-4-6",
                                max_tokens=1500,  # 500 was too low for 4-5 zones with bbox+view_type
                                system=(
                                    "Sos un detector de zonas de planos CAD. "
                                    "Detectar TODAS las zonas nombradas de esta página: PLANTA, CORTE 1-1, CORTE 2-2, DETALLE, etc. "
                                    "Para cada zona: name, bbox [x1,y1,x2,y2] en píxeles, view_type (top_view/section/detail/unknown), confidence (0-1). "
                                    "Si no tiene nombre → ZONA-N. "
                                    "Responder ÚNICAMENTE con JSON: {\"zones\": [...]}"
                                ),
                                messages=[{"role": "user", "content": zone_content}],
                            )
                            resp_text = zone_resp.content[0].text if zone_resp.content else ""
                            logging.info(f"[visual-pages] Zone detection response: {resp_text[:200]}")
                            zones = parse_zone_detection(resp_text)
                        except Exception as e:
                            logging.error(f"[visual-pages] Zone detection call failed: {e}")
                            zones = []

                        if not zones:
                            zones = [{"name": "PÁGINA COMPLETA", "bbox": [0, 0, 700, 700], "view_type": "unknown", "confidence": 0.5}]
                        _pd["detected_zones"] = zones
                        _page_data[_page_key] = _pd
                        _bd["page_data"] = _page_data
                        logging.info(f"[visual-pages] Page {_current_page}: {len(zones)} zones detected")

                    # STEP B: Select zone (auto or operator rectangle)
                    if "detected_zones" in _pd and "selected_zone" not in _pd:
                        zones = _pd["detected_zones"]
                        _zone_default_bbox = _bd.get("zone_default_bbox")

                        # Fix G: Check if operator rectangle needed (page 1 only, ambiguous zones)
                        _needs_selector = (
                            _total_pages >= 2
                            and _current_page == 1
                            and len(zones) >= 2
                            and not any(z.get("view_type") == "top_view" and z.get("confidence", 0) >= 0.85 for z in zones)
                            and not _bd.get("zone_default")
                            and not _zone_default_bbox
                        )

                        if _needs_selector:
                            # Save page image for frontend
                            import base64 as _b64_mod
                            from app.core.static import OUTPUT_DIR
                            _img_saved = False
                            try:
                                _page_crop_for_selector = await _read_plan_fn(
                                    _bd.get("pdf_filename", plan_filename or ""), [], page=_current_page
                                )
                                for _block in (_page_crop_for_selector or []):
                                    if _block.get("type") == "image":
                                        _img_bytes = _b64_mod.b64decode(_block["source"]["data"])
                                        _img_dir = OUTPUT_DIR / quote_id
                                        _img_dir.mkdir(parents=True, exist_ok=True)
                                        _img_file = _img_dir / f"page_{_current_page}.jpg"
                                        _img_file.write_bytes(_img_bytes)
                                        _img_saved = True
                                        break
                            except Exception as e:
                                logging.error(f"[visual-pages] Failed to save page image: {e}")

                            if _img_saved:
                                _bd["building_step"] = f"visual_page_{_current_page}_zone_selector"
                                try:
                                    await db.execute(
                                        update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                                    )
                                    await db.commit()
                                except Exception as e:
                                    logging.error(f"[visual-pages] Failed to persist zone_selector state: {e}")

                                yield {"type": "zone_selector", "content": json.dumps({
                                    "image_url": f"/files/{quote_id}/page_{_current_page}.jpg",
                                    "page_num": _current_page,
                                    "instruction": "Dibujá un rectángulo sobre la zona de la mesada de mármol",
                                })}
                                yield {"type": "done", "content": ""}
                                logging.info(f"[visual-pages] Page {_current_page}: showing zone selector to operator")
                                return
                            # If image save failed, fall through to auto-select

                        selected = auto_select_zone(zones, _zone_default, _zone_default_bbox)
                        if selected:
                            _pd["selected_zone"] = selected
                            _pd["zone_was_auto"] = True
                            _page_data[_page_key] = _pd
                            _bd["page_data"] = _page_data
                            logging.info(f"[visual-pages] Page {_current_page}: auto-selected zone '{selected['name']}'")

                    # STEP C: Extract tipología from zone crop
                    if "selected_zone" in _pd and "tipologias" not in _pd:
                        zone = _pd["selected_zone"]
                        bbox = zone.get("bbox", [0, 0, 700, 700])
                        logging.info(f"[visual-pages] Cropping zone '{zone['name']}' bbox={bbox} page={_current_page}")

                        # If bbox covers less than 30% of full page → use full page instead
                        bbox_area = abs(bbox[2] - bbox[0]) * abs(bbox[3] - bbox[1])
                        page_area = 700 * 700  # Approximate full page at 200 DPI
                        if bbox_area / max(page_area, 1) < 0.30:
                            logging.warning(f"[visual-pages] bbox covers only {bbox_area/page_area*100:.0f}% — using full page crop instead")
                            crop_instructions = []  # Empty = full page thumbnail
                        else:
                            crop_instructions = [{"label": zone["name"],
                                                  "x1": bbox[0], "y1": bbox[1],
                                                  "x2": bbox[2], "y2": bbox[3]}]

                        try:
                            crop_result = await _read_plan_fn(
                                _bd.get("pdf_filename", plan_filename or ""),
                                crop_instructions,
                                page=_current_page,
                            )
                        except Exception as e:
                            logging.error(f"[visual-pages] Crop failed page {_current_page}: {e}")
                            crop_result = []

                        # Claude extracts tipología from crop
                        if crop_result:
                            extraction_content = list(crop_result) if isinstance(crop_result, list) else []
                            extraction_content.append({
                                "type": "text",
                                "text": (
                                    f"Extraer tipología de esta zona (página {_current_page}). "
                                    f"Solo JSON con tipologias. No calcular m². "
                                    f"Filtrar SOLO sección MESADAS."
                                ),
                            })

                            # Load cotas guide from disk
                            _cotas_guide = ""
                            try:
                                _cotas_path = Path(__file__).parent.parent.parent.parent / "rules" / "plan-reading-cotas.md"
                                if _cotas_path.exists():
                                    _cotas_guide = _cotas_path.read_text(encoding="utf-8")
                                    logging.info(f"[visual-pages] Cotas guide loaded: True | length={len(_cotas_guide)}")
                                else:
                                    logging.warning(f"[visual-pages] Cotas guide NOT FOUND at {_cotas_path}")
                            except Exception as e:
                                logging.warning(f"[visual-pages] Cotas guide load error: {e}")

                            _extraction_system = (
                                "Estás analizando una vista cenital (desde arriba) de una cocina.\n"
                                "En esta vista las mesadas aparecen como rectángulos sombreados pegados a las paredes.\n"
                                "Vas a ver piletas (rectángulos con óvalo), anafes (círculos sobre mesada), y cotas numéricas.\n\n"
                                "FOCALIZATE ÚNICAMENTE en la geometría de la piedra (mesada):\n"
                                "- Medir los rectángulos sombreados que representan la mesada\n"
                                "- Leer cotas que estén sobre o junto a esos rectángulos\n"
                                "- Contar piletas y anafes que estén SOBRE la mesada\n\n"
                                "NO usar medidas de:\n"
                                "- Vistas de perfil lateral (cortes) — esas muestran el mueble, no la piedra desde arriba\n"
                                "- Objetos que no son piedra: heladera, microondas, lavarropas, horno\n"
                                "- Muebles bajo mesada (melamina/carpintería)\n"
                                "- Ancho total del ambiente\n\n"
                                "Si una medida no se puede leer con claridad → marcar como ambigua.\n\n"
                                "Responder ÚNICAMENTE con JSON usando EXACTAMENTE este schema:\n"
                                '{"material_text": "...", "tipologias": [{"id": "DC-02", "qty": 2, '
                                '"shape": "L", "depth_m": 0.62, "segments_m": [2.35, 1.15], '
                                '"backsplash_ml": 4.12, "embedded_sink_count": 1, "hob_count": 1, '
                                '"notes": [], "extraction_method": "direct_read", "page": 1}]}\n\n'
                                "Reglas de campos:\n"
                                "- shape: 'L' si tiene retorno con cota visible, 'linear' si es recta, 'U' si cubre 3 paredes, 'unknown' si ambiguo\n"
                                "- segments_m: en METROS (no cm). Para L: [tramo principal, retorno]. Para linear: [largo total]. "
                                "Para U: [tramo_izq, tramo_fondo_neto, tramo_der] — fondo ya con esquinas restadas\n"
                                "- depth_m: profundidad en METROS (no cm). Típico: 0.55-0.65\n"
                                "- embedded_sink_count: piletas empotradas por unidad (leer de simbología sa-01, etc)\n"
                                "- hob_count: anafes por unidad. Mesada continua + anafe empotrado = 1\n"
                                "- extraction_method: 'direct_read' si la cota es visible, 'inferred' si se dedujo\n"
                                "- NO calcular m² — el código lo hace\n\n"
                            )
                            if _cotas_guide:
                                _extraction_system += f"GUÍA COMPLETA DE LECTURA DE COTAS:\n{_cotas_guide}\n"

                            logging.info(f"[visual-pages] Crop content blocks: {len(extraction_content)}")
                            logging.info(f"[visual-pages] Extraction system prompt length: {len(_extraction_system)}")

                            try:
                                extraction_resp = await self.client.messages.create(
                                    model="claude-opus-4-6",
                                    max_tokens=1000,
                                    system=_extraction_system,
                                    messages=[{"role": "user", "content": extraction_content}],
                                )
                                resp_text = extraction_resp.content[0].text if extraction_resp.content else ""
                                logging.info(f"[visual-pages] Extraction response raw: {resp_text[:1000]}")
                                page_parsed = parse_visual_extraction(resp_text)
                                logging.info(f"[visual-pages] parse_visual_extraction result: {page_parsed is not None}, tipologias: {len(page_parsed.get('tipologias', [])) if page_parsed else 0}")
                            except Exception as e:
                                logging.error(f"[visual-pages] Extraction failed page {_current_page}: {e}")
                                page_parsed = None

                            if page_parsed and page_parsed.get("tipologias"):
                                tips = page_parsed["tipologias"]
                                # Compute confidence + Fix C second pass within zone bbox
                                for t in tips:
                                    conf = compute_field_confidence(t)
                                    t["_confidence"] = conf.to_dict()

                                # Second pass for doubtful tipologías (within same zone crop)
                                _field_confs = {t.get("id", ""): t.get("_confidence", {}) for t in tips}
                                ids_needing = get_tipologias_needing_second_pass(tips, _field_confs)
                                for tid in ids_needing[:3]:
                                    try:
                                        existing = _copy.deepcopy(next((t for t in tips if t.get("id") == tid), {}))
                                        existing.pop("_confidence", None)
                                        focused_resp = await self.client.messages.create(
                                            model="claude-opus-4-6",
                                            max_tokens=300,
                                            system=(
                                                f"Verificar tipología {tid}. "
                                                f"Extracción anterior: {json.dumps(existing, ensure_ascii=False)}. "
                                                f"Corregir shape/segments_m/depth_m. Solo JSON."
                                            ),
                                            messages=[{"role": "user", "content": extraction_content}],
                                        )
                                        sp_text = focused_resp.content[0].text if focused_resp.content else ""
                                        sp_data = parse_focused_response(sp_text)
                                        if sp_data:
                                            tips = merge_second_pass(tips, sp_data, tid)
                                            logging.info(f"[visual-pages] Second pass {tid}: {sp_data.get('second_pass_notes', 'updated')}")
                                    except Exception as e:
                                        logging.error(f"[visual-pages] Second pass {tid} failed: {e}")

                                # Compute geometry for this page's tipologías
                                mat_res_dict = _bd.get("material_resolution", {})
                                mat_res = MaterialResolution(**mat_res_dict) if mat_res_dict else resolve_visual_materials("")
                                geo = compute_visual_geometry(tips, mat_res)

                                _pd["tipologias"] = tips
                                _pd["geometries"] = [
                                    {"id": g.id, "m2_unit": g.m2_unit, "m2_total": g.m2_total,
                                     "backsplash_ml_unit": g.backsplash_ml_unit,
                                     "backsplash_m2_total": g.backsplash_m2_total,
                                     "physical_pieces_total": g.physical_pieces_total}
                                    for g in geo.tipologias
                                ]
                            else:
                                # No tipologías extracted
                                # If using zone_default_bbox and it failed → retry or skip
                                _retries = _pd.get("zone_selector_retries", 0)
                                if _bd.get("zone_default_bbox") and _current_page > 1 and _retries < 2:
                                    logging.warning(f"[visual-pages] zone_default_bbox produced no tipologías on page {_current_page} (retry {_retries + 1}/2)")
                                    _pd["zone_default_failed"] = True
                                    _pd["zone_selector_retries"] = _retries + 1
                                    # Remove selected_zone to trigger re-selection with full page
                                    _pd.pop("selected_zone", None)
                                    _page_data[_page_key] = _pd
                                    _bd["page_data"] = _page_data
                                elif _bd.get("zone_default_bbox") and _current_page > 1 and _retries >= 2:
                                    logging.warning(f"[visual-pages] zone_default_bbox failed {_retries} times on page {_current_page} — auto-skipping")
                                    _pd["tipologias"] = []
                                    _pd["geometries"] = []
                                    _pd["confirmed"] = True
                                    _pd["skipped"] = True
                                    _page_data[_page_key] = _pd
                                    _bd["page_data"] = _page_data
                                else:
                                    _pd["tipologias"] = []
                                    _pd["geometries"] = []

                            _page_data[_page_key] = _pd
                            _bd["page_data"] = _page_data

                    # STEP D: Show page confirmation to operator
                    if "tipologias" in _pd and not _pd.get("confirmed"):
                        try:
                            tips = _pd.get("tipologias", [])
                            zone = _pd.get("selected_zone", {"name": "?"})
                            zone_auto = _pd.get("zone_was_auto", False)

                            # Build TipologiaGeometry objects for render
                            mat_res_dict = _bd.get("material_resolution", {})
                            try:
                                mat_res = MaterialResolution(**mat_res_dict) if mat_res_dict else resolve_visual_materials("")
                            except Exception as e:
                                logging.error(f"[visual-pages] MaterialResolution init failed: {e}, dict={mat_res_dict}")
                                mat_res = resolve_visual_materials("")
                            geo_full = compute_visual_geometry(tips, mat_res) if tips else None
                            geo_list = geo_full.tipologias if geo_full else []

                            confirmation_text = render_page_confirmation(
                                _current_page, _total_pages, zone, tips, geo_list, zone_auto
                            )
                            yield {"type": "text", "content": confirmation_text}
                        except Exception as e:
                            logging.error(f"[visual-pages] STEP D failed: {e}", exc_info=True)
                            yield {"type": "text", "content": f"Error procesando página {_current_page}: {str(e)}"}

                        _bd["building_step"] = f"visual_page_{_current_page}_confirm"
                        _bd["page_data"] = _page_data
                        try:
                            await db.execute(
                                update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd)
                            )
                            await db.commit()
                        except Exception as e:
                            logging.error(f"[visual-pages] Failed to persist page {_current_page}: {e}")

                        _visual_builder_done = True
                        assistant_messages.append({
                            "role": "assistant",
                            "content": _serialize_content(final_message.content),
                        })
                        break

                    # Shouldn't reach here — fallback
                    logging.warning(f"[visual-pages] Unexpected state: step={_step}, page={_current_page}")
                    yield {"type": "text", "content": full_text}

                elif needs_vision and pdf_has_images and full_text and not is_visual_building:
                    # Non-building visual PDF (simple plan, single page) — flush text
                    yield {"type": "text", "content": full_text}
                    logging.info(f"[visual-pdf] Flushed {len(full_text)} chars (non-building visual)")

                _suppress_text = False

                # ── Guardrail: Paso 1 must use list_pieces ──
                # If this is likely Paso 1 (no breakdown yet, no calculate_quote called),
                # and list_pieces was never called, force a retry with explicit instruction.
                if not _list_pieces_called and not _list_pieces_retry_done and not is_building:
                    # Skip guardrail for edificio — data comes from deterministic pipeline, not list_pieces
                    try:
                        _gq = await db.execute(select(Quote).where(Quote.id == quote_id))
                        _gquote = _gq.scalar_one_or_none()
                        _has_breakdown = _gquote and _gquote.quote_breakdown
                    except Exception:
                        _has_breakdown = True  # On error, don't block
                    # Check if any text mentions pieces/m² (Paso 1 content)
                    _resp_text = "".join(b.text for b in final_message.content if hasattr(b, "text") and b.text)
                    _looks_like_paso1 = any(kw in _resp_text.lower() for kw in ["m²", "m2", "pieza", "mesada", "confirma"])
                    if not _has_breakdown and _looks_like_paso1:
                        _list_pieces_retry_done = True
                        logging.warning(f"[guardrail] Paso 1 without list_pieces for {quote_id} — forcing retry")
                        # Inject correction and continue the loop
                        assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
                        assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                            "[SISTEMA — ERROR PASO 1] ⛔ Mostraste piezas/m² SIN llamar a list_pieces. "
                            "DEBÉS llamar list_pieces con las piezas y usar sus valores EXACTOS (labels + total_m2). "
                            "Volvé a mostrar la tabla usando list_pieces. NO calcular m² manualmente."
                        )}]})
                        _loop_iterations += 1
                        continue

                assistant_messages.append({
                    "role": "assistant",
                    "content": _serialize_content(final_message.content),
                })
                break

            # Process tool calls
            tool_results = []
            _gen_docs_result: dict | None = None
            _paso2_rendered_out: str | None = None
            for tool_use in tool_use_blocks:
                if tool_use.name == "list_pieces":
                    _list_pieces_called = True
                yield {"type": "action", "content": f"⚙️ Ejecutando: {tool_use.name}..."}
                # PR #385 — tool call con input estructurado. Ya existía un
                # log ad-hoc; ahora pasa por `log_tool_call` que normaliza
                # el prefix + formato.
                log_tool_call(quote_id, tool_use.name, tool_use.input)

                try:
                    result = await self._execute_tool(
                        tool_use.name,
                        tool_use.input,
                        quote_id=quote_id,
                        db=db,
                        conversation_history=messages,
                        current_user_message=user_message,
                    )
                except Exception as e:
                    logging.error(f"Tool execution error ({tool_use.name}): {e}", exc_info=True)
                    result = {"ok": False, "error": f"Error ejecutando {tool_use.name}: {str(e)}"}

                # Log result summary
                # PR #385 — tool result REAL. El log anterior filtraba a
                # un subset de keys (`ok/total_ars/...`) que dejaba en `{}`
                # los resultados de catalog_batch_lookup, check_architect,
                # read_plan, etc. → era imposible saber qué devolvió. Ahora
                # loguea keys + valores primitivos y fingerprint para lo
                # complejo. Full dump con DEBUG_AGENT_PAYLOADS=1.
                try:
                    log_tool_result(quote_id, tool_use.name, result)
                except Exception:
                    pass

                # ── M2 surface validator: compare list_pieces total vs planilla ──
                if tool_use.name == "list_pieces" and isinstance(result, dict) and result.get("ok"):
                    _lp_m2 = result.get("total_m2", 0)
                    if _expected_m2 is not None and _expected_m2 > 0:
                        _m2_diff = abs(_lp_m2 - _expected_m2)
                        if _m2_diff > 0.1:
                            result["_m2_validation_error"] = (
                                f"⛔ SUPERFICIE NO COINCIDE: tus piezas suman {_lp_m2:.2f} m² "
                                f"pero la planilla dice {_expected_m2:.2f} m². "
                                f"Revisá las cotas del plano y corregí las medidas."
                            )
                            logging.warning(f"[m2-validator] MISMATCH: pieces={_lp_m2:.2f} vs planilla={_expected_m2:.2f} (diff={_m2_diff:.2f})")
                        else:
                            logging.info(f"[m2-validator] OK: pieces={_lp_m2:.2f} vs planilla={_expected_m2:.2f} (diff={_m2_diff:.2f})")

                # read_plan returns native content blocks (list of image/text dicts)
                # to avoid inflating context with base64 inside JSON strings.
                # All other tools return dicts that get JSON-serialized.
                if isinstance(result, list):
                    # Native content blocks (image + text) — pass directly
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result,
                    })
                else:
                    # Capture calculate_quote's deterministic Paso 2 and strip
                    # it from what Claude sees. Si queda dentro del tool_result
                    # JSON el modelo lo parafrasea con precios alucinados
                    # (Bug G: USD 337 vs el catálogo USD 363). Lo emitimos
                    # verbatim al stream más abajo.
                    if (
                        tool_use.name == "calculate_quote"
                        and isinstance(result, dict)
                        and result.get("ok")
                        and result.get("_paso2_rendered")
                    ):
                        _paso2_rendered_out = result["_paso2_rendered"]
                        result = {k: v for k, v in result.items() if k != "_paso2_rendered"}
                    try:
                        result_json = json.dumps(result, ensure_ascii=False)
                    except (TypeError, ValueError) as e:
                        logging.error(f"JSON serialization error for tool {tool_use.name}: {e}")
                        result_json = json.dumps({"ok": False, "error": f"Error serializando resultado de {tool_use.name}"}, ensure_ascii=False)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_json,
                    })

                # Capture generate_documents result for canonical short-circuit below
                if tool_use.name == "generate_documents" and isinstance(result, dict) and result.get("ok"):
                    _gen_docs_result = result

            assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
            assistant_messages.append({"role": "user", "content": tool_results})

            # ── PASO 2 short-circuit ────────────────────────────────────────
            # Avoid letting Valentina paraphrase _paso2_rendered. El texto
            # determinístico lee el catálogo directo (fuente de verdad); el
            # LLM tiende a reescribirlo alucinando base prices (Bug G: ponía
            # USD 337 vs USD 363 del catálogo). Emitimos verbatim y cerramos
            # el turno — mismo patrón que el PASO 3 short-circuit más abajo.
            if _paso2_rendered_out:
                try:
                    yield {"type": "text", "content": _paso2_rendered_out}
                    assistant_messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": _paso2_rendered_out}],
                    })
                    break
                except Exception as _e:
                    logging.warning(f"paso2 short-circuit failed, falling back to LLM: {_e}")

            # ── PASO 3 short-circuit (single-material flow) ─────────────────
            # Avoid letting Valentina paraphrase generate_documents output
            # (she omits links / breaks long URLs across lines). Emit a
            # canonical, code-built response with all PDF/Excel/Drive links,
            # matching what the edificio flow already does.
            if _gen_docs_result is not None:
                try:
                    _lines = ["Documentos generados:", ""]
                    for _r in (_gen_docs_result.get("results") or []):
                        if not _r.get("ok"):
                            continue
                        _mat = _r.get("material") or "Material"
                        _lines.append(f"📄 **{_mat}**")
                        _pdf_drive = _r.get("drive_pdf_url")
                        _pdf_local = _r.get("pdf_url")
                        if _pdf_drive:
                            _lines.append(f"- [PDF en Drive]({_pdf_drive})")
                        elif _pdf_local:
                            _lines.append(f"- [Descargar PDF]({_pdf_local})")
                        _xls_drive = _r.get("drive_excel_url")
                        _xls_local = _r.get("excel_url")
                        if _xls_drive:
                            _lines.append(f"- [Excel en Drive]({_xls_drive})")
                        elif _xls_local:
                            _lines.append(f"- [Descargar Excel]({_xls_local})")
                        _lines.append("")
                    _wt = _gen_docs_result.get("warnings_text")
                    if _wt:
                        _lines.append(_wt)
                    _canonical = "\n".join(_lines).rstrip() + "\n"
                    yield {"type": "text", "content": _canonical}
                    assistant_messages.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": _canonical}],
                    })
                    break
                except Exception as _e:
                    logging.warning(f"paso3 short-circuit failed, falling back to LLM: {_e}")

            # Track if this iteration used visual tools (preserve context for next iteration)
            _last_had_visual_tool = any(t.name in VISUAL_TOOLS for t in tool_use_blocks)

            # Suppress text streaming during visual tool loops (hide monologue from operator)
            if _last_had_visual_tool:
                _suppress_text = True
                # Count read_plan calls and enforce limit
                for t in tool_use_blocks:
                    if t.name == "read_plan":
                        _read_plan_calls += 1
                if _read_plan_calls >= MAX_READ_PLAN_CALLS:
                    logging.warning(f"[read_plan limit] Hit {MAX_READ_PLAN_CALLS} calls — forcing analysis with what we have")
                    assistant_messages.append({"role": "assistant", "content": _serialize_content(final_message.content)})
                    assistant_messages.append({"role": "user", "content": tool_results})
                    assistant_messages.append({"role": "user", "content": [{"type": "text", "text": (
                        f"[SISTEMA] Alcanzaste el límite de {MAX_READ_PLAN_CALLS} llamadas a read_plan. "
                        "DEJÁ de hacer crops. Usá TODA la información que ya extrajiste de las páginas "
                        "y del PDF inline para dar tu análisis consolidado. Presentá: tipologías, cantidades, "
                        "medidas extraídas, material, notas, y preguntas comerciales faltantes. NO hagas más crops."
                    )}]})
                    await asyncio.sleep(0.1)
                    continue

            # Brief pause between loop iterations (minimal with Tier 1)
            await asyncio.sleep(0.1)

        # Save updated messages to DB
        try:
            updated_messages = db_messages + assistant_messages
            save_values = {"messages": updated_messages}

            # Try to extract client_name and material from conversation if not yet set
            # This ensures the dashboard shows useful info before PDF generation
            result = await db.execute(select(Quote).where(Quote.id == quote_id))
            current_quote = result.scalar_one_or_none()
            if current_quote:
                # PR #75 — skip extraction on DUAL_READ_CONFIRMED turn.
                # El early handler reemplaza user_message con un texto interno
                # ("si falta cliente o proyecto, pedilos; si ya están..."). El
                # regex de cliente matchea "cliente o proyecto" y .title() lo
                # transforma en client_name="O Proyecto", contaminando el
                # quote. En ese turno el operador NO ingresó nuevo texto;
                # client_name / project ya fueron extraídos en turnos previos.
                if _just_confirmed_dual_read:
                    extracted = {}
                    logging.info("[save] skip _extract_quote_info on DUAL_READ_CONFIRMED turn")
                else:
                    extracted = _extract_quote_info(user_message)
                # DB columns are VARCHAR(500). Truncate defensively to prevent
                # StringDataRightTruncationError when regex over-extracts a long span
                # (e.g. operator paste with no comma delimiter hitting end-of-message).
                _MAX_FIELD = 450
                _cn = (extracted.get("client_name") or "")[:_MAX_FIELD]
                _mat = (extracted.get("material") or "")[:_MAX_FIELD]
                _prj = (extracted.get("project") or "")[:_MAX_FIELD]
                # Sanitize: remove newlines and markdown noise from extracted values
                import re as _re_clean
                def _clean(s: str) -> str:
                    s = _re_clean.sub(r"[\r\n]+", " ", s)
                    s = _re_clean.sub(r"\*+", "", s)
                    return s.strip()
                if not current_quote.client_name and _cn:
                    save_values["client_name"] = _clean(_cn)[:_MAX_FIELD]
                if not current_quote.material and _mat:
                    save_values["material"] = _clean(_mat)[:_MAX_FIELD]
                if not current_quote.project and _prj:
                    save_values["project"] = _clean(_prj)[:_MAX_FIELD]

            await db.execute(
                update(Quote)
                .where(Quote.id == quote_id)
                .values(**save_values)
            )
            await db.commit()
            # PR #385 — persistencia final del turn completo (user +
            # todos los assistants del loop). Loguea la cantidad de turns
            # nuevos, preview del content y si se modificaron campos
            # derivados (client_name, material, project) del regex.
            try:
                _added_turns = [db_messages[-1]] if db_messages and db_messages[-1].get("role") == "user" else []
                _added_turns = _added_turns + list(assistant_messages or [])
                log_messages_persist(
                    quote_id,
                    flow="stream_chat-save",
                    added_turns=_added_turns,
                    total_count=len(updated_messages),
                )
                _extracted_keys = [k for k in ("client_name", "material", "project") if k in save_values]
                if _extracted_keys:
                    logging.info(
                        f"[trace:extract:{quote_id}] extracted fields from user_message: "
                        f"{ {k: save_values[k] for k in _extracted_keys} }"
                    )
            except Exception:
                pass
        except Exception as e:
            logging.error(f"Error saving conversation to DB: {e}", exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass

        # OPT-05: Per-quote cost summary + save to DB
        # Pricing: Sonnet input=$3/1M, output=$15/1M, cache_read=$0.30/1M, cache_write=$3.75/1M
        #          Opus input=$15/1M, output=$75/1M
        used_opus = has_plan  # First iteration used Opus if plan was attached
        # Approximate: treat all tokens as Sonnet pricing (Opus is only iter 0)
        cost_input = _total_input_tokens * 3.0 / 1_000_000
        cost_output = _total_output_tokens * 15.0 / 1_000_000
        cost_cache_read = _total_cache_read * 0.30 / 1_000_000
        cost_cache_write = _total_cache_write * 3.75 / 1_000_000
        total_cost = cost_input + cost_output + cost_cache_read + cost_cache_write
        # Opus surcharge for first iteration (~5x input, ~5x output)
        if used_opus and _loop_iterations > 0:
            # Rough estimate: first iteration was ~1/N of total tokens at Opus pricing
            opus_fraction = 1.0 / max(_loop_iterations, 1)
            total_cost += opus_fraction * (cost_input * 4 + cost_output * 4)  # 5x - 1x already counted

        logging.info(
            f"QUOTE COST SUMMARY [{quote_id}] — "
            f"iterations: {_loop_iterations}, "
            f"total_input: {_total_input_tokens}, "
            f"total_output: {_total_output_tokens}, "
            f"cache_read: {_total_cache_read}, "
            f"cache_write: {_total_cache_write}, "
            f"cost_usd: ${total_cost:.4f}"
        )

        # Save usage to DB
        try:
            from app.models.usage import TokenUsage
            usage_record = TokenUsage(
                quote_id=quote_id,
                input_tokens=_total_input_tokens,
                output_tokens=_total_output_tokens,
                cache_read_tokens=_total_cache_read,
                cache_write_tokens=_total_cache_write,
                model="opus+sonnet" if used_opus else "sonnet",
                cost_usd=round(total_cost, 6),
                iterations=_loop_iterations,
            )
            db.add(usage_record)
            await db.commit()
        except Exception as e:
            logging.warning(f"Could not save usage record: {e}")

        logging.info(f"[stream_chat] Yielding done for quote {quote_id}")
        log_sse_structural(quote_id, "done", "")
        yield {"type": "done", "content": ""}

    async def _execute_tool(self, name: str, inputs: dict, quote_id: str, db: AsyncSession, conversation_history: list | None = None, current_user_message: str = "") -> dict:
        logging.info(f"Tool call: {name} | quote: {quote_id}")
        if name == "list_pieces":
            # Detect is_edificio from the breakdown if persisted
            _is_edif = False
            _has_plan_ctx = False
            try:
                _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
                _q = _qr.scalar_one_or_none()
                if _q:
                    _bd = _q.quote_breakdown or {}
                    _is_edif = bool(_bd.get("is_edificio") or _bd.get("building_step"))
                    # Plano detectado: hubo read_plan previo, o hay source_files
                    # con imagen/PDF, o el breakdown lo registró.
                    _has_plan_ctx = bool(
                        _bd.get("has_plan")
                        or _bd.get("plan_read")
                        or (_q.source_files and any(
                            (sf.get("filename") or "").lower().endswith(
                                (".pdf", ".jpg", ".jpeg", ".png", ".webp")
                            )
                            for sf in (_q.source_files or [])
                            if isinstance(sf, dict)
                        ))
                    )
            except Exception:
                pass

            # PR #25 — VALIDACIÓN ESTRICTA cuando hay plano adjunto.
            # Se exige tipo explícito por pieza + coherencia dims. Texto
            # puro (DINALE, Estudio 72) sigue sin cambios.
            if _has_plan_ctx and not _is_edif:
                _errs = _validate_plan_pieces(inputs.get("pieces", []))
                if _errs:
                    return {
                        "ok": False,
                        "error": (
                            "⛔ Piezas inválidas detectadas al leer el plano. "
                            "Releer el plano con atención a los rectángulos hachurados "
                            "(zócalos) y las vistas en planta vs elevación. "
                            "Errores:\n- " + "\n- ".join(_errs)
                        ),
                    }

            result = list_pieces(inputs["pieces"], is_edificio=_is_edif)
            # ── Persist Paso 1 pieces for Paso 2 consistency guardrail ──
            try:
                _qr = await db.execute(select(Quote).where(Quote.id == quote_id))
                _q = _qr.scalar_one_or_none()
                if _q:
                    _bd = dict(_q.quote_breakdown or {})
                    _bd["paso1_pieces"] = inputs["pieces"]
                    _bd["paso1_total_m2"] = result.get("total_m2")
                    await db.execute(update(Quote).where(Quote.id == quote_id).values(quote_breakdown=_bd))
                    await db.commit()
                    logging.info(f"[paso1] Persisted {len(inputs['pieces'])} pieces, total_m2={result.get('total_m2')}")

                    # PR #412 — render determinístico del Paso 1 (gemelo
                    # de `_paso2_rendered`). Inyectamos un string markdown
                    # listo para que el LLM lo emita verbatim, evitando
                    # que recalcule m² o sume mal las filas (caso DYSCON
                    # 9,43 vs 42,39). Ver system prompt para la regla
                    # "usar `_paso1_rendered` literal".
                    try:
                        from app.modules.quote_engine.calculator import (
                            build_deterministic_paso1,
                        )
                        result["_paso1_rendered"] = build_deterministic_paso1(
                            result,
                            client_name=_q.client_name,
                            project=_q.project,
                            material=_q.material,
                        )
                    except Exception as _e_p1:
                        logging.warning(
                            f"[paso1] build_deterministic_paso1 failed: {_e_p1}"
                        )
            except Exception as e:
                logging.warning(f"[paso1] Failed to persist pieces: {e}")
            return result
        elif name == "catalog_lookup":
            return catalog_lookup(inputs["catalog"], inputs["sku"])
        elif name == "catalog_batch_lookup":
            return catalog_batch_lookup(inputs["queries"])
        elif name == "check_stock":
            return check_stock(inputs["material_sku"])
        elif name == "check_architect":
            return check_architect(inputs["client_name"])
        elif name == "read_plan":
            return await read_plan(inputs["filename"], inputs.get("crop_instructions", []))
        elif name == "generate_documents":
            import uuid as uuid_mod
            quotes_data = inputs.get("quotes", [])
            # Backward compat: if old format with quote_data, wrap it
            if not quotes_data and "quote_data" in inputs:
                quotes_data = [inputs["quote_data"]]

            logging.info(f"generate_documents: {len(quotes_data)} material(s) to generate")

            # Populate material_price_base from catalog if missing. The
            # `generate_documents` tool schema doesn't expose this field to the
            # LLM, so we look it up here to enable validate_despiece's IVA
            # check. Without this the validator emitted "Falta
            # material_price_base" for every quote (DINALE 14/04/2026).
            _backfill_material_price_base(quotes_data)

            # ── Override LLM-built fields with canonical calc_result ──────
            # Issue DINALE 15/04/2026: el LLM construía sectors, piece_details,
            # mo_items con valores propios (a veces distintos del calc_result
            # real — ej: largos de mesada inventados/redondeados, descripciones
            # truncadas a solo el código). Reemplazamos esos campos con los
            # que persistió calculate_quote en quote.quote_breakdown.
            try:
                await _canonicalize_quotes_data_from_db(quote_id, quotes_data, db)
            except Exception as _ce:
                logging.warning(
                    f"[canonical-sectors] Could not canonicalize for {quote_id}: {_ce}"
                )

            # Pre-flight checklist before generating
            all_warnings: list[str] = []
            for qdata in quotes_data:
                errors, warnings = _validate_quote_data(qdata)
                if errors:
                    error_list = "\n".join(f"❌ {e}" for e in errors)
                    return {
                        "ok": False,
                        "error": f"Pre-flight fallido para {qdata.get('material_name', '?')}:\n{error_list}\n\nCorregir estos datos antes de generar.",
                    }
                all_warnings.extend(warnings)

                # Deep deterministic validation (safety net)
                deep = validate_despiece(qdata)
                if deep.errors:
                    error_list = "\n".join(f"❌ {e}" for e in deep.errors)
                    return {
                        "ok": False,
                        "error": f"Validación profunda fallida para {qdata.get('material_name', '?')}:\n{error_list}\n\nRecalcular antes de generar.",
                    }
                all_warnings.extend(deep.warnings)

            all_results = []

            # Load current quote for context
            cur_q = await db.execute(select(Quote).where(Quote.id == quote_id))
            cur_quote = cur_q.scalar_one_or_none()

            for idx, qdata in enumerate(quotes_data):
                mat_name = (qdata.get("material_name") or "").strip().upper()
                if idx == 0:
                    target_qid = quote_id
                else:
                    # Check if calculate_quote already created a quote for this material
                    from sqlalchemy import and_
                    target_qid = None
                    try:
                        client = qdata.get("client_name", cur_quote.client_name if cur_quote else "")
                        existing = await db.execute(select(Quote).where(Quote.client_name == client))
                        for eq in existing.scalars().all():
                            eq_mat = (eq.material or "").strip().upper()
                            if eq.id != quote_id and (eq_mat == mat_name or mat_name in eq_mat or eq_mat in mat_name):
                                target_qid = eq.id
                                logging.info(f"Reusing quote {target_qid} for material: {mat_name}")
                                break
                    except Exception as e:
                        logging.warning(f"Could not search for existing quote: {e}")

                    if not target_qid:
                        target_qid = str(uuid_mod.uuid4())
                        new_quote = Quote(
                            id=target_qid,
                            client_name=qdata.get("client_name", ""),
                            project=qdata.get("project", ""),
                            material=qdata.get("material_name"),
                            messages=list(cur_quote.messages or []) if cur_quote else [],
                            status=QuoteStatus.DRAFT,
                        )
                        db.add(new_quote)
                        await db.flush()
                        logging.info(f"Created independent quote {target_qid} for material: {qdata.get('material_name')}")

                # Use DB breakdown if it exists and material matches (from calculate_quote)
                existing_bd_result = await db.execute(select(Quote).where(Quote.id == target_qid))
                existing_bd_quote = existing_bd_result.scalar_one_or_none()
                if existing_bd_quote and existing_bd_quote.quote_breakdown:
                    db_bd = existing_bd_quote.quote_breakdown
                    db_material = (db_bd.get("material_name") or "").strip().upper()
                    valentina_material = (qdata.get("material_name") or "").strip().upper()
                    if db_material == valentina_material:
                        logging.info(f"Using DB breakdown for {target_qid} (material: {db_material})")
                        qdata = db_bd

                # PR #65 + #66 — first-wins para client_name y project CON
                # excepción retroactiva: si el valor existente parece
                # placeholder/junk ("O Proyecto", "Proyecto", "Cliente",
                # "Sin nombre", etc.), lo sobreescribimos con el nuevo.
                # Eso rescata quotes viejos contaminados por drift previo.
                save_vals = {
                    "material": qdata.get("material_name"),
                    "total_ars": qdata.get("total_ars"),
                    "total_usd": qdata.get("total_usd"),
                    "quote_breakdown": qdata,
                }

                def _looks_placeholder(s: str) -> bool:
                    """¿El valor parece placeholder/junk en vez de nombre real?"""
                    if not s or not s.strip():
                        return True
                    _low = s.strip().lower()
                    _junk = {
                        "o proyecto", "proyecto", "el proyecto", "un proyecto",
                        "cliente", "el cliente", "la cliente", "sin nombre",
                        "nuevo", "nuevo presupuesto", "presupuesto", "borrador",
                        "tbd", "pendiente", "n/a", "na", "—", "-", "?", ".",
                    }
                    if _low in _junk:
                        return True
                    # Una sola letra también es placeholder (ej: "O", "X").
                    if len(_low) <= 2:
                        return True
                    return False

                _existing_cn = (existing_bd_quote.client_name if existing_bd_quote else "") or ""
                _existing_pj = (existing_bd_quote.project if existing_bd_quote else "") or ""
                _new_cn = (qdata.get("client_name") or "").strip()
                _new_pj = (qdata.get("project") or "").strip()
                # client_name: overwrite si DB vacío O si DB parece placeholder.
                if (_looks_placeholder(_existing_cn) or not _existing_cn.strip()) and _new_cn:
                    save_vals["client_name"] = _new_cn
                    if _existing_cn.strip():
                        logging.info(
                            f"[save] overwriting placeholder client_name "
                            f"'{_existing_cn}' → '{_new_cn}'"
                        )
                elif _existing_cn.strip() and _new_cn and _new_cn != _existing_cn:
                    logging.warning(
                        f"[save] generate_documents intentó cambiar client_name "
                        f"'{_existing_cn}' → '{_new_cn}' — preservando valor DB."
                    )
                # project: idem.
                if (_looks_placeholder(_existing_pj) or not _existing_pj.strip()) and _new_pj:
                    save_vals["project"] = _new_pj
                    if _existing_pj.strip():
                        logging.info(
                            f"[save] overwriting placeholder project "
                            f"'{_existing_pj}' → '{_new_pj}'"
                        )
                elif _existing_pj.strip() and _new_pj and _new_pj != _existing_pj:
                    logging.warning(
                        f"[save] generate_documents intentó cambiar project "
                        f"'{_existing_pj}' → '{_new_pj}' — preservando valor DB."
                    )
                logging.info(f"Saving quote data {target_qid}: {save_vals}")
                await db.execute(update(Quote).where(Quote.id == target_qid).values(**save_vals))

                # Generate PDF + Excel
                result = await generate_documents(target_qid, qdata)
                logging.info(f"generate_documents [{idx}] {qdata.get('material_name')}: ok={result.get('ok')}, error={result.get('error')}")

                drive_result: dict = {}
                # Read existing drive_url before overwriting (preserve if new upload fails)
                _qr = await db.execute(select(Quote).where(Quote.id == target_qid))
                _cur = _qr.scalar_one_or_none()
                existing_drive_url = _cur.drive_url if _cur else None

                first_drive_url = None
                first_drive_file_id = None
                _drive_pdf_url = None
                _drive_excel_url = None
                if result.get("ok"):
                    # Only promote status to VALIDATED on first generation
                    # (draft/pending). On regeneration (already validated/sent),
                    # preserve current status — operator controls transitions.
                    doc_values: dict = {
                        "pdf_url": result.get("pdf_url"),
                        "excel_url": result.get("excel_url"),
                    }
                    if not _cur or _cur.status in (
                        QuoteStatus.DRAFT, QuoteStatus.PENDING
                    ):
                        doc_values["status"] = QuoteStatus.VALIDATED.value
                    await db.execute(
                        update(Quote).where(Quote.id == target_qid).values(**doc_values)
                    )

                    # Upload PDF + Excel to Drive individually + build files_v2
                    # NOTE: old Drive files are deleted AFTER successful upload (not before)
                    from app.modules.agent.tools.drive_tool import upload_single_file_to_drive, delete_drive_file
                    from app.core.static import OUTPUT_DIR as _FOUT
                    old_drive_file_id = _cur.drive_file_id if _cur else None
                    files_v2_items = []
                    first_drive_url = None
                    first_drive_file_id = None
                    _drive_pdf_url = None
                    _drive_excel_url = None
                    mat_label = (qdata.get("material_name") or "").replace(" ", "_").lower()[:30]
                    subfolder = qdata.get("client_name", "")

                    for kind, url_key in [("pdf", "pdf_url"), ("excel", "excel_url")]:
                        local_url = result.get(url_key)
                        if not local_url:
                            continue
                        local_path = str(_FOUT / local_url.replace("/files/", "", 1)) if local_url.startswith("/files/") else ""
                        filename = local_url.split("/")[-1] if local_url else ""

                        drive_info = {}
                        if local_path:
                            try:
                                import os as _os_drive
                                _file_size = _os_drive.path.getsize(local_path) if _os_drive.path.exists(local_path) else -1
                                logging.info(f"Drive upload starting: {kind} | path={local_path} | size={_file_size} bytes | subfolder={subfolder}")
                                dr = await upload_single_file_to_drive(local_path, subfolder)
                                if dr.get("ok"):
                                    drive_info = {
                                        "drive_file_id": dr["file_id"],
                                        "drive_url": dr["drive_url"],
                                        "drive_download_url": dr["drive_download_url"],
                                    }
                                    if not first_drive_url:
                                        first_drive_url = dr["drive_url"]
                                        first_drive_file_id = dr["file_id"]
                                    if kind == "pdf":
                                        _drive_pdf_url = dr["drive_url"]
                                    elif kind == "excel":
                                        _drive_excel_url = dr["drive_url"]
                                    logging.info(f"Drive upload OK: {kind} | file_id={dr['file_id']} | url={dr['drive_url']}")
                                else:
                                    logging.error(f"Drive upload returned error: {kind} | {dr.get('error', 'unknown')}")
                            except Exception as e:
                                logging.error(f"Drive upload EXCEPTION for {filename}: {e}", exc_info=True)

                        files_v2_items.append({
                            "kind": kind,
                            "scope": "self",
                            "owner_quote_id": target_qid,
                            "file_key": f"{mat_label}:{kind}",
                            "filename": filename,
                            "local_path": local_path,
                            "local_url": local_url,
                            **({f"drive_{k}": v for k, v in drive_info.items()} if drive_info else {}),
                        })

                    # Delete old Drive file ONLY after new upload succeeded
                    if first_drive_url and old_drive_file_id:
                        try:
                            await delete_drive_file(old_drive_file_id)
                            logging.info(f"Deleted old Drive file {old_drive_file_id} for quote {target_qid}")
                        except Exception as e:
                            logging.warning(f"Could not delete old Drive file {old_drive_file_id}: {e}")

                    # Persist files_v2 + legacy drive_url
                    try:
                        # Re-read quote for fresh breakdown (previous commit expired _cur)
                        _fresh_r = await db.execute(select(Quote).where(Quote.id == target_qid))
                        _fresh_q = _fresh_r.scalar_one_or_none()
                        _cur_bd = dict(_fresh_q.quote_breakdown) if _fresh_q and _fresh_q.quote_breakdown else {}
                        _cur_bd["files_v2"] = {"items": files_v2_items}
                        drive_update = {"quote_breakdown": _cur_bd}
                        if first_drive_url:
                            drive_update["drive_url"] = first_drive_url
                            drive_update["drive_file_id"] = first_drive_file_id
                        if _drive_pdf_url:
                            drive_update["drive_pdf_url"] = _drive_pdf_url
                        if _drive_excel_url:
                            drive_update["drive_excel_url"] = _drive_excel_url
                        await db.execute(
                            update(Quote).where(Quote.id == target_qid).values(**drive_update)
                        )
                    except Exception as e:
                        logging.warning(f"files_v2 persist failed for {target_qid}: {e}")

                # Single atomic commit per quote — all DB changes together
                try:
                    await db.commit()
                except Exception as e:
                    logging.error(f"Failed to commit quote {target_qid}: {e}", exc_info=True)
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    return {"ok": False, "error": f"Error guardando quote: {str(e)[:200]}"}

                # Use new drive_url if upload succeeded, else preserve existing
                final_drive_url = first_drive_url or existing_drive_url
                all_results.append({
                    "quote_id": target_qid,
                    "material": qdata.get("material_name"),
                    "ok": result.get("ok", False),
                    "pdf_url": result.get("pdf_url"),
                    "excel_url": result.get("excel_url"),
                    "drive_url": final_drive_url if result.get("ok") else None,
                    "drive_pdf_url": _drive_pdf_url,
                    "drive_excel_url": _drive_excel_url,
                    "error": result.get("error"),
                })

            # PR #24 — Generar PDF de Condiciones para cada quote edificio.
            # Anexo legal/comercial separado del presupuesto (template fijo
            # de config.condiciones_edificio + plazo del quote). Best-effort:
            # si falla no aborta la generación de docs.
            for r in all_results:
                if not r.get("ok"):
                    continue
                target_qid = r["quote_id"]
                try:
                    _q_res = await db.execute(select(Quote).where(Quote.id == target_qid))
                    _q = _q_res.scalar_one_or_none()
                    if not _q or not _q.is_building:
                        continue
                    # Plazo: leer del calc_result persistido si existe
                    _bd = _q.quote_breakdown if isinstance(_q.quote_breakdown, dict) else {}
                    _plazo = _bd.get("delivery_days") or _bd.get("plazo")
                    from app.modules.agent.tools.condiciones_tool import (
                        generate_condiciones_pdf,
                    )
                    rec = await generate_condiciones_pdf(db, target_qid, plazo_override=_plazo)
                    r["condiciones_pdf_url"] = rec.get("pdf_url")
                    r["condiciones_drive_url"] = rec.get("drive_url")
                except Exception as _ce:
                    logging.warning(
                        f"[condiciones] Could not generate PDF for {target_qid}: {_ce}"
                    )

            result = {"ok": True, "generated": len(all_results), "results": all_results}
            if all_warnings:
                result["warnings"] = all_warnings
                result["warnings_text"] = "⚠️ Warnings:\n" + "\n".join(f"• {w}" for w in all_warnings)
            return result

        elif name == "update_quote":
            updates = inputs.get("updates", {})
            allowed = {"client_name", "project", "material", "total_ars", "total_usd", "status"}
            clean = {k: v for k, v in updates.items() if k in allowed and v is not None}
            if not clean:
                return {"ok": False, "error": "No hay campos válidos para actualizar"}
            logging.info(f"update_quote {quote_id}: {clean}")

            # Also update client_name/project inside the breakdown JSON
            q_result = await db.execute(select(Quote).where(Quote.id == quote_id))
            q_obj = q_result.scalar_one_or_none()
            if q_obj and q_obj.quote_breakdown:
                bd = dict(q_obj.quote_breakdown)
                changed = False
                if "client_name" in clean and bd.get("client_name") != clean["client_name"]:
                    bd["client_name"] = clean["client_name"]
                    changed = True
                if "project" in clean and bd.get("project") != clean["project"]:
                    bd["project"] = clean["project"]
                    changed = True
                if changed:
                    clean["quote_breakdown"] = bd

            await db.execute(
                update(Quote)
                .where(Quote.id == quote_id)
                .values(**clean)
            )
            await db.commit()
            return {"ok": True, "updated_fields": list(clean.keys())}
        elif name == "calculate_quote":
            save_to_qid = inputs.pop("target_quote_id", None) or quote_id

            # ── Auto-create independent quote for different material ──
            # Create a NEW quote only when operator explicitly wants alternatives
            # (quote already has docs/validated). In DRAFT without docs, overwrite
            # the same quote — operator is editing, not adding alternatives.
            try:
                check_q = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                check_quote = check_q.scalar_one_or_none()
                has_docs = check_quote and (check_quote.pdf_url or check_quote.status in ("validated", "sent"))
                if check_quote and check_quote.quote_breakdown and has_docs:
                    existing_mat = (check_quote.quote_breakdown.get("material_name") or "").strip().upper()
                    new_mat = (inputs.get("material") or "").strip().upper()
                    same_material = (
                        existing_mat == new_mat
                        or existing_mat in new_mat
                        or new_mat in existing_mat
                    )
                    if existing_mat and new_mat and not same_material:
                        # Check if an independent quote for this material already exists
                        # (same client + project + material)
                        from sqlalchemy import and_
                        existing_result = await db.execute(
                            select(Quote).where(
                                and_(
                                    Quote.client_name == (check_quote.client_name or ""),
                                    Quote.material == inputs.get("material"),
                                )
                            )
                        )
                        existing_match = None
                        for eq in existing_result.scalars().all():
                            if eq.id != save_to_qid:
                                existing_match = eq
                                break

                        if existing_match:
                            save_to_qid = existing_match.id
                            logging.info(f"Reusing existing independent quote {save_to_qid} for material {new_mat}")
                        else:
                            import uuid as _uuid
                            new_qid = str(_uuid.uuid4())
                            # Copy messages from original quote
                            new_quote = Quote(
                                id=new_qid,
                                client_name=check_quote.client_name,
                                project=check_quote.project,
                                material=inputs.get("material"),
                                messages=list(check_quote.messages or []),
                                status=QuoteStatus.DRAFT,
                            )
                            db.add(new_quote)
                            await db.flush()
                            save_to_qid = new_qid
                            logging.info(f"Created independent quote {new_qid} for material {new_mat} (original: {quote_id})")
            except Exception as e:
                logging.warning(f"Could not check material conflict for {save_to_qid}: {e}")

            # ── Defensive: preserve params from existing breakdown ──
            # If Valentina omits pileta/anafe/etc but the existing breakdown
            # had them, auto-inject UNLESS the operator explicitly asked to remove them.
            try:
                existing_q = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                existing_quote = existing_q.scalar_one_or_none()
                if existing_quote and existing_quote.quote_breakdown:
                    ebd = existing_quote.quote_breakdown
                    msg_lower = current_user_message.lower()

                    # Detect pileta from breakdown field OR from mo_items descriptions
                    existing_pileta = ebd.get("pileta")
                    if not existing_pileta:
                        # Infer from MO items if breakdown was saved without pileta field
                        for mo in ebd.get("mo_items", []):
                            desc = (mo.get("description") or "").lower()
                            if "pegado pileta" in desc or "pegadopileta" in desc:
                                existing_pileta = "empotrada_johnson"
                                break
                            elif "pileta apoyo" in desc or "agujero apoyo" in desc:
                                existing_pileta = "apoyo"
                                break
                            elif "pileta" in desc and "agujero" in desc:
                                existing_pileta = "empotrada_cliente"
                                break

                    # Detect anafe from breakdown field OR from mo_items
                    existing_anafe = ebd.get("anafe", False)
                    if not existing_anafe:
                        for mo in ebd.get("mo_items", []):
                            if "anafe" in (mo.get("description") or "").lower():
                                existing_anafe = True
                                break

                    # Check if operator is explicitly removing something
                    removing_pileta = any(kw in msg_lower for kw in ["sin pileta", "sacar pileta", "quitar pileta", "remover pileta", "sin agujero", "sacar agujero"])
                    removing_anafe = any(kw in msg_lower for kw in ["sin anafe", "sacar anafe", "quitar anafe", "remover anafe"])

                    # Auto-inject pileta if it existed and operator didn't remove it
                    if not inputs.get("pileta") and existing_pileta and not removing_pileta:
                        inputs["pileta"] = existing_pileta
                        logging.info(f"Auto-preserved pileta={existing_pileta} from existing breakdown for {save_to_qid}")

                    # Auto-inject anafe if it existed and operator didn't remove it
                    if not inputs.get("anafe") and existing_anafe and not removing_anafe:
                        inputs["anafe"] = existing_anafe
                        logging.info(f"Auto-preserved anafe={existing_anafe} from existing breakdown for {save_to_qid}")

                    # Auto-inject frentin/pulido
                    existing_frentin = ebd.get("frentin", False)
                    if not existing_frentin:
                        for mo in ebd.get("mo_items", []):
                            if "frentin" in (mo.get("description") or "").lower() or "regrueso" in (mo.get("description") or "").lower():
                                existing_frentin = True
                                break
                    if not inputs.get("frentin") and existing_frentin:
                        inputs["frentin"] = True

                    existing_pulido = ebd.get("pulido", False)
                    if not existing_pulido:
                        for mo in ebd.get("mo_items", []):
                            if "pulido" in (mo.get("description") or "").lower():
                                existing_pulido = True
                                break
                    if not inputs.get("pulido") and existing_pulido:
                        inputs["pulido"] = True

                    # Auto-inject inglete
                    if not inputs.get("inglete") and ebd.get("inglete"):
                        inputs["inglete"] = True

                    # PR #41 — carry-over de flags de MO/flete previos al
                    # recalcular. Antes solo se preservaban pileta/anafe/
                    # frentin/pulido/inglete. Con esto, 'cambiar material' o
                    # cualquier recálculo mantiene 'sin flete', '5% sobre MO',
                    # y las cantidades ya acordadas.
                    # Detect "re-add flete" operator phrases — si el operador
                    # pide reactivar el flete, no preservar el skip_flete
                    # previo (aunque ebd lo tenga en True).
                    _re_add_flete = any(kw in msg_lower for kw in [
                        "agregar flete", "volver a agregar flete", "con flete",
                        "volver flete", "re agregar flete", "poner flete",
                    ])
                    if (
                        "skip_flete" not in inputs
                        and ebd.get("skip_flete")
                        and not _re_add_flete
                    ):
                        inputs["skip_flete"] = True
                        logging.info(f"Auto-preserved skip_flete=True from breakdown for {save_to_qid}")
                    if not inputs.get("mo_discount_pct") and ebd.get("mo_discount_pct"):
                        inputs["mo_discount_pct"] = ebd["mo_discount_pct"]
                        logging.info(f"Auto-preserved mo_discount_pct={ebd['mo_discount_pct']} from breakdown for {save_to_qid}")
                    if not inputs.get("flete_qty") and ebd.get("flete_qty"):
                        inputs["flete_qty"] = ebd["flete_qty"]
                        logging.info(f"Auto-preserved flete_qty={ebd['flete_qty']} from breakdown for {save_to_qid}")
                    if not inputs.get("tomas_qty") and ebd.get("tomas_qty"):
                        inputs["tomas_qty"] = ebd["tomas_qty"]
                        logging.info(f"Auto-preserved tomas_qty={ebd['tomas_qty']} from breakdown for {save_to_qid}")
                    if not inputs.get("pileta_qty") and ebd.get("pileta_qty") and (ebd["pileta_qty"] or 0) > 1:
                        inputs["pileta_qty"] = ebd["pileta_qty"]
                        logging.info(f"Auto-preserved pileta_qty={ebd['pileta_qty']} from breakdown for {save_to_qid}")
            except Exception as e:
                logging.warning(f"Could not check existing breakdown for {save_to_qid}: {e}")

            # ── Pileta signal: structured field first, keywords fallback ──
            if not inputs.get("pileta"):
                # 1. Structured signal: read pileta field from Quote model (set by chatbot)
                try:
                    _pq = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                    _pileta_quote = _pq.scalar_one_or_none()
                    if _pileta_quote and _pileta_quote.pileta:
                        inputs["pileta"] = _pileta_quote.pileta
                        logging.info(f"Pileta from quote field: {_pileta_quote.pileta} for {save_to_qid}")
                except Exception as e:
                    logging.warning(f"Could not read pileta field from quote {save_to_qid}: {e}")

            # Gather all operator text for keyword detection (used in multiple checks)
            _pileta_all_text = current_user_message.lower()
            if conversation_history:
                for msg in conversation_history:
                    if msg.get("role") == "user":
                        c = msg.get("content", "")
                        if isinstance(c, str):
                            _pileta_all_text += " " + c.lower()
                        elif isinstance(c, list):
                            for blk in c:
                                if isinstance(blk, dict) and blk.get("type") == "text":
                                    _pileta_all_text += " " + blk.get("text", "").lower()

            # ⛔ LITERAL RULE: if operator says "sin producto de pileta" / "sin pileta
            # producto" / "cliente trae la pileta" / "D'Angelo no provee la pileta"
            # → force pileta=empotrada_cliente, regardless of what the agent passed.
            # This prevents the calculator from adding a default QUADRA Q71A sink
            # when the operator explicitly said the product is NOT included.
            _no_product_phrases = [
                "sin producto de pileta", "sin producto pileta",
                "sin pileta producto", "sin pileta-producto",
                "cliente trae la pileta", "cliente trae pileta",
                "no provee la pileta", "no provee pileta",
                "d'angelo no provee", "dangelo no provee",
                "(sin producto", "pegadopileta mo",
                # Operator explicit removal phrases (mid-conversation edit)
                "sacar pileta el producto", "sacar el producto pileta",
                "sacar el producto de pileta", "sacar producto pileta",
                "sacar producto de pileta", "sacar la pileta producto",
                "quitar pileta producto", "quitar producto pileta",
                "eliminar pileta producto", "eliminar producto pileta",
                "remover producto pileta", "remover pileta producto",
                "sin la pileta producto", "sin pileta como producto",
                # PR #41 — frases "bare" (sin la palabra 'producto').
                # Antes estas quedaban solo en `removing_pileta` (que suprime
                # auto-preserve) pero NO forzaban empotrada_cliente → el
                # producto sink seguía apareciendo en el PDF.
                "sacar pileta", "quitar pileta", "sin pileta",
                "remover pileta", "eliminar pileta", "sacar la pileta",
                "quitar la pileta", "ya no lleva pileta",
            ]
            if any(phrase in _pileta_all_text for phrase in _no_product_phrases):
                if inputs.get("pileta") != "empotrada_cliente":
                    logging.warning(
                        f"Forcing pileta=empotrada_cliente (operator said 'sin producto'). "
                        f"Was: {inputs.get('pileta')} for {save_to_qid}"
                    )
                    inputs["pileta"] = "empotrada_cliente"
                # Ensure no pileta_sku leaks through and triggers sink lookup
                inputs.pop("pileta_sku", None)

            # ── MO list authority ──────────────────────────────────────────
            # If the operator explicitly listed the MO items (markers like
            # "listá cada línea como concepto separado") and did NOT mention
            # pileta/bacha/agujero anywhere in the brief, treat the list as
            # exhaustive: no pileta product, no anafe, no colocación.
            # This prevents Valentina from hallucinating "Agujero pileta apoyo"
            # or similar MO lines that the operator did not request.
            _mo_authority_markers = [
                "listá cada línea como concepto separado",
                "lista cada linea como concepto separado",
                "listá cada línea",
                "lista cada linea",
                "listá como concepto separado",
                "lista como concepto separado",
                "listá como concepto",
                "lista como concepto",
            ]
            _has_mo_authority = any(
                m in _pileta_all_text for m in _mo_authority_markers
            )
            if _has_mo_authority:
                # Words that signal an actual pileta is requested somewhere.
                _pileta_mentions = (
                    "pileta", "bacha", "agujero pileta",
                    "pegadopileta", "pegado pileta",
                )
                _anafe_mentions = ("anafe", "agujero anafe")
                _coloc_mentions = ("colocacion", "colocación", "colocar")
                _mentions_pileta = any(
                    w in _pileta_all_text for w in _pileta_mentions
                )
                _mentions_anafe = any(
                    w in _pileta_all_text for w in _anafe_mentions
                )
                _mentions_coloc = any(
                    w in _pileta_all_text for w in _coloc_mentions
                )
                if not _mentions_pileta and inputs.get("pileta") != "empotrada_cliente":
                    logging.warning(
                        f"[mo-list-authority] Operator listed MO explicitly and "
                        f"did NOT mention pileta — forcing empotrada_cliente "
                        f"for {save_to_qid} (was: {inputs.get('pileta')})"
                    )
                    inputs["pileta"] = "empotrada_cliente"
                    inputs.pop("pileta_sku", None)
                    # PR #407 — flag de origen. El calculator usa esto para
                    # decidir si activar el fallback de pileta_qty desde
                    # mesadas (caso DYSCON: 32 mesadas → 32 piletas).
                    # Si la pileta la pasó el operador explícita, este flag
                    # NO se setea y el fallback no se activa — se respeta
                    # el `pileta_qty` del operador, incluso si es 1.
                    inputs["_pileta_inferred_by_guardrail"] = True
                if not _mentions_anafe and inputs.get("anafe"):
                    logging.warning(
                        f"[mo-list-authority] Operator listed MO explicitly and "
                        f"did NOT mention anafe — forcing anafe=False "
                        f"for {save_to_qid}"
                    )
                    inputs["anafe"] = False
                # Colocación: only suppress when the list looks exhaustive AND
                # operator didn't mention "sin colocación" explicitly (handled
                # elsewhere). If "colocación" word never appeared, assume the
                # list is complete and no colocación line was intended.
                if not _mentions_coloc and inputs.get("colocacion"):
                    logging.warning(
                        f"[mo-list-authority] Operator listed MO explicitly and "
                        f"did NOT mention colocación — forcing colocacion=False "
                        f"for {save_to_qid}"
                    )
                    inputs["colocacion"] = False

            if not inputs.get("pileta"):
                # 2. Keyword fallback: scan conversation for pileta/bacha mentions
                if any(kw in _pileta_all_text for kw in ["bacha", "pileta", "cotizar bacha", "con bacha",
                                                  "compra la bacha", "compra bacha", "compra pileta",
                                                  "la compra en", "la pide"]):
                    inputs["pileta"] = "empotrada_johnson"
                    logging.warning(f"Auto-injected pileta=empotrada_johnson from conversation keywords for {save_to_qid}")

            # ── skip_flete: detect "retiro en fábrica" / "lo busco yo" ──
            if not inputs.get("skip_flete"):
                _all_user_text = current_user_message.lower()
                if conversation_history:
                    for msg in conversation_history:
                        if msg.get("role") == "user":
                            c = msg.get("content", "")
                            if isinstance(c, str):
                                _all_user_text += " " + c.lower()
                            elif isinstance(c, list):
                                for blk in c:
                                    if isinstance(blk, dict) and blk.get("type") == "text":
                                        _all_user_text += " " + blk.get("text", "").lower()
                # PR #41 — incluir frases de EDICIÓN ('sacar/quitar/remover
                # flete', 'ya no lleva flete') además de las iniciales.
                # Antes 'sacar flete' (frase natural) no matcheaba y el flete
                # re-aparecía silenciosamente al recalcular.
                _skip_phrases = [
                    "lo retiro", "retiro yo", "retiro en", "voy a buscar", "lo busco",
                    "retira en fábrica", "retira en fabrica", "sin flete", "no necesita flete",
                    # Frases de modificación
                    "sacar flete", "quitar flete", "remover flete", "eliminar flete",
                    "sacar el flete", "quitar el flete", "ya no lleva flete",
                    "sin el flete",
                ]
                if any(phrase in _all_user_text for phrase in _skip_phrases):
                    inputs["skip_flete"] = True
                    logging.info(f"Auto-set skip_flete=True from conversation keywords for {save_to_qid}")

            # ── Flete qty override: detect explicit count in operator message ──
            # Patterns: "× 5 fletes", "x 5 fletes", "5 fletes", "flete × 5",
            #           "5 viajes", "flete × 3", "× 1 UNO SOLO", "un flete", etc.
            # Only override if the agent didn't already pass flete_qty.
            if not inputs.get("flete_qty"):
                _all_op_text = ""
                if conversation_history:
                    for _m in conversation_history:
                        if _m.get("role") == "user":
                            _c = _m.get("content", "")
                            if isinstance(_c, str):
                                _all_op_text += " " + _c
                            elif isinstance(_c, list):
                                for _b in _c:
                                    if isinstance(_b, dict) and _b.get("type") == "text":
                                        _all_op_text += " " + _b.get("text", "")
                _all_op_text += " " + (current_user_message or "")
                import re as _re_flete
                _flete_patterns = [
                    r'flete[s]?\s*[×x]\s*(\d+)',         # "flete × 5", "fletes x 5"
                    r'[×x]\s*(\d+)\s*flete',              # "× 5 fletes", "x5 fletes"
                    r'(\d+)\s*flete[s]?\b',               # "5 fletes"
                    r'(\d+)\s*viaje[s]?\b',               # "5 viajes"
                    # Digit near "flete" within a short window (handles
                    # "Flete + toma de medidas × 1 UNO SOLO" — operator writes
                    # the count far from the literal word "flete").
                    r'\bflete[s]?\b[^\n.]{0,80}?[×x]\s*(\d+)\b',
                    r'[×x]\s*(\d+)[^\n.]{0,40}?\bflete[s]?\b',
                ]
                for _pat in _flete_patterns:
                    _m_flete = _re_flete.search(_pat, _all_op_text, _re_flete.IGNORECASE)
                    if _m_flete:
                        try:
                            _fqty = int(_m_flete.group(1))
                            if 1 <= _fqty <= 50:
                                inputs["flete_qty"] = _fqty
                                logging.info(
                                    f"Auto-set flete_qty={_fqty} from operator message for {save_to_qid} "
                                    f"(pattern='{_pat}', match='{_m_flete.group(0)}')"
                                )
                                break
                        except ValueError:
                            continue

                # ── Word-number fallback for flete ──────────────────────────
                # "un flete", "dos fletes", "tres viajes", etc. — plus the
                # emphatic "uno solo" / "un solo" qualifier that operators
                # use to underline there's a SINGLE trip.
                if not inputs.get("flete_qty"):
                    _word_nums = {
                        "un": 1, "uno": 1, "una": 1,
                        "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
                        "seis": 6, "siete": 7, "ocho": 8,
                        "nueve": 9, "diez": 10,
                    }
                    for _word, _num in _word_nums.items():
                        if _re_flete.search(
                            rf'\b{_word}\s+flete[s]?\b',
                            _all_op_text, _re_flete.IGNORECASE,
                        ) or _re_flete.search(
                            rf'\b{_word}\s+viaje[s]?\b',
                            _all_op_text, _re_flete.IGNORECASE,
                        ):
                            inputs["flete_qty"] = _num
                            logging.info(
                                f"Auto-set flete_qty={_num} from word-number "
                                f"'{_word}' near flete/viaje for {save_to_qid}"
                            )
                            break

                # "× N UNO SOLO" / "× N UN SOLO" — the emphatic qualifier pins
                # to qty=1 regardless of what N is (operator wants to force
                # a single trip; the '1' is just restating it).
                if not inputs.get("flete_qty"):
                    if _re_flete.search(
                        r'\b(?:uno?|un)\s+sol[oa]\b',
                        _all_op_text, _re_flete.IGNORECASE,
                    ) and _re_flete.search(
                        r'\bflete[s]?\b', _all_op_text, _re_flete.IGNORECASE,
                    ):
                        inputs["flete_qty"] = 1
                        logging.info(
                            f"Auto-set flete_qty=1 from 'uno solo' emphasis "
                            f"near flete for {save_to_qid}"
                        )

            # ── Discount override: "Descuento N% sobre material" ─────────
            # Parse explicit material discounts from the operator brief.
            # Auto-18%-edificio only triggers when m²>=15 in the calculator;
            # smaller edificio jobs (e.g. patas x8 with 5.6m²) would lose the
            # discount even when the operator declared it literally. This
            # block honors "Descuento 18%" regardless of m².
            # Similarly captures "5% sobre MO" for mo_discount_pct.
            if not inputs.get("discount_pct") or not inputs.get("mo_discount_pct"):
                _disc_text = ""
                if conversation_history:
                    for _m in conversation_history:
                        if _m.get("role") == "user":
                            _c = _m.get("content", "")
                            if isinstance(_c, str):
                                _disc_text += " " + _c
                            elif isinstance(_c, list):
                                for _b in _c:
                                    if isinstance(_b, dict) and _b.get("type") == "text":
                                        _disc_text += " " + _b.get("text", "")
                _disc_text += " " + (current_user_message or "")
                import re as _re_disc

                # Material discount — "Descuento 18% sobre material",
                # "18% de descuento sobre material", "descuento edificio 18%"
                if not inputs.get("discount_pct"):
                    _mat_patterns = [
                        r'descuento[^\n.]{0,30}?(\d{1,2})\s*%[^\n.]{0,30}?(?:sobre\s+)?material',
                        r'(\d{1,2})\s*%[^\n.]{0,30}?(?:de\s+)?descuento[^\n.]{0,30}?(?:sobre\s+)?material',
                        r'(\d{1,2})\s*%\s+sobre\s+(?:total\s+)?material',
                        r'descuento\s+edificio\s+(\d{1,2})\s*%',
                    ]
                    for _pat in _mat_patterns:
                        _m_disc = _re_disc.search(_pat, _disc_text, _re_disc.IGNORECASE)
                        if _m_disc:
                            try:
                                _pct = int(_m_disc.group(1))
                                if 1 <= _pct <= 50:
                                    inputs["discount_pct"] = _pct
                                    logging.info(
                                        f"Auto-set discount_pct={_pct} from operator text "
                                        f"for {save_to_qid} (pattern='{_pat}', "
                                        f"match='{_m_disc.group(0)[:60]}...')"
                                    )
                                    break
                            except ValueError:
                                continue

                # MO discount — "5% sobre MO", "descuento 5% sobre mano de obra",
                # y también "sobre PEGADOPILETA" / "sobre pileta" / "sobre pegado
                # pileta" / "sobre subtotal PEGADOPILETA" (scope invariante: el
                # descuento SIEMPRE aplica a todo MO excepto flete, sin importar
                # cómo lo enuncie el operador — ver rules/quote-process-buildings.md).
                if not inputs.get("mo_discount_pct"):
                    _mo_patterns = [
                        r'(\d{1,2})\s*%\s+sobre\s+(?:la\s+)?(?:mo\b|mano\s+de\s+obra)',
                        r'descuento[^\n.]{0,30}?(\d{1,2})\s*%[^\n.]{0,30}?(?:mo\b|mano\s+de\s+obra)',
                        r'(\d{1,2})\s*%\s+sobre\s+(?:subtotal\s+)?(?:el\s+)?pegadopileta',
                        r'(\d{1,2})\s*%\s+sobre\s+(?:subtotal\s+)?(?:el\s+)?pegado\s+pileta',
                        r'descuento[^\n.]{0,40}?(\d{1,2})\s*%[^\n.]{0,40}?pegadopileta',
                        r'descuento[^\n.]{0,40}?(\d{1,2})\s*%[^\n.]{0,40}?pegado\s+pileta',
                    ]
                    for _pat in _mo_patterns:
                        _m_mo = _re_disc.search(_pat, _disc_text, _re_disc.IGNORECASE)
                        if _m_mo:
                            try:
                                _pct_mo = int(_m_mo.group(1))
                                if 1 <= _pct_mo <= 50:
                                    inputs["mo_discount_pct"] = _pct_mo
                                    logging.info(
                                        f"Auto-set mo_discount_pct={_pct_mo} from "
                                        f"operator text for {save_to_qid} "
                                        f"(pattern='{_pat}', match='{_m_mo.group(0)[:60]}...')"
                                    )
                                    break
                            except ValueError:
                                continue

            # ── Agujero de toma corriente — operator-declared qty ──────────
            # Caso DINALE 14/04/2026: brief dice "Agujero de toma × 1 unidad"
            # pero el calculator solo detectaba toma via heurística de zócalo
            # alto/revestimiento. Sin override explícito, el ítem se dropeaba.
            if not inputs.get("tomas_qty"):
                import re as _re_toma
                _toma_text = _disc_text if '_disc_text' in dir() else ""
                if not _toma_text and conversation_history:
                    for _m in conversation_history:
                        if _m.get("role") == "user":
                            _c = _m.get("content", "")
                            if isinstance(_c, str):
                                _toma_text += " " + _c
                            elif isinstance(_c, list):
                                for _b in _c:
                                    if isinstance(_b, dict) and _b.get("type") == "text":
                                        _toma_text += " " + _b.get("text", "")
                    _toma_text += " " + (current_user_message or "")
                _toma_patterns = [
                    r'agujero\s+(?:de\s+)?toma(?:s)?\s*(?:de\s+corriente)?[^\n]{0,30}?[×x]\s*(\d{1,2})',
                    r'agujero\s+(?:de\s+)?toma(?:s)?\s*(?:de\s+corriente)?[^\n]{0,30}?(\d{1,2})\s+unidad',
                    r'(\d{1,2})\s+agujero(?:s)?\s+(?:de\s+)?toma',
                ]
                for _pat in _toma_patterns:
                    _m_toma = _re_toma.search(_pat, _toma_text, _re_toma.IGNORECASE)
                    if _m_toma:
                        try:
                            _qty_toma = int(_m_toma.group(1))
                            if 1 <= _qty_toma <= 50:
                                inputs["tomas_qty"] = _qty_toma
                                logging.info(
                                    f"Auto-set tomas_qty={_qty_toma} from operator "
                                    f"text for {save_to_qid} "
                                    f"(match='{_m_toma.group(0)[:60]}...')"
                                )
                                break
                        except ValueError:
                            continue

            # ── Paso 1 ↔ Paso 2 consistency guardrail ──
            # Two layers:
            #   A) paso1_pieces persisted by list_pieces (residencial — list_pieces siempre se llama)
            #   B) operator_declared_m2 parseado del texto del operador (edificios — list_pieces deshabilitado)
            try:
                _gq = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                _gquote = _gq.scalar_one_or_none()
                if _gquote:
                    _gbd = _gquote.quote_breakdown or {}

                    # PR #25 — detectar si hay plano adjunto en el contexto.
                    # Cuando hay plano, residencial (is_edificio=False) NO
                    # permite m2_override: se debe reconstruir desde medidas.
                    _has_plan_ctx = bool(
                        _gbd.get("has_plan")
                        or _gbd.get("plan_read")
                        or (_gquote.source_files and any(
                            (sf.get("filename") or "").lower().endswith(
                                (".pdf", ".jpg", ".jpeg", ".png", ".webp")
                            )
                            for sf in (_gquote.source_files or [])
                            if isinstance(sf, dict)
                        ))
                    )
                    _is_edif_ctx = bool(inputs.get("is_edificio"))
                    if _has_plan_ctx and not _is_edif_ctx:
                        _override_pieces = [
                            (p.get("description") or "?")
                            for p in inputs.get("pieces", [])
                            if p.get("m2_override") is not None
                        ]
                        if _override_pieces:
                            return {
                                "ok": False,
                                "error": (
                                    "⛔ m2_override está prohibido en presupuestos "
                                    "residenciales con plano adjunto. El m² debe "
                                    "reconstruirse desde las medidas del plano "
                                    "(largo × prof por cada pieza, zócalos como "
                                    "ml × alto). Piezas con override: "
                                    + ", ".join(_override_pieces)
                                ),
                            }

                    # Calculate m2 of what Claude is trying to pass now.
                    # If a piece declares m2_override (operator's Planilla de
                    # Cómputo), that value takes precedence over largo×prof —
                    # matches calculator.calculate_m2 semantics so the
                    # guardrail does not flag override-based quotes.
                    _current_m2 = 0
                    _uses_override = False
                    for _p in inputs.get("pieces", []):
                        _pq = _p.get("quantity", 1) or 1
                        _ovr = _p.get("m2_override")
                        if _ovr is not None:
                            try:
                                _ovr_val = float(_ovr)
                            except (TypeError, ValueError):
                                _ovr_val = 0
                            if _ovr_val > 0:
                                _current_m2 += _ovr_val * _pq
                                _uses_override = True
                                continue
                        _pl = _p.get("largo", 0) or 0
                        _pp = _p.get("prof", 0) or _p.get("dim2", 0) or _p.get("alto", 0) or 0
                        _current_m2 += _pl * _pp * _pq

                    # Layer A: residencial (list_pieces persisted)
                    _paso1_pieces = _gbd.get("paso1_pieces")
                    _paso1_m2 = _gbd.get("paso1_total_m2") or 0
                    if _paso1_pieces:
                        _diff_m2 = abs(_current_m2 - _paso1_m2)
                        _diff_count = abs(len(inputs.get("pieces", [])) - len(_paso1_pieces))
                        # PR #25 — tolerancia ajustada a max(0.05 m², 2% del
                        # declarado). Antes 0.5 absolutos era demasiado laxo:
                        # un 2.50 vs 2.00 pasaba sin flag.
                        _a_tol = max(0.05, (_paso1_m2 or 1) * 0.02)
                        if _diff_m2 > _a_tol or _diff_count > 0:
                            logging.error(
                                f"[guardrail-A] PASO1↔PASO2 mismatch for {save_to_qid}: "
                                f"paso1={len(_paso1_pieces)}p/{_paso1_m2:.2f}m² "
                                f"vs paso2={len(inputs.get('pieces', []))}p/{_current_m2:.2f}m² "
                                f"(tol={_a_tol:.3f}). OVERRIDING with paso1 pieces."
                            )
                            inputs["pieces"] = _paso1_pieces

                    # Layer B: edificios — parse operator text for declared m²
                    # Examples: "TOTAL MATERIAL: 66.57 m²", "Total: 74.10 m²", "Subtotal: 58.66 m²"
                    import re as _re_m2op
                    _op_text = ""
                    if conversation_history:
                        for _m in conversation_history:
                            if _m.get("role") == "user":
                                _c = _m.get("content", "")
                                if isinstance(_c, str):
                                    _op_text += " " + _c
                                elif isinstance(_c, list):
                                    for _b in _c:
                                        if isinstance(_b, dict) and _b.get("type") == "text":
                                            _op_text += " " + _b.get("text", "")
                    _op_text += " " + (current_user_message or "")

                    _total_patterns = [
                        r'total\s+material[:\s]+([\d.,]+)\s*m[²2]',
                        r'material\s+total[:\s]+([\d.,]+)\s*m[²2]',
                        r'total[:\s]+([\d.,]+)\s*m[²2]',
                    ]
                    _declared_m2 = None
                    for _pat in _total_patterns:
                        _m = _re_m2op.search(_pat, _op_text, _re_m2op.IGNORECASE)
                        if _m:
                            try:
                                _declared_m2 = float(_m.group(1).replace(".", "").replace(",", ".")
                                                     if _m.group(1).count(",") == 1 and _m.group(1).count(".") > 1
                                                     else _m.group(1).replace(",", "."))
                                break
                            except ValueError:
                                continue

                    if _declared_m2 and _declared_m2 > 1:
                        _diff_op = abs(_current_m2 - _declared_m2)
                        _diff_pct = _diff_op / _declared_m2
                        # Abort only on significant mismatch (>10% or >2m²)
                        if _diff_pct > 0.10 and _diff_op > 2.0:
                            logging.error(
                                f"[guardrail-B] Operator declared {_declared_m2:.2f} m² but agent is "
                                f"passing {_current_m2:.2f} m² ({_diff_pct*100:.0f}% diff). ABORTING calculate_quote."
                            )
                            # Return error to agent so it re-reads the message
                            return {
                                "ok": False,
                                "error": (
                                    f"⛔ El despiece que pasaste a calculate_quote ({_current_m2:.2f} m²) "
                                    f"NO coincide con el total declarado por el operador ({_declared_m2:.2f} m²). "
                                    "Re-leer el mensaje ORIGINAL del operador (NO los ejemplos) y pasar "
                                    "EXACTAMENTE las piezas listadas ahí. En edificio son múltiples tipologías "
                                    "(DC-02 × 2, DC-03 × 6, etc.), NO inventes datos residenciales."
                                ),
                                "_guardrail_aborted": True,
                                "_current_m2": _current_m2,
                                "_declared_m2": _declared_m2,
                            }
            except Exception as e:
                logging.warning(f"[guardrail] paso1↔paso2 check failed: {e}")

            calc_result = calculate_quote(inputs)

            # ── Surface variant negations from the brief (PR #10) ──────────
            # El LLM normaliza el material name antes de pasarlo a
            # calculate_quote, por lo que `_find_material` no ve frases como
            # "NO Extra 2" / "sin Fiamatado" del brief original. Detectamos
            # acá esas negaciones desde el conversation_history y, si la
            # variante devuelta coincide con la que el operador negó,
            # agregamos un warning visible al render del Paso 2.
            if calc_result.get("ok"):
                _neg_text = (current_user_message or "").lower()
                if conversation_history:
                    for _m in conversation_history:
                        if _m.get("role") == "user":
                            _c = _m.get("content", "")
                            if isinstance(_c, str):
                                _neg_text += " " + _c.lower()
                            elif isinstance(_c, list):
                                for _b in _c:
                                    if isinstance(_b, dict) and _b.get("type") == "text":
                                        _neg_text += " " + _b.get("text", "").lower()
                import re as _re_neg
                _neg_patterns = [
                    (r'\bno\s+extra\s*2\b', "extra 2"),
                    (r'\bsin\s+extra\s*2\b', "extra 2"),
                    (r'\b(?:no|sin)\s+fiamatado\b', "fiamatado"),
                    (r'\b(?:no|sin)\s+flameado\b', "flameado"),
                    (r'\b(?:no|sin)\s+leather\b', "leather"),
                    (r'\b(?:no|sin)\s+pulido\b', "pulido"),
                ]
                _matched_name_lower = (calc_result.get("material_name") or "").lower()

                def _has_affirmative_mention(kw: str, text: str) -> bool:
                    """¿El kw aparece al menos una vez en `text` sin estar
                    inmediatamente precedido por 'no ' o 'sin '?

                    Maneja variantes multi-palabra (ej: "extra 2") y caracteres
                    no-palabra alrededor (dash, guión, punto, paréntesis).
                    Ejemplos que retornan True:
                      - "GRANITO GRIS MARA EXTRA 2 ESP"
                      - "granito gris mara - 20mm extra 2 esp"
                      - "mara (extra 2) 20mm"
                    Ejemplos que retornan False:
                      - "mara sin extra 2, quiero fiamatado"
                      - "NO Extra 2" (único match, todo negado)
                    """
                    kw_escaped = _re_neg.escape(kw).replace(r'\ ', r'\s+')
                    # Match con word boundary flexible: cualquier char no-palabra
                    # antes/después (incluye inicio/fin de string).
                    kw_regex = r'(?<![A-Za-z0-9])' + kw_escaped + r'(?![A-Za-z0-9])'
                    for _m in _re_neg.finditer(kw_regex, text):
                        _start = _m.start()
                        # Mirar los ~6 chars antes: si hay "no " o "sin " justo
                        # antes del kw, esa ocurrencia es negada. Si al menos una
                        # ocurrencia NO está negada → afirmativa → True.
                        _prefix = text[max(0, _start - 6):_start]
                        if not _re_neg.search(r'\b(no|sin)\s+$', _prefix):
                            return True
                    return False

                for _pat, _kw in _neg_patterns:
                    if not _re_neg.search(_pat, _neg_text):
                        continue
                    if _kw not in _matched_name_lower:
                        continue
                    # PR #47 — suprimir falso positivo: si el operador menciona
                    # el kw afirmativamente en algún lado del brief, claramente
                    # quiere esa variante. Casos cubiertos:
                    #   - "GRANITO GRIS MARA EXTRA 2 ESP" → afirmativo
                    #   - "mara - 20mm - extra 2 esp" → afirmativo (dashes OK)
                    #   - "no dejar extra 2 mm pero SI Extra 2 ESP" → afirmativo
                    # Casos que siguen firing:
                    #   - "Mara, NO Extra 2, quiero fiamatado" → todas negadas
                    if _has_affirmative_mention(_kw, _neg_text):
                        logging.info(
                            f"[variant-negated-agent] SUPPRESSED: '{_kw}' "
                            f"aparece afirmativamente en brief → operador "
                            f"pidió esta variante explícito, no es negada."
                        )
                        break
                    _w = (
                        f"⚠️ VARIANT NEGADA: el operador escribió "
                        f"'{_kw}' en el brief negándola, pero el catálogo "
                        f"solo tiene '{calc_result['material_name']}' como "
                        "opción. Se cotiza con esa variante — confirmar "
                        "con operador antes de generar PDF."
                    )
                    existing = calc_result.setdefault("warnings", [])
                    if _w not in existing:
                        existing.append(_w)
                    logging.warning(
                        f"[variant-negated-agent] '{_kw}' negado por brief "
                        f"pero match es '{calc_result['material_name']}' "
                        f"para {save_to_qid}"
                    )
                    break

            # ── Post-calculate deterministic validation ──
            if calc_result.get("ok"):
                validation = validate_despiece(calc_result)
                if not validation.ok:
                    calc_result["_validation_errors"] = validation.errors
                    calc_result["_validation_warnings"] = validation.warnings
                    calc_result["_validation_note"] = (
                        "⚠️ ERRORES DE VALIDACIÓN DETECTADOS. "
                        "Corregir los datos y volver a calcular con calculate_quote. "
                        "NO llamar a generate_documents hasta resolver estos errores."
                    )
                    logging.warning(f"Validation FAILED for {save_to_qid}: {validation.errors}")
                else:
                    if validation.warnings:
                        calc_result["_validation_warnings"] = validation.warnings
                    calc_result["_review_checklist"] = (
                        "ANTES de llamar a generate_documents, revisá:\n"
                        "1. ¿Las piezas coinciden con lo que pidió el operador?\n"
                        "2. ¿El material es correcto?\n"
                        "3. ¿Pileta/anafe/colocación coinciden con el pedido?\n"
                        "4. ¿Los m² tienen sentido para las medidas dadas?\n"
                        "5. ¿El flete es para la zona correcta?"
                    )

                # Build deterministic Paso 2 text — Claude must use this verbatim
                from app.modules.quote_engine.calculator import build_deterministic_paso2
                calc_result["_paso2_rendered"] = build_deterministic_paso2(calc_result)
                logging.info(f"Deterministic Paso 2 built for {save_to_qid} ({len(calc_result['_paso2_rendered'])} chars)")

            # Persist breakdown + change history to DB
            if calc_result.get("ok"):
                try:
                    # Build change log entry
                    old_q = await db.execute(select(Quote).where(Quote.id == save_to_qid))
                    old_quote = old_q.scalar_one_or_none()
                    change_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "action": "calculate_quote",
                        "material": calc_result.get("material_name"),
                        "total_ars_before": old_quote.total_ars if old_quote else None,
                        "total_usd_before": old_quote.total_usd if old_quote else None,
                        "total_ars_after": calc_result.get("total_ars"),
                        "total_usd_after": calc_result.get("total_usd"),
                        "user_message": current_user_message[:200],
                    }
                    # Append to existing history
                    history = list(old_quote.change_history or []) if old_quote else []
                    history.append(change_entry)

                    # PR #19 — propagar is_edificio del calc_result a la
                    # columna is_building del Quote para que el dashboard
                    # muestre el badge OBRA en edificios single-material
                    # (DINALE, Estudio 72 individual, etc.). Antes solo se
                    # marcaba en el flow building_parent multi-material.
                    #
                    # Preservar keys de dual_read que el reemplazo completo
                    # de calc_result borraba (causaba que al confirmar Paso 2
                    # el dual_read corriera de nuevo y apareciera otra card).
                    _merged_bd = dict(calc_result)
                    if old_quote and isinstance(old_quote.quote_breakdown, dict):
                        for _keep_key in (
                            "dual_read_result", "verified_measurements",
                            "verified_context", "dual_read_planilla_m2",
                            "dual_read_crop_label", "files_v2",
                        ):
                            if _keep_key in old_quote.quote_breakdown and _keep_key not in _merged_bd:
                                _merged_bd[_keep_key] = old_quote.quote_breakdown[_keep_key]

                    _values = {
                        "quote_breakdown": _merged_bd,
                        "total_ars": calc_result.get("total_ars"),
                        "total_usd": calc_result.get("total_usd"),
                        "material": calc_result.get("material_name"),
                        "change_history": history,
                    }
                    if calc_result.get("is_edificio"):
                        _values["is_building"] = True
                    await db.execute(
                        update(Quote).where(Quote.id == save_to_qid).values(**_values)
                    )
                    await db.commit()
                    logging.info(f"Saved breakdown for {save_to_qid} after calculate_quote | ARS: {change_entry['total_ars_before']} → {change_entry['total_ars_after']}")
                    # PR #385 — diff del breakdown post-calculate_quote. Clave
                    # para detectar qué piezas/totales se persistieron vs qué
                    # había antes. Si acá el input del tool dice isla=1.80 pero
                    # el breakdown tiene isla=2.03 → bug en el calculador.
                    try:
                        from app.modules.agent._trace import log_bd_mutation
                        log_bd_mutation(
                            save_to_qid,
                            "calculate-quote-save",
                            old_quote.quote_breakdown if old_quote else {},
                            _merged_bd,
                        )
                    except Exception:
                        pass
                except Exception as e:
                    logging.warning(f"Could not save breakdown for {save_to_qid}: {e}")
            calc_result["quote_id"] = save_to_qid
            return calc_result
        elif name == "patch_quote_mo":
            # ── Modify MO items directly without recalculating everything ──
            target_qid = quote_id
            remove_keywords = [kw.lower() for kw in inputs.get("remove_items", [])]
            add_colocacion = inputs.get("add_colocacion", False)
            add_flete_localidad = inputs.get("add_flete")

            try:
                q_result = await db.execute(select(Quote).where(Quote.id == target_qid))
                target_quote = q_result.scalar_one_or_none()
                if not target_quote or not target_quote.quote_breakdown:
                    return {"ok": False, "error": f"Quote {target_qid} no tiene breakdown"}

                bd = dict(target_quote.quote_breakdown)
                original_mo = list(bd.get("mo_items", []))
                new_mo = []
                removed = []

                # Remove items matching keywords
                for item in original_mo:
                    desc_lower = (item.get("description") or "").lower()
                    should_remove = any(kw in desc_lower for kw in remove_keywords)
                    if should_remove:
                        removed.append(item["description"])
                    else:
                        new_mo.append(item)

                # Add colocación if requested
                if add_colocacion:
                    # Check if already exists
                    has_col = any("colocación" in (m.get("description") or "").lower() or "colocacion" in (m.get("description") or "").lower() for m in new_mo)
                    if not has_col:
                        mat_type = bd.get("material_type", "nacional")
                        is_sint = mat_type in ("sintetico", "sintético")
                        sku = "COLOCACIONDEKTON/NEOLITH" if is_sint else "COLOCACION"
                        col_result = catalog_lookup("labor", sku)
                        if col_result.get("found"):
                            price = col_result.get("price_ars", 0)
                            base = col_result.get("price_ars_base", price)
                            qty = max(bd.get("material_m2", 1), 1.0)
                            new_mo.append({"description": "Colocación", "quantity": round(qty, 2), "unit_price": price, "base_price": base, "total": round(price * qty)})

                # Add flete if requested
                if add_flete_localidad:
                    has_flete = any("flete" in (m.get("description") or "").lower() for m in new_mo)
                    if not has_flete:
                        from app.modules.quote_engine.calculator import _find_flete
                        flete_result = _find_flete(add_flete_localidad)
                        if flete_result.get("found"):
                            price = flete_result.get("price_ars", 0)
                            base = flete_result.get("price_ars_base", price)
                            new_mo.append({"description": f"Flete + toma medidas {add_flete_localidad}", "quantity": 1, "unit_price": price, "base_price": base, "total": price})

                # Recalculate totals
                bd["mo_items"] = new_mo
                total_mo = sum(m.get("total", 0) for m in new_mo)
                total_sinks = sum(s.get("unit_price", 0) * s.get("quantity", 1) for s in bd.get("sinks", []))
                currency = bd.get("material_currency", "ARS")
                # material_total may not exist in breakdowns saved by generate_documents
                material_total = bd.get("material_total")
                if material_total is None:
                    # Reconstruct from m2 * price_unit
                    m2 = bd.get("material_m2", 0)
                    price_unit = bd.get("material_price_unit", 0)
                    material_total = round(m2 * price_unit)
                    bd["material_total"] = material_total
                    logging.info(f"Reconstructed material_total={material_total} from {m2} * {price_unit}")

                if currency == "USD":
                    bd["total_ars"] = total_mo + total_sinks
                    bd["total_usd"] = material_total
                else:
                    bd["total_ars"] = total_mo + total_sinks + material_total
                    bd["total_usd"] = 0

                # Save to DB
                history = list(target_quote.change_history or [])
                history.append({
                    "timestamp": datetime.now().isoformat(),
                    "action": "patch_quote_mo",
                    "removed": removed,
                    "total_ars_before": target_quote.total_ars,
                    "total_ars_after": bd["total_ars"],
                    "total_usd_before": target_quote.total_usd,
                    "total_usd_after": bd["total_usd"],
                    "user_message": current_user_message[:200],
                })

                await db.execute(
                    update(Quote).where(Quote.id == target_qid).values(
                        quote_breakdown=bd,
                        total_ars=bd["total_ars"],
                        total_usd=bd["total_usd"],
                        change_history=history,
                    )
                )
                await db.commit()

                added = []
                if add_colocacion: added.append("Colocación")
                if add_flete_localidad: added.append(f"Flete {add_flete_localidad}")

                logging.info(f"patch_quote_mo {target_qid}: removed={removed}, added={added}, total_ars={bd['total_ars']}, total_usd={bd['total_usd']}")

                return {
                    "ok": True,
                    "quote_id": target_qid,
                    "removed": removed,
                    "added": added,
                    "mo_items": [{"description": m["description"], "total": m["total"]} for m in new_mo],
                    "total_ars": bd["total_ars"],
                    "total_usd": bd["total_usd"],
                    "material": bd.get("material_name"),
                }
            except Exception as e:
                logging.error(f"patch_quote_mo error for {target_qid}: {e}", exc_info=True)
                return {"ok": False, "error": str(e)[:200]}
        else:
            return {"error": f"Tool desconocida: {name}"}
