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
