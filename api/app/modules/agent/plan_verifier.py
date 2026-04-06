"""Plan reading verifier — uses Opus to QA Valentina's plan interpretation.

After Valentina (Sonnet) reads a plan and extracts measurements,
this module sends the same plan to Opus for independent verification.
If Opus finds discrepancies, it returns corrections.
"""

import base64
import json
import logging
from pathlib import Path

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

# Opus model for verification — more accurate at reading handwritten plans
VERIFIER_MODEL = "claude-opus-4-20250514"

VERIFY_SYSTEM = """Sos un verificador de lectura de planos para una marmolería.

Tu ÚNICA tarea: mirar el plano adjunto y listar TODAS las cotas/medidas que ves escritas.

Reglas:
- Solo reportar medidas que están EXPLÍCITAMENTE escritas en el plano (números con unidad)
- NO inferir, NO calcular, NO asumir medidas que no están escritas
- Convertir todo a metros (60 CM = 0.60m, 38 CM = 0.38m, 1503 MM = 1.503m)
- Reportar también qué pieza corresponde cada medida (mesada, zócalo, etc.)
- Reportar perforaciones, piletas, u otros elementos visibles

Respondé SOLO con JSON válido, sin markdown:
{
  "cotas": [
    {"valor_plano": "60 CM", "metros": 0.60, "dimension": "largo", "pieza": "mesada"},
    {"valor_plano": "38 CM", "metros": 0.38, "dimension": "profundidad", "pieza": "mesada"}
  ],
  "elementos": ["perforación monocomando", "perforación desagüe"],
  "notas": "texto libre si hay algo relevante"
}"""

COMPARE_SYSTEM = """Sos un verificador de presupuestos de marmolería.

Te doy dos cosas:
1. Las cotas REALES del plano (verificadas)
2. Las medidas que Valentina (otro agente) extrajo del mismo plano

Tu tarea: comparar y reportar SOLO las discrepancias.

Respondé SOLO con JSON válido:
{
  "ok": true/false,
  "discrepancias": [
    {
      "pieza": "mesada",
      "dimension": "largo",
      "valor_plano": 0.60,
      "valor_valentina": 1.00,
      "correccion": "El plano dice 60 CM = 0.60m, no 1.00m"
    }
  ],
  "medidas_correctas": {
    "mesada": {"largo": 0.60, "prof": 0.38},
    "zocalo": {"largo": 0.60, "alto": 0.05}
  }
}

Si no hay discrepancias: {"ok": true, "discrepancias": [], "medidas_correctas": {...}}"""


async def verify_plan_reading(
    plan_bytes: bytes,
    plan_filename: str,
    valentina_measurements: str,
) -> dict | None:
    """Verify Valentina's plan reading using Opus.

    Args:
        plan_bytes: Raw file bytes of the plan
        plan_filename: Filename for MIME type detection
        valentina_measurements: Text of what Valentina extracted (her first response)

    Returns:
        Dict with corrections if discrepancies found, None if OK or on error
    """
    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build plan content block
        ext = Path(plan_filename).suffix.lower()
        if ext == ".pdf":
            plan_block = {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(plan_bytes).decode()},
            }
        else:
            media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/webp" if ext == ".webp" else "image/png"
            plan_block = {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(plan_bytes).decode()},
            }

        # Step 1: Opus reads the plan independently
        logger.info(f"[plan-verifier] Step 1: Opus reading plan {plan_filename}")
        read_response = await client.messages.create(
            model=VERIFIER_MODEL,
            max_tokens=2000,
            system=VERIFY_SYSTEM,
            messages=[{
                "role": "user",
                "content": [plan_block, {"type": "text", "text": "Listá todas las cotas y medidas que ves en este plano."}],
            }],
        )

        opus_reading = ""
        for block in read_response.content:
            if hasattr(block, "text"):
                opus_reading = block.text
                break

        if not opus_reading:
            logger.warning("[plan-verifier] Opus returned empty reading")
            return None

        logger.info(f"[plan-verifier] Opus reading: {opus_reading[:200]}")

        # Step 2: Compare Opus reading vs Valentina's measurements
        logger.info("[plan-verifier] Step 2: Comparing readings")
        compare_response = await client.messages.create(
            model=VERIFIER_MODEL,
            max_tokens=2000,
            system=COMPARE_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"COTAS REALES DEL PLANO (verificadas por Opus):\n{opus_reading}\n\nMEDIDAS DE VALENTINA:\n{valentina_measurements}\n\nComparí y reportá discrepancias.",
            }],
        )

        compare_text = ""
        for block in compare_response.content:
            if hasattr(block, "text"):
                compare_text = block.text
                break

        if not compare_text:
            logger.warning("[plan-verifier] Opus returned empty comparison")
            return None

        # Parse JSON response
        # Strip markdown code fences if present
        clean = compare_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1]
            clean = clean.rsplit("```", 1)[0]

        result = json.loads(clean)
        logger.info(f"[plan-verifier] Result: ok={result.get('ok')}, discrepancias={len(result.get('discrepancias', []))}")

        if result.get("ok") and not result.get("discrepancias"):
            return None  # All good, no corrections needed

        # Log discrepancies
        for d in result.get("discrepancias", []):
            logger.warning(
                f"[plan-verifier] DISCREPANCIA: {d.get('pieza')} {d.get('dimension')}: "
                f"plano={d.get('valor_plano')}, valentina={d.get('valor_valentina')} — {d.get('correccion')}"
            )

        return result

    except json.JSONDecodeError as e:
        logger.error(f"[plan-verifier] Failed to parse Opus response: {e}")
        return None
    except Exception as e:
        logger.error(f"[plan-verifier] Verification failed: {e}", exc_info=True)
        return None
