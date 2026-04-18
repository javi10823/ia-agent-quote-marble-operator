"""Parse free-text measurements into structured pieces using Claude.

Used by /v1/quote when the web chatbot sends notes with measurements
instead of pre-structured pieces[].
"""

import json
import logging
import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

from app.core.company_config import get as _cfg

def _parse_system() -> str:
    depth = _cfg("measurements.default_depth", 0.60)
    zocalo = _cfg("measurements.default_zocalo_height", 0.05)
    return f"""Sos un parser de medidas para una marmolería.
Recibís texto libre con medidas de un trabajo y devolvés JSON estructurado.

Reglas de medidas:
- Todo en METROS (convertir cm a m: 60cm = 0.60m, 5cm = 0.05m)
- Mesada: largo × prof (profundidad default cocina: {depth}m si no dice)
- Zócalo: largo × alto (alto default: {zocalo}m si no dice)
- Alza: largo × alto
- Frentín: largo × alto (generalmente 0.02m o 0.03m)
- Si dice "zócalo atrás 5cm" en una mesada de 2m → zócalo largo=2.0, alto=0.05

Detectar también:
- pileta: "Johnson" o "johnson" → "empotrada_johnson", "empotrada" o "bajo mesada" → "empotrada_cliente", "apoyo" → "apoyo"
- anafe: si menciona anafe/hornalla → true
- colocacion: true por default, false si dice "sin colocación"
- frentin: si menciona frentín → true

Respondé SOLO con JSON válido, sin markdown ni explicaciones:
{{
  "pieces": [
    {{"description": "Mesada cocina", "largo": 2.0, "prof": {depth}}},
    {{"description": "Zócalo trasero", "largo": 2.0, "alto": {zocalo}}}
  ],
  "pileta": "empotrada_johnson" | "empotrada_cliente" | "apoyo" | null,
  "anafe": false,
  "colocacion": true,
  "frentin": false
}}"""

PARSE_SYSTEM = _parse_system()


async def parse_measurements(notes: str, material: str, project: str = "") -> dict | None:
    """Parse free-text measurements into structured pieces using Claude.

    Returns dict with 'pieces' and parameters, or None if parsing fails.
    """
    if not notes or not notes.strip():
        return None

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        user_msg = f"Material: {material}\n"
        if project:
            user_msg += f"Proyecto: {project}\n"
        user_msg += f"\nTexto del cliente:\n{notes}"

        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=500,
            system=PARSE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        parsed = json.loads(text)

        # Validate minimum structure
        if not parsed.get("pieces") or not isinstance(parsed["pieces"], list):
            logger.warning(f"Parser returned no pieces: {text[:200]}")
            return None

        for p in parsed["pieces"]:
            if "largo" not in p or not isinstance(p["largo"], (int, float)):
                logger.warning(f"Piece missing largo: {p}")
                return None

        logger.info(f"Parsed {len(parsed['pieces'])} pieces from text ({len(notes)} chars)")
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"Parser JSON decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"Parser error: {e}")
        return None


def _field(valor: float) -> dict:
    """FieldValue shape usado por el componente DualReadResult."""
    return {"opus": None, "sonnet": None, "valor": valor, "status": "CONFIRMADO"}


def parsed_pieces_to_card(parsed: dict) -> dict | None:
    """Adapter: transforma el output de `parse_measurements()` a la misma
    shape que emite `_run_dual_read()` para que el frontend renderice la
    card editable igual que para un plano.

    - **Recalcula `m2`** siempre como `round(largo * ancho, 2)` (no confía
      en el parser para consistencia largo/ancho/m2).
    - Separa piezas de mesada (tienen `prof`) de zócalos (tienen `alto`).
      Los zócalos se asignan al último tramo de mesada previo.
    - Cada tramo queda `_manual=True` para que todos los fields sean
      editables desde la UI (el operador no confirma a ciegas).
    - `source="TEXT"` al top-level separa origen (texto) de reconciliación
      (que aquí no aplica — es fuente única). `_retry=True` oculta el
      botón "reintentar con Opus" (no hay plano para releer).

    Devuelve `None` si `parsed` no tiene al menos una mesada con `largo>0`
    (sin medidas válidas no tiene sentido emitir card — el flujo clásico
    pedirá medidas).
    """
    if not parsed or not isinstance(parsed.get("pieces"), list):
        return None

    tramos: list[dict] = []
    pending_zocalos: list[dict] = []
    for p in parsed["pieces"]:
        largo = p.get("largo")
        if not isinstance(largo, (int, float)) or largo <= 0:
            continue
        prof = p.get("prof")
        alto = p.get("alto")

        if prof is not None and isinstance(prof, (int, float)) and prof > 0:
            # Es una mesada
            m2 = round(largo * prof, 2)
            tramo = {
                "id": f"t{len(tramos) + 1}",
                "descripcion": p.get("description") or f"Mesada {len(tramos) + 1}",
                "largo_m": _field(largo),
                "ancho_m": _field(prof),
                "m2": _field(m2),
                "zocalos": [],
                "frentin": [],
                "regrueso": [],
                "_manual": True,
            }
            # Si hay zócalos pendientes sin tramo previo, asignarlos al primer tramo
            if pending_zocalos and not tramos:
                tramo["zocalos"].extend(pending_zocalos)
                pending_zocalos = []
            tramos.append(tramo)
        elif alto is not None and isinstance(alto, (int, float)) and alto > 0:
            # Es un zócalo — asignar al último tramo, o dejarlo pendiente
            zocalo = {
                "lado": (p.get("description") or "trasero").replace("Zócalo ", "").replace("Zócalo", "").strip() or "trasero",
                "ml": float(largo),
                "alto_m": float(alto),
                "status": "CONFIRMADO",
                "opus_ml": None,
                "sonnet_ml": None,
            }
            if tramos:
                tramos[-1]["zocalos"].append(zocalo)
            else:
                pending_zocalos.append(zocalo)

    if not tramos:
        return None

    # Cualquier zócalo todavía pendiente (no había tramos aún) se cuelga del primero
    if pending_zocalos:
        tramos[0]["zocalos"].extend(pending_zocalos)

    m2_total_valor = round(
        sum(t["m2"]["valor"] for t in tramos)
        + sum(z["ml"] * z["alto_m"] for t in tramos for z in t["zocalos"]),
        2,
    )

    sector = {
        "id": "sector_1",
        "tipo": "cocina",
        "tramos": tramos,
        "m2_total": _field(m2_total_valor),
        "ambiguedades": [],
        "_manual": True,
    }

    return {
        "sectores": [sector],
        "requires_human_review": False,
        "conflict_fields": [],
        "source": "TEXT",
        "view_type": "texto",
        "view_type_reason": "Card generada desde texto del operador (sin plano adjunto)",
        "m2_warning": None,
        "_retry": True,
    }


async def parse_brief_to_card(notes: str, material: str, project: str = "") -> dict | None:
    """Parsea un brief de texto y devuelve la card editable lista para
    emitir como chunk `dual_read_result`, o `None` si no hay medidas.
    """
    parsed = await parse_measurements(notes, material, project)
    if not parsed:
        return None
    return parsed_pieces_to_card(parsed)
