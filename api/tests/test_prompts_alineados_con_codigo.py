"""Lo que el prompt/reglas le dicen al LLM no puede contradecir al código."""
import json
import re
from pathlib import Path

API = Path(__file__).resolve().parent.parent
CONTEXT = (API / "CONTEXT.md").read_text(encoding="utf-8")
BUILDINGS = (API / "rules" / "quote-process-buildings.md").read_text(encoding="utf-8")
CONFIG = json.loads((API / "catalog" / "config.json").read_text(encoding="utf-8"))


def test_flete_por_viaje_del_texto_coincide_con_la_config():
    per_trip = CONFIG["building"]["flete_mesadas_per_trip"]
    for name, text in (("CONTEXT.md", CONTEXT), ("quote-process-buildings.md", BUILDINGS)):
        divisores = set(re.findall(r"ceil\(piezas(?:_fisicas)?\s*/\s*(\d+)\)", text))
        assert divisores <= {str(per_trip)}, f"{name}: dice /{divisores}, la config usa {per_trip}"
        assert divisores, f"{name}: no menciona el divisor del flete"


def test_tomas_no_se_agregan_solas():
    assert "TOMAS automaticamente" not in CONTEXT
    assert "tomas_qty" in CONTEXT


def test_tolerancia_paso1_paso2_del_texto():
    assert ">0.5 m²" not in CONTEXT
