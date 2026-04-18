"""Required fields contract — validación completa de datos obligatorios
por tipo de trabajo (cocina, baño, lavadero) + globales.

Principio: Valentina NUNCA avanza al Paso 2 (cálculo) con datos faltantes
importantes. Este módulo define el contrato de campos obligatorios por
tipo de trabajo y emite pending_questions para los que falten.

Spec confirmado con el operador D'Angelo:

COCINA
  Geometría          : recta / L / U / isla — inferible del plano/card
  Dimensiones        : largo × ancho por tramo
  Material           : REQUERIDO
  Zócalos            : sí/no + alto + lados                    (PR B)
  Alzada             : sí/no + alto + lados
  Pileta             : sí/no — en cocina SIEMPRE empotrada      (PR C)
  Simple vs doble    : REQUERIDO si hay pileta                  (PR C)
  Anafe              : sí/no + cuántos                          (PR D)
  Isla               : profundidad + patas                      (PR D)
  Colocación         : sí/no                                    (PR D)
  Localidad          : REQUERIDO (flete)
  Descuento          : sí/no + tipo (arquitecta, etc)

BAÑO
  Geometría          : recta / L / doble
  Dimensiones        : largo × ancho
  Material           : REQUERIDO
  Zócalos            : sí/no + alto + lados                    (PR B)
  Pileta             : apoyo / bajomesada / empotrada           (specific)
  Cantidad           : N piletas
  Colocación         : sí/no                                    (PR D)
  Localidad          : REQUERIDO
  Descuento          : sí/no + tipo

LAVADERO
  Dimensiones        : largo × ancho
  Material           : REQUERIDO
  Zócalos            : sí/no                                   (PR B)
  Pileta             : sí/no + tipo
  Colocación         : sí/no                                    (PR D)
  Localidad          : REQUERIDO
  Descuento          : sí/no

GLOBAL (aplica a todos)
  Cliente            : del brief o DB (_extract_quote_info)
  Obra / proyecto    : del brief o DB
  Particular/edificio: inferible (edificio si brief menciona edificio/B,
                       departamentos, unidades)
  Forma de pago      : default "Contado" (config)
  Demora             : default del config

Este módulo NO reemplaza los detectores específicos de pending_questions.py
(zócalos/pileta_simple_doble/isla/colocación/anafe). Se integra con ellos:
los específicos capturan matices visuales/contextuales; este valida
presencia básica y agrega material + localidad como mínimo.
"""
from __future__ import annotations

import re


# ─────────────────────────────────────────────────────────────────────────────
# Field presence detectors
# ─────────────────────────────────────────────────────────────────────────────

# Ciudades típicas del área de D'Angelo — si se matchea, hay localidad.
_LOCALIDAD_HINTS = re.compile(
    r"\b(rosario|echesortu|funes|roldán|roldan|villa\s+constitución|villa\s+constitucion|"
    r"san\s+lorenzo|san\s+nicolás|san\s+nicolas|pergamino|rafaela|fisherton|"
    r"puerto\s+san\s+mart[ií]n|granadero\s+baigorria|pueblo\s+esther|"
    r"capit[aá]n\s+bermudez|villa\s+gobernador\s+g[aá]lvez|arroyo\s+seco|"
    r"cabin|cabina|arrecifes|c[oó]rdoba|buenos\s+aires|caba|capital|córdoba)\b",
    re.IGNORECASE,
)


def has_material(brief: str, quote: dict | None, dual_result: dict) -> bool:
    """True si hay material identificable en el brief o en el quote."""
    if quote and (quote.get("material") or "").strip():
        return True
    if not brief:
        return False
    # Keywords de materiales conocidos del catálogo
    material_keywords = [
        "silestone", "dekton", "neolith", "puraprima", "pura prima",
        "purastone", "laminatto", "granito", "mármol", "marmol",
        "negro brasil", "blanco norte", "onix", "quartz",
    ]
    return any(k in brief.lower() for k in material_keywords)


def has_localidad(brief: str, quote: dict | None) -> bool:
    """True si hay localidad identificable en el brief o en el quote."""
    if quote and (quote.get("localidad") or "").strip():
        return True
    if not brief:
        return False
    return bool(_LOCALIDAD_HINTS.search(brief))


# ─────────────────────────────────────────────────────────────────────────────
# Question builders
# ─────────────────────────────────────────────────────────────────────────────

def build_material_question() -> dict:
    return {
        "id": "material",
        "label": "Material",
        "question": (
            "¿Qué material se usa para este presupuesto? No lo identificamos en "
            "el brief ni en el plano. Requerido para buscar precio en catálogo."
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "granito", "label": "Granito (especificar en el cuadro)"},
            {"value": "silestone", "label": "Silestone (especificar modelo)"},
            {"value": "dekton", "label": "Dekton"},
            {"value": "neolith", "label": "Neolith"},
            {"value": "puraprima", "label": "Puraprima / Purastone"},
            {"value": "marmol", "label": "Mármol"},
            {"value": "custom", "label": "Otro (detallar)"},
        ],
        "detail_placeholder": "Nombre exacto del modelo (ej: 'Silestone Blanco Norte')",
    }


def build_localidad_question() -> dict:
    return {
        "id": "localidad",
        "label": "Localidad",
        "question": (
            "¿Dónde se entrega / instala? Requerido para calcular flete."
        ),
        "type": "radio_with_detail",
        "options": [
            {"value": "rosario", "label": "Rosario"},
            {"value": "funes", "label": "Funes"},
            {"value": "roldan", "label": "Roldán"},
            {"value": "custom", "label": "Otra localidad (detallar)"},
        ],
        "detail_placeholder": "Nombre de la localidad / ciudad",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Detector entry point (para composición en pending_questions)
# ─────────────────────────────────────────────────────────────────────────────

def detect_required_field_questions(
    brief: str,
    quote: dict | None,
    dual_result: dict,
) -> list[dict]:
    """Detecta campos obligatorios faltantes y devuelve preguntas.

    Hoy arranca con 2: material + localidad (ambos requeridos para
    cualquier tipo de trabajo). Siguientes iteraciones pueden ampliar
    con descuento, forma de pago, etc.
    """
    questions: list[dict] = []
    if not has_material(brief, quote, dual_result):
        questions.append(build_material_question())
    if not has_localidad(brief, quote):
        questions.append(build_localidad_question())
    return questions


# ─────────────────────────────────────────────────────────────────────────────
# Answer appliers
# ─────────────────────────────────────────────────────────────────────────────

def apply_material_answer(dual_result: dict, answer: dict) -> dict:
    """Registra el material elegido en el dual_result y hinte al quote."""
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    detail = (answer.get("detail") or "").strip()
    if value == "custom":
        if not detail:
            return dual_result
        dual_result["material_hint"] = detail
    elif value:
        label_map = {
            "granito": "Granito",
            "silestone": "Silestone",
            "dekton": "Dekton",
            "neolith": "Neolith",
            "puraprima": "Puraprima",
            "marmol": "Mármol",
        }
        base = label_map.get(value, value.title())
        dual_result["material_hint"] = f"{base}{' — ' + detail if detail else ''}"
    return dual_result


def apply_localidad_answer(dual_result: dict, answer: dict) -> dict:
    if not isinstance(answer, dict):
        return dual_result
    value = answer.get("value")
    detail = (answer.get("detail") or "").strip()
    if value == "custom":
        if not detail:
            return dual_result
        dual_result["localidad_hint"] = detail
    elif value:
        dual_result["localidad_hint"] = value
    return dual_result
