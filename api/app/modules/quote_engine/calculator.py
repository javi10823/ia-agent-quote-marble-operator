"""Pure Python quote calculator — no LLM, deterministic, fast."""

import math
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.modules.agent.tools.catalog_tool import catalog_lookup
from app.core.company_config import get as cfg


def _round_half_up(value: float, decimals: int = 2) -> float:
    """Redondeo half-up (1.575 → 1.58, no 1.57 como hace Python por float).

    Usa Decimal sobre la representación string para evitar el bug clásico
    de Python: round(1.575, 2) == 1.57 porque el float 1.575 es internamente
    1.5749999...
    """
    if value is None:
        return 0.0
    quant = Decimal("1").scaleb(-decimals)  # ej: 0.01 para decimals=2
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


_AMBIENTE_KEYWORDS = {
    "cocina": "Cocina",
    "lavadero": "Lavadero",
    "baño": "Baño",
    "bano": "Baño",
    "vanitory": "Vanitory",
    "isla": "Isla",
    "barra": "Barra",
    "bar": "Barra",
}


def _detect_ambiente(desc: str) -> str | None:
    """Detecta el ambiente de una pieza por keyword en la descripción."""
    d = (desc or "").lower()
    for kw, name in _AMBIENTE_KEYWORDS.items():
        if kw in d:
            return name
    return None

# Material classifications — read from config.json, fallback to defaults
def _set(path: str, default: list) -> set:
    val = cfg(path)
    return set(val) if val else set(default)

SINTERIZADOS = _set("materials.sinterizados", ["dekton", "neolith", "puraprima", "laminatto"])
SINTETICOS = _set("materials.sinteticos", ["silestone", "dekton", "neolith", "puraprima", "purastone", "laminatto"])
MERMA_MEDIA_PLACA = _set("materials.merma_media_placa", ["silestone"])
MERMA_PLACA_ENTERA = _set("materials.merma_placa_entera", ["purastone", "puraprima", "dekton", "neolith", "laminatto"])

def _build_plate_sizes() -> dict[str, float]:
    """Build material→m2 map from config plate_sizes + material_map."""
    plate_sizes = cfg("plate_sizes", {})
    mat_map = cfg("materials.plate_material_map", {})
    result = {}
    for material, plate_type in mat_map.items():
        plate = plate_sizes.get(plate_type, {})
        result[material] = plate.get("m2", 4.20)
    return result

PLATE_SIZES = _build_plate_sizes()

# Zone aliases — loaded from config.json
# Supports both old format (str) and new format ({"sku": str, "pulido_extra": bool})
def _load_zone_aliases() -> dict[str, dict]:
    """Returns {zone_key: {"sku": str, "pulido_extra": bool}}."""
    raw = cfg("zone_aliases", {})
    result = {}
    for k, v in raw.items():
        key = k.lower().strip()
        if key.startswith("_"):
            continue  # skip _comment
        if isinstance(v, str):
            result[key] = {"sku": v, "pulido_extra": False}
        elif isinstance(v, dict):
            result[key] = {"sku": v.get("sku", ""), "pulido_extra": v.get("pulido_extra", False)}
    return result

ZONE_ALIASES = _load_zone_aliases()


def _detect_material_type(catalog_result: dict) -> str:
    """Detect if material is sinterizado based on catalog data."""
    mat_type = catalog_result.get("material_type", "").lower()
    name = catalog_result.get("name", "").lower()

    for s in SINTERIZADOS:
        if s in mat_type or s in name:
            return s
    for s in SINTETICOS:
        if s in mat_type or s in name:
            return s
    return mat_type or "granito"


MATERIAL_CATALOGS = [
    "materials-silestone", "materials-purastone",
    "materials-granito-nacional", "materials-granito-importado",
    "materials-dekton", "materials-neolith",
    "materials-marmol", "materials-puraprima", "materials-laminatto",
]

# Common name normalizations (user typos / spacing)
_NORMALIZE_MAP = {
    "pura stone": "purastone",
    "pura prima": "puraprima",
    "negro brasil extra": "granito negro brasil extra",
}


def _normalize_material_name(name: str) -> str:
    """Normalize common variations in material names."""
    lower = name.lower().strip()
    # Apply known normalizations
    for pattern, replacement in _NORMALIZE_MAP.items():
        lower = lower.replace(pattern, replacement)
    # Remove extra spaces
    lower = " ".join(lower.split())
    return lower


# ═══════════════════════════════════════════════════════════════════════
# PR #396 — Family gate para fuzzy matching de materiales
# ═══════════════════════════════════════════════════════════════════════
#
# Bug raíz: `_find_material` corría `thefuzz.extractOne` sobre TODOS los
# catálogos juntos. Palabras genéricas ("Grey", "Silver", "Metro")
# matcheaban entre familias incompatibles. Caso real Perdomo Fabiana
# (2026-04-24): input="Puraprima Metro Grey" → output="GRANITO SILVER
# GREY LETHER - 2 ESP". Son familias ontológicamente distintas:
#
#   Puraprima = sinterizado  → merma sí, COLOCACIONDEKTON/NEOLITH
#   Granito   = piedra natural → merma no,  COLOCACION
#
# Ahora: detector de familia previo al fuzzy. Input con keyword de
# familia busca SÓLO en los catálogos de esa familia.


# Familia canónica → lista de catálogos (usar `unión` para granito —
# hay `materials-granito-nacional` + `materials-granito-importado`).
_FAMILY_CATALOGS: dict[str, list[str]] = {
    "puraprima": ["materials-puraprima"],
    "purastone": ["materials-purastone"],
    "silestone": ["materials-silestone"],
    "dekton": ["materials-dekton"],
    "neolith": ["materials-neolith"],
    "laminatto": ["materials-laminatto"],
    "granito": ["materials-granito-nacional", "materials-granito-importado"],
    "marmol": ["materials-marmol"],
}

# Familias sintéticas vs naturales — usado para bloquear cross-type
# catastrófico (sintético ≠ natural en merma, colocación, precio base).
_SYNTHETIC_FAMILIES = frozenset({
    "puraprima", "purastone", "silestone", "dekton", "neolith", "laminatto",
})
_NATURAL_FAMILIES = frozenset({"granito", "marmol"})


# Keywords normalizados (post-`_normalize_input_string`) que mapean a
# familia. Orden IMPORTA: keywords más específicos primero. Ej:
# "purastone prima" → familia "puraprima" (porque los items
# "PURASTONE PRIMA X" viven en materials-puraprima.json), NO "purastone".
_FAMILY_KEYWORDS: list[tuple[str, str]] = [
    # Aliases específicos primero.
    ("purastone prima", "puraprima"),
    ("pura stone prima", "puraprima"),
    # Luego los genéricos.
    ("puraprima", "puraprima"),
    ("pura prima", "puraprima"),
    ("purastone", "purastone"),
    ("pura stone", "purastone"),
    ("silestone", "silestone"),
    ("dekton", "dekton"),
    ("neolith", "neolith"),
    ("laminatto", "laminatto"),
    ("laminato", "laminatto"),
    ("granito", "granito"),
    ("marmol", "marmol"),  # normalizado ya sin tilde
]


def _normalize_input_string(raw: str) -> str:
    """Normalización canónica para matcheo: lowercase, sin tildes,
    espacios colapsados, separadores tipo `-_/|` a espacios.

    No es idéntica a `_normalize_material_name`: esta es más agresiva
    (decompone acentos con unicodedata + reemplaza separadores) y se
    usa antes del fuzzy para dar al matcher un shape estable.
    """
    import unicodedata as _u
    if not raw:
        return ""
    # Decomponer acentos.
    nfkd = _u.normalize("NFKD", raw)
    no_accent = "".join(c for c in nfkd if not _u.combining(c))
    lower = no_accent.lower().strip()
    # Reemplazar separadores raros por espacios.
    for ch in ("-", "_", "/", "|", "–", "—"):
        lower = lower.replace(ch, " ")
    # Colapsar múltiples espacios.
    lower = " ".join(lower.split())
    return lower


def _detect_family(raw_input: str) -> str | None:
    """Detecta la familia del material desde el input del usuario.

    Dos pasadas:
      1. Substring exacto sobre `_FAMILY_KEYWORDS` (orden específico →
         genérico). Si matchea, retorna sin llamar al fuzzy.
      2. Fuzzy token-level: cada token del input vs cada keyword con
         `fuzz.ratio`. Captura typos ("puraprma" → "puraprima",
         "maramol" → "marmol"). Cutoff 85.

    Retorna la familia canónica o `None` si ninguna alternativa pasa.
    """
    normalized = _normalize_input_string(raw_input)
    if not normalized:
        return None
    for keyword, family in _FAMILY_KEYWORDS:
        if keyword in normalized:
            return family
    # Fuzzy fallback: typos en el keyword de familia.
    try:
        from thefuzz import fuzz as _fz
    except ImportError:
        return None
    tokens = normalized.split()
    best_family: str | None = None
    best_score = 0
    for keyword, family in _FAMILY_KEYWORDS:
        # Si el keyword es multi-palabra, saltear (el substring ya no
        # matcheó; fuzz.ratio sobre un multi-word vs un solo token daría
        # falsos negativos — usaríamos partial_ratio pero es demasiado
        # permisivo para tokens cortos).
        if " " in keyword:
            continue
        for token in tokens:
            score = _fz.ratio(token, keyword)
            if score > best_score:
                best_score = score
                best_family = family
    if best_score >= 85:
        return best_family
    return None


def _strip_family_keyword(text: str, family: str) -> str:
    """Remueve los keywords de la `family` especificada del texto
    normalizado. Usado para que el fuzzy intra-familia mire solo la
    parte específica del material, no el nombre de la familia que ya
    usamos como gate.

    Dos pasos:
      1. Exact replace: saca substrings que matcheen keywords de la
         familia (más largos primero: "purastone prima" > "purastone").
      2. Fuzzy single-token: saca tokens individuales que matcheen un
         keyword single-word con `ratio ≥ 85`. Cubre typos que
         `_detect_family` aceptó pero quedaron en el texto ("puraprma"
         vs "puraprima" → removido).

    Ejemplo:
      - "puraprima metro grey" (family=puraprima) → "metro grey".
      - "puraprma metro grey" → "metro grey" (typo sacado por fuzzy).
      - "PURASTONE PRIMA METRO GREY..." → "metro grey..." (exact).
    """
    lowered = _normalize_input_string(text)
    keywords = [k for k, f in _FAMILY_KEYWORDS if f == family]
    keywords.sort(key=len, reverse=True)
    for kw in keywords:
        lowered = lowered.replace(kw, " ")
    lowered = " ".join(lowered.split())
    # Pasada fuzzy: tokens con typo de familia se sacan también.
    try:
        from thefuzz import fuzz as _fz
    except ImportError:
        return lowered
    single_word_keywords = [k for k in keywords if " " not in k]
    if not single_word_keywords:
        return lowered
    tokens = lowered.split()
    kept = [
        t for t in tokens
        if not any(_fz.ratio(t, kw) >= 85 for kw in single_word_keywords)
    ]
    return " ".join(kept)


def _build_family_material_list(family: str) -> list[tuple[str, str]]:
    """Devuelve `[(name, catalog), ...]` de todos los items en los
    catálogos de esa familia. Si la familia no existe, lista vacía."""
    from app.modules.agent.tools.catalog_tool import _load_catalog
    out: list[tuple[str, str]] = []
    for cat in _FAMILY_CATALOGS.get(family, []):
        items = _load_catalog(cat) or []
        for item in items:
            name = item.get("name", "")
            if name:
                out.append((name, cat))
    return out


def _top_suggestions(
    raw_input: str,
    scope: list[tuple[str, str]],
    *,
    top_k: int = 3,
) -> list[dict]:
    """Top-K matches por `thefuzz` sobre el scope dado. Shape estable:
        [{"sku": str | None, "name": str, "score": int, "catalog": str}]

    `sku` se deja `None` si el catálogo no lo devuelve — el caller
    puede pasar a `catalog_lookup` si necesita el SKU exacto.
    """
    if not scope:
        return []
    try:
        from thefuzz import process as fuzz_process
    except ImportError:
        return []
    names = [n for n, _c in scope]
    name_to_cat = dict(scope)
    results = fuzz_process.extract(raw_input, names, limit=top_k)
    out: list[dict] = []
    for name, score in results:
        cat = name_to_cat.get(name, "")
        # Extraer familia corta del catálogo ("materials-puraprima" → "puraprima").
        cat_short = cat.replace("materials-", "") if cat else ""
        out.append({
            "sku": None,
            "name": name,
            "score": int(score),
            "catalog": cat_short,
        })
    return out


def _find_material(material_name: str) -> dict:
    """Search for material across all catalogs with fuzzy fallback."""
    from app.modules.agent.tools.catalog_tool import _load_catalog

    # PR #410 — Default duro de "Gris Mara" → "GRANITO GRIS MARA EXTRA 2 ESP".
    # Regla del operador: el granito Gris Mara se vende solo como
    # variante Extra 2 a menos que el operador pida explícitamente
    # FIAMATADO o LEATHER. El catálogo tiene 3 variantes (GRISMARA,
    # GRISIFIAMATADO, MARALEATHER) que el matcher fuzzy puede confundir
    # cuando el agente Sonnet, leyendo "NO Extra 2" en el brief, infiere
    # otra variante e inyecta "Granito Gris Mara Fiamatado" al calculator.
    #
    # Pre-check determinístico (corre antes del fuzzy):
    #   - Input contiene "gris mara"
    #   - Input NO contiene "fiamatado" ni "leather"
    #   → resolver directo a SKU GRISMARA (Extra 2 ESP).
    #
    # Si el operador escribe "fiamatado" o "leather" explícito, este
    # pre-check no entra y el fuzzy resuelve normalmente a esa variante.
    _name_norm = (material_name or "").lower()
    if "gris mara" in _name_norm and "fiamatado" not in _name_norm and "leather" not in _name_norm:
        from app.modules.agent.tools.catalog_tool import catalog_lookup as _cl
        _gm = _cl("materials-granito-nacional", "GRISMARA")
        if _gm.get("found"):
            logging.info(
                f"[material-default] Granito Gris Mara → forzado SKU=GRISMARA "
                f"(EXTRA 2 ESP) por regla de negocio. Input='{material_name}' "
                "no menciona fiamatado/leather explícito."
            )
            _gm["fuzzy_corrected_from"] = material_name
            _gm["fuzzy_score"] = 100  # determinístico, no fuzzy
            _gm["fuzzy_catalog"] = "granito-nacional"
            _gm["fuzzy_family"] = "granito"
            return _gm

    # PR #59 — guard contra material genérico (familia sola sin variante).
    # Caso observado: brief/plano dice "MESADA GRANITO RECTA LINEAL" →
    # Valentina pasa material="GRANITO" solo → fuzzy lo matchea con
    # "GRANITO GRIS MARA EXTRA 2 ESP" al azar y cotiza. Debe PREGUNTAR.
    _FAMILY_NAMES = {
        "granito", "granitos",
        "mármol", "marmol", "mármoles", "marmoles",
        "silestone",
        "dekton",
        "neolith",
        "puraprima", "pura prima",
        "purastone", "pura stone",
        "laminatto", "laminato",
    }
    _stripped = (material_name or "").strip().lower()
    if _stripped in _FAMILY_NAMES:
        return {
            "found": False,
            "ambiguous_family": True,
            "family": _stripped,
            "error": (
                f"Material '{material_name}' es un nombre de familia genérico. "
                "El catálogo tiene múltiples variantes. NO elegir por default — "
                "preguntar al operador qué material específico (color + acabado) "
                "antes de cotizar."
            ),
        }

    # PR #396 — si el input tiene keyword de familia, TODOS los pasos
    # (exact, normalize, fuzzy) deben buscar sólo en esa familia para
    # prevenir cross-family bleed incluso en match exacto.
    _detected_family_early = _detect_family(material_name)
    if _detected_family_early:
        _early_cats = _FAMILY_CATALOGS.get(_detected_family_early, MATERIAL_CATALOGS)
    else:
        _early_cats = MATERIAL_CATALOGS

    # 1. Exact match (case-insensitive via catalog_lookup)
    for cat in _early_cats:
        result = catalog_lookup(cat, material_name)
        if result.get("found"):
            return result

    # 2. Try normalized name
    normalized = _normalize_material_name(material_name)
    if normalized != material_name.lower().strip():
        for cat in _early_cats:
            result = catalog_lookup(cat, normalized)
            if result.get("found"):
                logging.info(f"[normalize] '{material_name}' → '{result.get('name')}' (normalized)")
                result["fuzzy_corrected_from"] = material_name
                # PR #396 — también marcamos el catálogo para trazabilidad
                # (el path de normalización es determinístico, score=100).
                result["fuzzy_score"] = 100
                result["fuzzy_catalog"] = cat.replace("materials-", "")
                return result

    # 3. Fuzzy match — PR #396: family-gated.
    #
    # Política:
    #   - Input con keyword de familia → fuzzy SOLO en catálogos de esa
    #     familia (score_cutoff=80).
    #   - Input sin keyword de familia → fuzzy cross-catalog con
    #     score_cutoff=85 (más estricto — evita matches accidentales).
    #   - Sin match → `{found: False, suggestions: [...]}` con shape
    #     estable, sin cross-family silencioso.
    try:
        from thefuzz import process as fuzz_process

        # Strip thickness tokens ("25mm", "— 25mm") — el catálogo no
        # siempre trae espesor en el nombre y no queremos penalizarlo.
        import re as _re_thk
        _clean_input = _re_thk.sub(
            r'[—\-–]?\s*\d{1,2}\s*mm\b', '', material_name, flags=_re_thk.IGNORECASE,
        ).strip()
        # PR #396 — quitar paréntesis y su contenido del input para el
        # fuzzy. Los paréntesis típicamente llevan notas del operador
        # ("(SKU estándar, NO Extra 2)") que no deben pesar en el
        # matcheo — generaban ties con tokens comunes tipo "2 ESP".
        # El `material_name` original se preserva para la detección
        # downstream de negaciones (PR #8 DINALE).
        _clean_input = _re_thk.sub(r'\([^)]*\)', '', _clean_input).strip()
        _clean_input = " ".join(_clean_input.split())

        # Build list (scope depende de si detectamos familia o no).
        detected_family = _detect_family(material_name)

        if detected_family is not None:
            scope: list[tuple[str, str]] = _build_family_material_list(detected_family)
            score_cutoff = 80
            logging.info(
                f"[fuzzy] family gate: '{material_name}' → family={detected_family} "
                f"(scope {len(scope)} items, cutoff={score_cutoff})"
            )
        else:
            # Sin familia: cross-catalog con umbral más estricto.
            scope = []
            for cat in MATERIAL_CATALOGS:
                for item in _load_catalog(cat) or []:
                    name = item.get("name", "")
                    if name:
                        scope.append((name, cat))
            score_cutoff = 85
            logging.info(
                f"[fuzzy] no family keyword for '{material_name}' → cross-catalog "
                f"(scope {len(scope)} items, cutoff={score_cutoff})"
            )

        if not scope:
            return {
                "found": False,
                "error": f"Material '{material_name}' no encontrado — catálogos vacíos",
                "suggestions": [],
            }

        # Filtro de acabado: excluir LEATHER / FIAMATADO / FLAMEADO a
        # menos que el input los pida explícitamente.
        input_lower = material_name.lower()
        has_leather = "leather" in input_lower
        has_fiamatado = "fiamatado" in input_lower or "flameado" in input_lower
        filtered = [
            (n, c) for n, c in scope
            if (has_leather or "leather" not in n.lower())
            and (has_fiamatado or "fiamatado" not in n.lower())
        ]
        working_scope = filtered if filtered else scope

        # PR #396 — cuando ya detectamos familia, strip el keyword de
        # familia del input y de los nombres. Así el fuzzy mira solo la
        # parte específica del material ("metro grey" vs "metro grey"),
        # no el nombre de la familia que ya validamos como gate. Sin
        # esto el matcher puede preferir otro item que tenga la palabra
        # "PURAPRIMA" literal sobre el que tiene el material correcto.
        if detected_family is not None:
            # Mapa de nombre stripped → (name_original, catalog).
            stripped_to_original: dict[str, tuple[str, str]] = {}
            for n, c in working_scope:
                stripped = _strip_family_keyword(n, detected_family)
                # Si varios items strippean al mismo texto, el primero
                # gana (determinístico por orden del catálogo).
                stripped_to_original.setdefault(stripped, (n, c))
            names = list(stripped_to_original.keys())
            _fuzzy_input = _strip_family_keyword(_clean_input, detected_family)
            if not _fuzzy_input:
                # Solo keyword de familia, nada específico. No podemos
                # fuzzy con string vacío — delegar a suggestions.
                _fuzzy_input = _clean_input
        else:
            stripped_to_original = {n: (n, c) for n, c in working_scope}
            names = [n for n, _c in working_scope]
            _fuzzy_input = _clean_input

        match = fuzz_process.extractOne(_fuzzy_input, names, score_cutoff=score_cutoff)

        # Fallback "EXTRA 2 ESP": aplicar SOLO si el match ya está en
        # la familia correcta (scope family-gated o cross con familia
        # coincidente). No hacemos cross-family fallback.
        if match:
            matched_stripped, _score_pre = match
            matched_name, matched_cat = stripped_to_original[matched_stripped]
            m_upper = matched_name.upper()
            if "EXTRA 2" not in m_upper and "EXTRA" not in m_upper:
                # Buscar sibling "EXTRA 2 ESP" con MISMO catálogo
                # (misma familia) y mismo material base (tokens
                # compartidos).
                base_tokens = set(
                    t for t in m_upper.split()
                    if t not in {"LEATHER", "FIAMATADO", "FLAMEADO", "PULIDO", "20MM", "-"}
                )
                for n, c in working_scope:
                    if c != matched_cat:
                        continue  # Mismo catálogo = misma familia.
                    n_upper = n.upper()
                    if ("EXTRA 2" in n_upper or "EXTRA" in n_upper) and base_tokens.issubset(set(n_upper.split())):
                        logging.info(
                            f"[variant-default] '{material_name}' → preferring "
                            f"'{n}' (EXTRA 2 ESP) over '{matched_name}' "
                            f"[same catalog {c}]"
                        )
                        # Sustituir el tuple del match con el nombre
                        # ORIGINAL del sibling EXTRA — ya no necesitamos
                        # el stripped_to_original lookup.
                        matched_name = n
                        matched_cat = c
                        match = (n, match[1])
                        break

        if match:
            _, score = match
            # matched_name + matched_cat ya resueltos arriba.
            result = catalog_lookup(matched_cat, matched_name)
            if result.get("found"):
                logging.info(
                    f"[fuzzy] '{material_name}' → '{matched_name}' "
                    f"(score={score}, catalog={matched_cat})"
                )
                result["fuzzy_corrected_from"] = material_name
                result["fuzzy_score"] = int(score)
                result["fuzzy_catalog"] = matched_cat.replace("materials-", "")
                if detected_family:
                    result["fuzzy_family"] = detected_family

                # Detectar negación explícita del variant matcheado.
                # Caso DINALE 14/04/2026: brief dice "NO Extra 2" pero el
                # catálogo solo tiene la variante EXTRA 2 ESP → el operador
                # debe saber que el sistema igual devolvió esa variante.
                _neg_patterns = [
                    r'\bno\s+extra\s*2',
                    r'\bsin\s+extra\s*2',
                    r'\b(?:no|sin)\s+fiamatado',
                    r'\b(?:no|sin)\s+flameado',
                    r'\b(?:no|sin)\s+leather',
                    r'\b(?:no|sin)\s+pulido',
                ]
                _input_norm = material_name.lower()
                _matched_norm = matched_name.lower()
                for _pat in _neg_patterns:
                    _m_neg = _re_thk.search(_pat, _input_norm)
                    if not _m_neg:
                        continue
                    # ¿La variante negada está en el match?
                    _neg_kw = _m_neg.group(0).split()[-1]  # 'extra', 'fiamatado', etc.
                    if _neg_kw in _matched_norm or (
                        _neg_kw == "extra" and "extra" in _matched_norm
                    ):
                        result["variant_negated"] = {
                            "requested": _m_neg.group(0),
                            "returned": matched_name,
                            "reason": (
                                f"Operador pidió '{_m_neg.group(0)}' pero el catálogo "
                                f"solo tiene '{matched_name}' para este material. "
                                "Se devuelve esa variante por default — confirmar con operador."
                            ),
                        }
                        logging.warning(
                            f"[variant-negated] input='{material_name}' "
                            f"negó '{_neg_kw}' pero match es '{matched_name}' "
                            "(única variante disponible)"
                        )
                        break
                return result

        # No hay match con score_cutoff suficiente → suggestions estable
        # sin cross-family silencioso (PR #396).
        suggestions = _top_suggestions(_clean_input, working_scope, top_k=3)
        detail = (
            f"Material '{material_name}' no encontrado en familia "
            f"'{detected_family}'. Revisar sugerencias o corregir nombre."
            if detected_family
            else f"Material '{material_name}' no encontrado con confianza "
                 f"suficiente. Revisar sugerencias o especificar familia "
                 f"(puraprima, silestone, dekton, granito, etc.)."
        )
        return {
            "found": False,
            "error": detail,
            "family": detected_family,
            "suggestions": suggestions,
        }
    except ImportError:
        logging.warning("thefuzz not installed — fuzzy matching disabled")

    return {
        "found": False,
        "error": f"Material '{material_name}' no encontrado en ningún catálogo",
        "suggestions": [],
    }


def _find_flete(localidad: str) -> dict:
    """Find flete price for a zone using exact match from config.json zone_aliases."""
    zone_key = localidad.lower().strip()
    aliases = _load_zone_aliases()
    zone_info = aliases.get(zone_key)
    if zone_info:
        result = catalog_lookup("delivery-zones", zone_info["sku"])
        if result.get("found"):
            result["pulido_extra"] = zone_info.get("pulido_extra", False)
        return result
    logging.warning(f"Flete: zona '{localidad}' (normalizada: '{zone_key}') no encontrada en zone_aliases de config.json")
    return {"found": False, "error": f"Zona '{localidad}' no encontrada en zone_aliases de config.json. Agregar alias en config.json → zone_aliases."}


def _has_alzada_piece(pieces: list) -> bool:
    """True si el despiece contiene al menos una pieza de alzada.

    PR #376 — Usado como gate de `Agujero toma corriente`: el agujero se
    realiza físicamente EN LA ALZADA, por lo tanto sin alzada no hay
    dónde agujerear. Este helper deduplica la heurística de detección
    que ya usa el renderer (`is_alzada = desc_lower.startswith("alzada")`
    en list_pieces, línea 431, 998).

    Se acepta tanto dict como ORM-model-dumped (patrón de este módulo,
    ver `calculate_quote` donde se normaliza cada p).
    """
    for p in pieces or []:
        pd = p if isinstance(p, dict) else p.model_dump()
        desc = (pd.get("description") or "").lower().lstrip()
        if desc.startswith("alzada"):
            return True
    return False


def _get_mo_price(sku: str) -> tuple:
    """Get MO price with IVA and base price from labor.json.
    Returns (price_with_iva, price_base).
    """
    result = catalog_lookup("labor", sku)
    if result.get("found"):
        return result.get("price_ars", 0), result.get("price_ars_base", 0)
    return 0, 0


def calculate_m2(pieces: list) -> tuple[float, list[dict]]:
    """Calculate total m2 from pieces. Returns (total_m2, piece_details).

    Respects the optional `quantity` field on each piece. A piece like
    {largo: 1.43, prof: 0.62, quantity: 2} contributes 1.43 × 0.62 × 2
    to the total and keeps quantity=2 in its detail entry.

    If a piece declares `m2_override` (float), that value is used as the
    per-unit m² verbatim — largo × prof is NOT computed. Use case: Planilla
    de Cómputo del comitente en obras de edificio, donde el m² ya incluye
    zócalo/frente y D'Angelo cotiza sin recalcular. El detail entry conserva
    `override=True` para que el renderer del PDF marque la fila con *.

    Rounding policy (BUG-045):
    - Per piece: NO rounding (sum raw values)
    - Total: round to 2 decimals
    - Display per piece: 4 decimals (for traceability only)
    """
    total = 0.0
    raw_details = []
    for p in pieces:
        largo = p.get("largo", 0)
        dim2 = p.get("prof") or p.get("alto") or 0
        qty_in = int(p.get("quantity", 1) or 1)
        override = p.get("m2_override")
        if override is not None:
            try:
                override_val = float(override)
            except (TypeError, ValueError):
                override_val = None
        else:
            override_val = None
        if override_val is not None and override_val > 0:
            raw_m2 = override_val
            used_override = True
        else:
            raw_m2 = largo * dim2
            used_override = False

        # Faldón/frentín: contribuye SOLO a MO (armado frentín × ml), no al
        # m² de material. Caso DINALE 14/04/2026: la planilla del comitente
        # ya trae los m² con zócalo/frente incluidos; al listar el frentín
        # como pieza aparte, sumar su m² al material lo duplica. La regla
        # del negocio: los ml del frentín van al SKU FALDON (MO), no al
        # material. Ver rules/calculation-formulas.md § Frentín.
        _desc_head = (p.get("description") or "").lower().lstrip()
        is_frentin_piece = (
            _desc_head.startswith("faldón")
            or _desc_head.startswith("faldon")
            or _desc_head.startswith("frentín")
            or _desc_head.startswith("frentin")
        )
        # m² por pieza con half-up a 2 decimales (lo que el operador ve en la
        # columna m²). Sumamos al total el valor ya redondeado para que el
        # total coincida con la suma visual — antes total_m2 usaba los raw
        # floats (1.5749...), generando inconsistencias entre display (5.34)
        # y precio calculado (5.33 × USD → cobraba menos de lo mostrado).
        m2_piece_2d = _round_half_up(raw_m2, 2) if not is_frentin_piece else 0
        if not is_frentin_piece:
            total += m2_piece_2d * qty_in  # respect input quantity
        raw_details.append({
            "description": p.get("description", ""),
            "largo": largo,
            "dim2": dim2,
            "m2": m2_piece_2d,
            "quantity": qty_in,        # preserve explicit qty
            "override": used_override, # renderer uses this to add '*' mark
            "_is_frentin": is_frentin_piece,
        })
    # Group identical pieces by description+dimensions.
    # If the operator already provided an explicit quantity on each piece,
    # do NOT re-increment it (that was the old behavior for repeated rows
    # without qty). We only increment when we see a duplicate row that did
    # not declare its own quantity.
    details = []
    seen = {}
    for d in raw_details:
        key = f'{d["largo"]:.4f}_{d["dim2"]:.4f}_{d["description"]}'
        if key in seen:
            # Duplicate description+dims: sum quantities (handles either
            # "repeated rows" style or mixed-style input defensively).
            seen[key]["quantity"] += d["quantity"]
        else:
            seen[key] = dict(d)
            details.append(seen[key])
    return round(total, 2), details


def list_pieces(pieces: list, is_edificio: bool = False) -> dict:
    """Format pieces for Paso 1 display: correct labels + total m² (deterministic).

    Returns structured data that the agent must use verbatim in Paso 1.
    Zócalos use "ml" format, mesadas use "largo × prof", >3m gets "2 TRAMOS"
    ONLY for residential quotes (is_edificio=False). For edificios the legend
    is suppressed since they list many pieces by tipología.
    """
    total_m2, piece_details = calculate_m2(
        [p if isinstance(p, dict) else p for p in pieces]
    )

    formatted = []
    for pd in piece_details:
        desc = pd.get("description", "")
        desc_lower = desc.lower().lstrip()
        # Pure zócalo: description starts with "zócalo". Mesadas que mencionan
        # "c/zócalo h:Xcm" son mesadas, no zócalos — deben conservar su label.
        is_zocalo = (
            desc_lower.startswith("zócalo")
            or desc_lower.startswith("zocalo")
            or desc_lower.startswith("zoc ")
        )
        # Alzada: render simple "L × D Alzada" — sin detalle del operador
        # ni leyenda TRAMOS. Las alzadas no se parten en 2 tramos como mesadas.
        is_alzada = desc_lower.startswith("alzada")
        qty = pd.get("quantity", 1)

        if is_zocalo:
            label = f"{pd['largo']:.2f}ML X {pd['dim2']:.2f} ZOC"
        elif is_alzada:
            label = f"{pd['largo']:.2f} × {pd['dim2']:.2f} Alzada"
        elif pd.get("_is_frentin"):
            # Faldón/frentín: solo se contabiliza como MO (armado × ml).
            # NO sumar m² al material. Render con ml para que el operador
            # sepa que no aporta al bruto material.
            label = f"{pd['largo']:.2f}ML FALDON"
        else:
            label = f"{desc} — {pd['largo']:.2f} x {pd['dim2']:.2f}"
            if pd["largo"] >= 3.0 and not is_edificio:
                label += " (SE REALIZA EN 2 TRAMOS)"

        m2_display = _round_half_up(pd["m2"] * qty, 2)
        entry = {"label": label, "m2": m2_display}
        if qty > 1:
            entry["qty"] = qty
        formatted.append(entry)

    return {
        "ok": True,
        "pieces": formatted,
        "total_m2": total_m2,
    }


def build_deterministic_paso1(
    list_pieces_result: dict,
    *,
    client_name: str | None = None,
    project: str | None = None,
    material: str | None = None,
) -> str:
    """Build Paso 1 markdown from `list_pieces` output — 100% deterministic.

    PR #412 — Paso 1 venía siendo armado libremente por el LLM como
    respuesta de chat. El LLM ignoraba `piece.m2` y `total_m2` del
    response y rehacía la cuenta como `largo × prof` (m²/u, sin
    multiplicar por `qty`). Caso DYSCON: tabla decía 9.43 m² cuando
    `total_m2` era 42.39, y el propio modelo emitía un warning de
    "DISCREPANCIA DETECTADA" como efecto secundario del bug.

    Patrón: gemelo a `build_deterministic_paso2` (línea ~1607). El
    handler de `list_pieces` en agent.py inyecta este string como
    `result["_paso1_rendered"]`. El system prompt instruye al LLM a
    usarlo verbatim — sin recalcular ni acompañar con tabla propia.

    Reglas del render:
    - Una fila por `piece` del response.
    - Columna `Cant`: `×N` cuando `qty > 1`, `—` cuando `qty == 1`.
    - Columna `m²`: usar **`piece.m2` literal** (ya viene multiplicado
      por qty desde `list_pieces:821`).
    - TOTAL: usar **`total_m2` literal** del response (suma del
      backend, fuente de verdad — nunca recalcular sumando filas).
    - Header con cliente/obra/material si se pasaron.
    """
    pieces = list_pieces_result.get("pieces") or []
    total_m2 = list_pieces_result.get("total_m2", 0)

    lines: list[str] = []

    # Header — cliente / obra / material (si vienen).
    if client_name or project:
        header_parts = []
        if client_name:
            header_parts.append(f"**{client_name}**")
        if project:
            header_parts.append(f"**Obra:** {project}")
        lines.append(" | ".join(header_parts))
        lines.append("")

    # Material + total m² del sector.
    if material:
        # `_round_half_up` para alinear display con el cálculo (ARS rules).
        _total_disp = _round_half_up(total_m2, 2)
        # Display ARS-style: 42.39 → "42,39" (coma decimal). El render
        # del Paso 2 hace lo mismo en otras partes del breakdown.
        _total_str = f"{_total_disp:.2f}".replace(".", ",")
        lines.append(f"### {material} — {_total_str} m²")
        lines.append("")

    # Tabla de piezas.
    lines.append("| Pieza | Cant | m² |")
    lines.append("|---|---|---|")
    for p in pieces:
        label = p.get("label") or ""
        qty = p.get("qty", 1) or 1
        try:
            qty_int = int(qty)
        except (TypeError, ValueError):
            qty_int = 1
        cant_disp = f"×{qty_int}" if qty_int > 1 else "—"
        m2 = p.get("m2", 0)
        m2_disp = f"{m2:.2f}".replace(".", ",")
        lines.append(f"| {label} | {cant_disp} | {m2_disp} |")

    # TOTAL — fuente única de verdad: `total_m2` del response.
    _total_disp = _round_half_up(total_m2, 2)
    _total_str = f"{_total_disp:.2f}".replace(".", ",")
    lines.append(f"| **TOTAL** | | **{_total_str} m²** |")

    return "\n".join(lines)


def calculate_merma(m2_needed: float, material_type: str, is_edificio: bool = False) -> dict:
    """Calculate merma for synthetic materials.

    Edificios NEVER apply merma — the operator handles piece cutting
    per tipología manually. Only residential quotes have merma logic.
    """
    # Edificio: no merma regardless of material
    if is_edificio:
        return {"aplica": False, "desperdicio": 0, "sobrante_m2": 0, "motivo": "Edificio — sin merma"}

    mat_lower = material_type.lower()

    # Negro Brasil: never merma
    if "negro brasil" in mat_lower:
        return {"aplica": False, "desperdicio": 0, "sobrante_m2": 0, "motivo": "Negro Brasil — nunca merma"}

    # Natural stone: no merma
    is_synthetic = any(s in mat_lower for s in SINTETICOS)
    if not is_synthetic:
        return {"aplica": False, "desperdicio": 0, "sobrante_m2": 0, "motivo": "Piedra natural — sin merma"}

    # Get reference size
    if mat_lower in MERMA_MEDIA_PLACA or any(s in mat_lower for s in MERMA_MEDIA_PLACA):
        plate_m2 = PLATE_SIZES.get("silestone", 4.20)
        m2_ref = plate_m2 / 2  # media placa
        ref_label = f"media placa ({m2_ref} m²)"
        # How many half plates needed
        n_halves = math.ceil(m2_needed / m2_ref)
        m2_ref_total = n_halves * m2_ref
    else:
        # Find plate size for this material type
        plate_m2 = 4.20  # default
        for key, size in PLATE_SIZES.items():
            if key in mat_lower:
                plate_m2 = size
                break
        m2_ref = plate_m2  # placa entera
        ref_label = f"placa entera ({m2_ref} m²)"
        n_plates = math.ceil(m2_needed / m2_ref)
        m2_ref_total = n_plates * m2_ref

    desperdicio = round(m2_ref_total - m2_needed, 2)

    merma_threshold = cfg("merma.small_piece_threshold_m2", 1.0)
    if desperdicio < merma_threshold:
        return {
            "aplica": False,
            "desperdicio": desperdicio,
            "sobrante_m2": 0,
            "motivo": f"Desperdicio {desperdicio} m² < {merma_threshold} → sin sobrante (ref: {ref_label})",
        }
    else:
        sobrante = round(desperdicio / 2, 2)
        return {
            "aplica": True,
            "desperdicio": desperdicio,
            "sobrante_m2": sobrante,
            "motivo": f"Desperdicio {desperdicio} m² ≥ {merma_threshold} → sobrante {sobrante} m² (ref: {ref_label})",
        }


def calculate_quote(input_data: dict) -> dict:
    """
    Calculate a complete quote from input data.
    Returns dict with all quote details, ready for document generation.
    """
    warnings: list[str] = []  # Collect warnings visible to the agent

    client_name = (input_data.get("client_name") or "").strip()
    # PR: cliente obligatorio también (antes solo chequeaba project).
    _placeholder_clients = {"", "n/a", "n/d", "sin cliente", "-", "—", "."}
    if client_name.lower() in _placeholder_clients:
        return {
            "ok": False,
            "error": (
                "⛔ Falta el nombre del cliente. Es obligatorio. "
                "PEDIRLO al operador antes de calcular: "
                "'¿Nombre del cliente?'. NUNCA inventarlo ni tomarlo del "
                "nombre del archivo/proyecto."
            ),
        }
    project = (input_data.get("project") or "").strip()
    # PR #15 — proyecto obligatorio. El operador siempre da contexto de la
    # OBRA en el brief (ej: "OBRA: Ampliación Unidad Penitenciaria N°12").
    # Antes el calculator caía a default "Cocina" cuando project venía vacío,
    # lo que enmascaraba que la agente no había extraído la información.
    # Ahora retornamos error explícito → la agente debe pedirlo al operador.
    # "Cocina" se permite (presupuestos residenciales suelen usarlo como
    # proyecto). Lo que NO se permite es vacío o placeholders genéricos
    # tipo "n/a", "sin proyecto", "-".
    _placeholder_projects = {"", "n/a", "n/d", "sin proyecto", "sin obra", "-", "—", "."}
    if project.lower().strip() in _placeholder_projects:
        return {
            "ok": False,
            "error": (
                "⛔ Falta el nombre del proyecto/obra. Es obligatorio. "
                "Buscarlo en el brief del operador (suele venir como 'OBRA:', "
                "'PROYECTO:', 'Obra:'). Si no aparece, PEDIRLO al operador "
                "antes de calcular: '¿Cuál es el nombre de la obra/proyecto?'."
            ),
        }
    material_name = input_data["material"]
    pieces = input_data["pieces"]
    localidad = input_data.get("localidad") or "rosario"  # Default Rosario if empty
    skip_flete = input_data.get("skip_flete", False)
    colocacion = input_data.get("colocacion", True)
    is_edificio = input_data.get("is_edificio", False)
    pileta = input_data.get("pileta")
    pileta_qty = input_data.get("pileta_qty", 1)
    pileta_sku = input_data.get("pileta_sku")
    anafe = input_data.get("anafe", False)
    # anafe_qty: explicit count of anafes (edificio multi-tipología).
    # Default 1 for residential; edificio operator passes the total.
    anafe_qty = int(input_data.get("anafe_qty", 1) or 1)
    frentin = input_data.get("frentin", False)
    inglete = input_data.get("inglete", False)
    pulido = input_data.get("pulido", False)
    plazo = input_data["plazo"]
    discount_pct = input_data.get("discount_pct", 0)
    # MO discount is a separate comercial discount ONLY over MO items, EXCLUDING
    # flete. Used in edificio quotes when operator declares "5% sobre MO".
    # Flete NEVER gets any discount (neither mo_discount_pct nor ÷1.05 edificio).
    mo_discount_pct = input_data.get("mo_discount_pct", 0)

    # ── Auto-detect architect discount (deterministic, not LLM-dependent) ──
    if client_name and not discount_pct:
        from app.modules.agent.tools.catalog_tool import check_architect
        arch_result = check_architect(client_name)
        if arch_result.get("found") and arch_result.get("discount", True):
            # Apply architect discount automatically
            imported_pct = cfg("discount.imported_percentage", 5)
            national_pct = cfg("discount.national_percentage", 8)
            # Will be applied after we know the currency (below)
            input_data["_auto_architect_discount"] = True
            logging.info(f"Auto-detected architect: '{client_name}' → {arch_result.get('name')}. Discount will be applied.")

    # ── Edificio guardrails ──
    if is_edificio:
        # Force no colocación
        if colocacion:
            logging.warning(f"Edificio guardrail: forcing colocacion=false (was true)")
            colocacion = False

        # Auto-count piletas from piece descriptions if not provided
        if pileta and pileta_qty <= 1:
            # PR #407 fix A — sumar `quantity` (no contar 1 por línea).
            # Antes: una pieza "Mesada con pileta × 24" contaba 1.
            # Ahora: cuenta 24. Caso DYSCON no se beneficia de este path
            # (sus descripciones no tienen keywords), pero edificios con
            # etiquetado correcto ahora sí escalan.
            _kw_pileta = ["pileta", "bacha", "lavatorio", "kitchenette",
                          "c/pileta", "c/bacha"]
            auto_pileta_count = sum(
                int(p.get("quantity", 1) or 1)
                for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces)
                if any(kw in (p.get("description") or "").lower() for kw in _kw_pileta)
            )
            if auto_pileta_count > 1:
                pileta_qty = auto_pileta_count
                logging.info(
                    f"Edificio guardrail: auto-detected {pileta_qty} piletas "
                    f"from piece descriptions (sum of quantities)"
                )
            elif input_data.get("_pileta_inferred_by_guardrail"):
                # PR #407 fix B (acotado por origen) — fallback solo si
                # la pileta fue **auto-inyectada** por el guardrail
                # `mo-list-authority` (agent.py:5469). En ese caso el
                # operador no declaró pileta y no etiquetó piezas; la
                # convención del operador es que cada mesada del edificio
                # lleva pileta. Caso DYSCON: 32 mesadas → 32 piletas.
                #
                # NO se activa cuando:
                #   - El operador pasó `pileta_qty` explícito (ya filtra
                #     el `pileta_qty <= 1` arriba).
                #   - La pileta vino del operador (sin flag).
                #   - Hay match por keyword (rama anterior toma precedencia).
                #   - No hay mesadas con quantity > 1.
                #
                # Excluye: zócalos, frentín, regrueso, alzada, faldón —
                # esas piezas no llevan pileta propia.
                _kw_excluded = ("zócalo", "zocalo", "frentín", "frentin",
                                "regrueso", "alzada", "faldón", "faldon")
                _mesada_qty = sum(
                    int(p.get("quantity", 1) or 1)
                    for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces)
                    if "mesada" in (p.get("description") or "").lower()
                    and not any(kw in (p.get("description") or "").lower()
                                for kw in _kw_excluded)
                )
                if _mesada_qty > 1:
                    pileta_qty = _mesada_qty
                    logging.info(
                        f"Edificio + pileta auto-inyectada por mo-list-authority: "
                        f"pileta_qty={pileta_qty} (suma de quantities de mesadas)"
                    )

        # Auto-calculate frentin_ml from piece descriptions if not provided
        if frentin and not input_data.get("frentin_ml"):
            auto_ml = sum(
                p.get("largo", 0)
                for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces)
                if any(kw in (p.get("description") or "").lower() for kw in ["faldón", "faldon", "frentín", "frentin"])
            )
            if auto_ml > 0:
                input_data["frentin_ml"] = round(auto_ml, 2)
                logging.info(f"Edificio guardrail: auto-detected {auto_ml:.2f} ml of frentín from piece descriptions")

        # Validate pieces have largo and prof/dim2 — never accept pre-multiplied m² only.
        # If operator passes only m² without dimensions, the breakdown is opaque and the
        # agent will invent fake dimensions (e.g. "6.0 × 1.0" for a 6 m² piece).
        _pieces_missing_dims = []
        for _idx, _p in enumerate((pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces)):
            _largo = _p.get("largo", 0) or 0
            _prof = _p.get("prof", 0) or _p.get("dim2", 0) or _p.get("ancho", 0) or 0
            if _largo <= 0 or _prof <= 0:
                _pieces_missing_dims.append(_p.get("description", f"pieza #{_idx}"))
        if _pieces_missing_dims:
            warnings.append(
                "⛔ Edificio: todas las piezas deben tener largo y prof (no solo m²). "
                f"Faltan dimensiones en: {', '.join(_pieces_missing_dims[:5])}. "
                "Pedí al operador las medidas completas del despiece (ej: 2.34 × 0.62)."
            )
    date_str = input_data.get("date") or datetime.now().strftime("%d.%m.%Y")

    # 1. Find material
    mat_result = _find_material(material_name)
    if not mat_result.get("found"):
        return {"ok": False, "error": mat_result.get("error", f"Material '{material_name}' no encontrado")}

    # Surface variant negation: operador pidió "NO Extra 2" / "sin Fiamatado"
    # pero el catálogo solo tiene esa variante → el sistema la devuelve igual
    # y debe flaguear al operador que confirme.
    if mat_result.get("variant_negated"):
        _vn = mat_result["variant_negated"]
        warnings.append(
            f"⚠️ VARIANT NEGADA: operador pidió '{_vn['requested']}' pero el "
            f"catálogo solo tiene '{_vn['returned']}' como opción. Se cotiza "
            "con esa variante — confirmar con operador antes de generar PDF."
        )

    mat_type = _detect_material_type(mat_result)
    is_sint = any(s in mat_type for s in SINTERIZADOS)
    currency = mat_result.get("currency", "USD")

    if currency == "USD":
        price_unit = mat_result["price_usd"]
        price_base = mat_result["price_usd_base"]
    else:
        price_unit = mat_result["price_ars"]
        price_base = mat_result["price_ars_base"]

    # 2. Calculate m2
    total_m2, piece_details = calculate_m2([p if isinstance(p, dict) else p.model_dump() for p in pieces])

    # 3. Merma
    merma = calculate_merma(total_m2, mat_result.get("name", material_name), is_edificio=is_edificio)

    # 4. Auto-apply architect discount if detected
    if input_data.get("_auto_architect_discount") and not discount_pct:
        if currency == "USD":
            discount_pct = cfg("discount.imported_percentage", 5)
        else:
            discount_pct = cfg("discount.national_percentage", 8)
        logging.info(f"Applied auto architect discount: {discount_pct}% ({currency})")

    # 4b. Auto-apply building discount (edificio) if threshold met
    # Rule: edificio + m² ≥ building_min_m2_threshold → discount_pct = building_percentage.
    # Only auto-applies if agent didn't already set a discount_pct.
    if is_edificio and not discount_pct:
        _bmin = cfg("discount.building_min_m2_threshold", 15)
        _bpct = cfg("discount.building_percentage", 18)
        if total_m2 >= _bmin:
            discount_pct = _bpct
            logging.info(
                f"Applied auto edificio discount: {discount_pct}% "
                f"(total_m2 {total_m2} ≥ {_bmin})"
            )

    # 4b. Material total
    material_total = round(total_m2 * price_unit)
    if discount_pct > 0:
        discount_amount = round(material_total * discount_pct / 100)
        material_total_net = material_total - discount_amount
    else:
        discount_amount = 0
        material_total_net = material_total

    # 4c. Sobrante (merma) — por regla calculation-formulas.md:
    # "Bloque separado e independiente, subtotal propio. Grand total suma
    # principal + sobrante." Mismo precio unitario que el material.
    sobrante_m2 = merma.get("sobrante_m2", 0) if merma.get("aplica") else 0
    sobrante_total = round(sobrante_m2 * price_unit) if sobrante_m2 else 0

    # 5. MO items
    mo_items = []

    # Pileta (supports quantity for edificios)
    # PR #82 — respetar `pileta_qty=0` como "sin pileta", aunque el
    # operador/LLM haya pasado `pileta=empotrada_cliente`. Antes,
    # max(1, 0)=1 forzaba el ítem igual → bug de "agujero pileta
    # fantasma" cuando Valentina intentaba remover pasando qty=0.
    if pileta and pileta_qty > 0:
        qty = max(1, pileta_qty)
        if pileta in ("empotrada_cliente", "empotrada_johnson"):
            sku = "PILETADEKTON/NEOLITH" if is_sint else "PEGADOPILETA"
            price, base = _get_mo_price(sku)
            mo_items.append({"description": "Agujero y pegado pileta", "quantity": qty, "unit_price": price, "base_price": base, "total": round(price * qty)})
        elif pileta == "apoyo":
            sku = "PILETAAPOYODEKTON/NEO" if is_sint else "AGUJEROAPOYO"
            price, base = _get_mo_price(sku)
            mo_items.append({"description": "Agujero pileta apoyo", "quantity": qty, "unit_price": price, "base_price": base, "total": round(price * qty)})

    # Anafe (respects anafe_qty for edificio multi-tipología)
    if anafe:
        sku = "ANAFEDEKTON/NEOLITH" if is_sint else "ANAFE"
        price, base = _get_mo_price(sku)
        mo_items.append({
            "description": "Agujero anafe",
            "quantity": anafe_qty,
            "unit_price": price,
            "base_price": base,
            "total": round(price * anafe_qty),
        })

    # Colocación — split por ambiente cuando se detectan varios.
    # Si las piezas tienen keywords "cocina", "lavadero", "baño", etc., emitimos
    # una línea de colocación por ambiente. Cada uno respeta el mínimo de 1m².
    # Si todas las piezas son del mismo ambiente (o no se detecta ninguno),
    # se mantiene la línea única "Colocación" como antes.
    if colocacion:
        sku = "COLOCACIONDEKTON/NEOLITH" if is_sint else "COLOCACION"
        price, base = _get_mo_price(sku)
        min_qty = cfg("colocacion.min_quantity", 1.0)

        # Agrupar m² por ambiente leyendo descriptions de las piezas finales
        ambientes_m2: dict[str, float] = {}
        for pd in piece_details:
            if pd.get("_is_frentin"):
                continue
            amb = _detect_ambiente(pd.get("description", ""))
            if amb is None:
                continue
            qty_p = pd.get("quantity", 1) or 1
            ambientes_m2[amb] = ambientes_m2.get(amb, 0) + (pd.get("m2", 0) * qty_p)

        # Decidir: split solo si hay >= 2 ambientes detectados; si no, línea única.
        if len(ambientes_m2) >= 2:
            for amb, m2_amb in ambientes_m2.items():
                qty = max(m2_amb, min_qty)
                mo_items.append({
                    "description": f"Colocación {amb.lower()}",
                    "quantity": _round_half_up(qty, 2),
                    "unit_price": price,
                    "base_price": base,
                    "total": round(price * qty),
                })
        else:
            qty = max(total_m2, min_qty)
            mo_items.append({
                "description": "Colocación",
                "quantity": _round_half_up(qty, 2),
                "unit_price": price,
                "base_price": base,
                "total": round(price * qty),
            })

    # Frentín/faldón — MO is charged per METRO LINEAL, not per piece
    # frentin_ml = total metros lineales of faldón/frentín pieces
    frentin_ml = input_data.get("frentin_ml", 0)
    if frentin and frentin_ml <= 0:
        # Auto-calculate from pieces that look like faldón/frentín
        for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces):
            desc = (p.get("description") or "").lower()
            if any(kw in desc for kw in ["faldón", "faldon", "frentín", "frentin"]):
                frentin_ml += p.get("largo", 0)
        if frentin_ml <= 0:
            frentin_ml = 1  # Fallback: at least 1 ml
    if frentin and frentin_ml > 0:
        # Pegado/armado faldón: ml × precio por ml
        sku = "FALDONDEKTON/NEOLITH" if is_sint else "FALDON"
        price, base = _get_mo_price(sku)
        ml = round(frentin_ml, 2)
        mo_items.append({"description": "Armado frentín", "quantity": ml, "unit_price": price, "base_price": base, "total": round(price * ml)})
        if inglete:
            # Corte 45: ml × 2 × precio por ml (cut on both sides)
            sku_45 = "CORTE45DEKTON/NEOLITH" if is_sint else "CORTE45"
            price_45, base_45 = _get_mo_price(sku_45)
            ml_45 = round(frentin_ml * 2, 2)
            mo_items.append({"description": "Corte 45", "quantity": ml_45, "unit_price": price_45, "base_price": base_45, "total": round(price_45 * ml_45)})

    # PR #401 — Regrueso (refuerzo de espesor en frentes). Análogo al
    # frentín pero más simple:
    #   - Único SKU "REGRUESO" en labor.json (sin variante sintético).
    #   - No tiene CORTE45 asociado — el regrueso se pega plano al frente.
    #   - Cobrado por metro lineal igual que el frentín.
    #
    # Causa raíz histórica: PR #392 introdujo el detector + apply de
    # respuesta de regrueso en pending_questions, pero asumió que el
    # calculator lo procesaría automáticamente. No había bloque para
    # convertir `regrueso_ml` → mo_item, por lo que el texto fuente
    # ("M.O. REGRUESO frente 1x60,68ml") nunca se reflejaba en el costo
    # final. Este bloque lo cierra.
    regrueso = input_data.get("regrueso", False)
    regrueso_ml = input_data.get("regrueso_ml", 0)
    if regrueso and regrueso_ml <= 0:
        # Auto-calculate from pieces with "regrueso" en la descripción.
        # Mismo patrón que el auto-detect del frentín (línea 1130-1136):
        # si el operador declaró el regrueso pero no pasó ml, sumamos el
        # largo de las piezas marcadas como tal. Fallback de 1 ml si no
        # se encuentra ninguna — pero al menos genera la línea para que
        # el operador la vea (vs silenciosamente perderla).
        for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces):
            desc = (p.get("description") or "").lower()
            if "regrueso" in desc:
                regrueso_ml += p.get("largo", 0)
        if regrueso_ml <= 0:
            regrueso_ml = 1  # Fallback: at least 1 ml
    if regrueso and regrueso_ml > 0:
        price, base = _get_mo_price("REGRUESO")
        ml = round(regrueso_ml, 2)
        # PR #403 — label canónico del repo. El ejemplo validado
        # `examples/quote-030-juan-carlos-negro-brasil.md:49` usa
        # "Mano de obra regrueso x ml" como description del row de
        # MO. PR #401 (yo) había puesto "Regrueso frente" calcando
        # mal del frentín — el "frente" del brief era ubicación
        # ("regrueso del frente, h:5cm"), no parte del nombre.
        mo_items.append({
            "description": "Mano de obra regrueso x ml",
            "quantity": ml,
            "unit_price": price,
            "base_price": base,
            "total": round(price * ml),
        })

    # Flete (default: always charge unless skip_flete=True)
    if skip_flete:
        logging.info(f"Flete skipped: skip_flete=True (cliente retira en fábrica)")
    else:
        flete_result = _find_flete(localidad)
        # Fallback to Rosario if zone not found
        if not flete_result.get("found") and localidad.lower().strip() != "rosario":
            warnings.append(f"⚠️ Zona '{localidad}' no encontrada en zone_aliases. Usando flete Rosario como fallback. Agregar alias en config.json si es una zona válida.")
            logging.warning(f"Flete: zona '{localidad}' no encontrada, usando fallback Rosario")
            flete_result = _find_flete("rosario")
        if flete_result.get("found"):
            flete_price = flete_result.get("price_ars", 0)
            flete_base = flete_result.get("price_ars_base", 0)

            # Operator override: if the input explicitly declares flete_qty,
            # respect it. This matters for edificios where the operator knows
            # something the calculator doesn't (e.g. mesadas stacked per truck).
            _operator_flete_qty = input_data.get("flete_qty")
            if _operator_flete_qty and int(_operator_flete_qty) > 0:
                flete_qty = int(_operator_flete_qty)
                logging.info(f"Flete override by operator: {flete_qty} fletes (no auto-calc)")
            elif is_edificio:
                # Sum quantity per piece, not just len() — a DC-04 × 8 is 8 physical pieces, not 1.
                # Also exclude zócalos (they travel with mesadas, not as separate pieces).
                physical_pieces = [
                    p for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces)
                    if not any(kw in (p.get("description") or "").lower()
                               for kw in ["faldón", "faldon", "frentín", "frentin", "zócalo", "zocalo"])
                ]
                num_pieces = sum(int(p.get("quantity", 1) or 1) for p in physical_pieces)
                _per_trip = cfg("building.flete_mesadas_per_trip", 6)
                flete_qty = math.ceil(num_pieces / _per_trip)
                flete_qty = max(1, flete_qty)
                # Sanity cap: very high values are usually a bug (double counting).
                # Log a warning but don't silently correct — operator must see it.
                if flete_qty > 20:
                    logging.warning(
                        f"[flete-sanity] Unusually high flete_qty={flete_qty} for {num_pieces} pieces. "
                        f"Verify the input doesn't double-count quantities."
                    )
                logging.info(f"Edificio flete: {num_pieces} piezas físicas ÷ {_per_trip} = {flete_qty} fletes")
            else:
                flete_qty = 1
            mo_items.append({"description": f"Flete + toma medidas {localidad}", "quantity": flete_qty, "unit_price": flete_price, "base_price": flete_base, "total": round(flete_price * flete_qty)})

            # Pulido de cantos extra: if zone has pulido_extra=true AND colocación is on
            if colocacion and flete_result.get("pulido_extra", False):
                pulido_extra_price = round(flete_price / 2)
                pulido_extra_base = round(flete_base / 2)
                mo_items.append({"description": "Pulido de cantos", "quantity": 1, "unit_price": pulido_extra_price, "base_price": pulido_extra_base, "total": pulido_extra_price})
                logging.info(f"Pulido cantos extra for {localidad}: ${pulido_extra_price} (flete/2)")
        else:
            warnings.append(f"⚠️ FLETE NO INCLUIDO: zona '{localidad}' no encontrada ni con fallback Rosario. El presupuesto NO tiene flete.")
            logging.warning(f"Flete not found for '{localidad}' (even after fallback)")

    # Agujero toma corriente — enforcement duro por alzada (PR #376).
    # ANTES: se auto-agregaba 1 toma si había zócalo alto (>10cm) O
    # revestimiento. Esa heurística era inferencia comercial inválida:
    # correlacional (a veces aparecían juntos) pero no causal. El agujero
    # de toma se hace físicamente EN LA ALZADA — si no hay alzada, no hay
    # dónde agujerear. Anafe eléctrico tampoco implica toma
    # (caso Bernardi: cocina con anafe eléctrico pero sin alzada → el LLM
    # inferencia `tomas_qty=1`, el calculator lo agregaba sin validar).
    #
    # REGLA ACTUAL:
    #   - Sin alzada → NO agregar toma, nunca, por ningún path.
    #   - Con alzada + `tomas_qty` explícito → agregar.
    #   - Con alzada sin `tomas_qty` → no agregar (no inferir).
    #   - Si `tomas_qty > 0` pero no hay alzada → ignorar + warning fuerte
    #     de inconsistencia para revisión manual (no romper el cálculo).
    has_alzada = _has_alzada_piece(pieces)
    tomas_qty = input_data.get("tomas_qty")
    if tomas_qty and int(tomas_qty) > 0:
        if has_alzada:
            sku = "TOMASDEKTON/NEO" if is_sint else "TOMAS"
            price, base = _get_mo_price(sku)
            mo_items.append({
                "description": "Agujero toma corriente",
                "quantity": int(tomas_qty),
                "unit_price": price,
                "base_price": base,
                "total": round(price * int(tomas_qty)),
            })
        else:
            msg = (
                f"⚠️ Inconsistencia: tomas_qty={tomas_qty} pero no hay alzada "
                f"en el despiece. No se agrega 'Agujero toma corriente' "
                f"(el agujero se hace físicamente en la alzada). Si la alzada "
                f"existe pero no está en el despiece, agregala y reprocesá. "
                f"Si es error del asistente al inferir, confirmá sin toma."
            )
            warnings.append(msg)
            logging.warning(
                "[calc] toma corriente ignorado — no hay alzada (tomas_qty=%s)",
                tomas_qty,
            )

    # Sink product (physical sink, not just labor)
    sinks = []
    if pileta == "empotrada_johnson":
        sink_result = None
        if pileta_sku:
            # Specific model requested — exact lookup first
            sink_result = catalog_lookup("sinks", pileta_sku)
            if not sink_result or not sink_result.get("found"):
                # Fuzzy match by brand + model number
                from app.modules.agent.tools.catalog_tool import fuzzy_sink_lookup
                sink_result = fuzzy_sink_lookup(pileta_sku)
                if sink_result and sink_result.get("found"):
                    logging.info(f"Sink fuzzy matched: '{pileta_sku}' → {sink_result.get('name')} (SKU: {sink_result.get('sku')})")
                    warnings.append(f"Pileta '{pileta_sku}' no encontrada exacta. Se usó: {sink_result.get('name')}")
        # ⛔ NO default to QUADRAQ71A when no sku provided. This was causing phantom
        # sinks on edificio quotes where operator says "sin producto de pileta".
        # If empotrada_johnson but no sku → skip product (treat as empotrada_cliente),
        # only labor is charged. Add a warning so operator sees what happened.
        if not sink_result or not sink_result.get("found"):
            if pileta_sku:
                warnings.append(
                    f"⚠️ Pileta '{pileta_sku}' no encontrada en catálogo. "
                    "No se incluyó producto. Si debería ir, especificá el SKU correcto."
                )
            else:
                warnings.append(
                    "ℹ️ Pileta empotrada sin SKU específico → solo MO PEGADOPILETA, "
                    "sin producto. Si Johnson debe proveerla, pasar pileta_sku."
                )
            sink_result = None  # explicit: no sink product added
        # DEPRECATED: QUADRAQ71A default removed. Kept as no-op branch for safety.
        if False and (not sink_result or not sink_result.get("found")):
            sink_result = catalog_lookup("sinks", "QUADRAQ71A")
            if pileta_sku:
                warnings.append(f"Pileta '{pileta_sku}' no encontrada. Se usó QUADRA Q71A por defecto. Verificar con operador.")
        if sink_result and sink_result.get("found"):
            sink_price = sink_result.get("price_ars", 0)
            sinks.append({
                "name": sink_result.get("name", "Pileta Johnson"),
                "quantity": 1,
                "unit_price": sink_price,
            })
            logging.info(f"Added sink product: {sink_result.get('name')} @ ${sink_price}")

    # Edificio: MO ÷1.05 (except flete — flete NEVER discounted)
    if is_edificio:
        for item in mo_items:
            if "flete" not in item["description"].lower():
                # Redondear unit_price primero, luego recomputar total =
                # round(unit × qty). Antes se redondeaban unit y total por
                # separado (round(unit/1.05) vs round(total/1.05)), y con
                # edificio + mo_discount_pct esto generaba una deriva de
                # 1-3 pesos entre el "unit × qty" que muestra el PDF y el
                # total_ars que suma el grand total. Esta versión garantiza
                # que unit × qty == total siempre.
                item["unit_price"] = round(item["unit_price"] / 1.05)
                item["total"] = round(item["unit_price"] * item["quantity"])
                item["edificio_discount"] = True
        logging.info(f"Edificio MO ÷1.05 applied (except flete)")

    # Optional commercial MO discount (e.g. "5% sobre MO" for building quotes).
    # Applies ONLY to MO items that are NOT flete. Sum then round.
    mo_discount_amount = 0
    if mo_discount_pct and mo_discount_pct > 0:
        _mo_subtotal_excl_flete = sum(
            item["total"] for item in mo_items
            if "flete" not in item["description"].lower()
        )
        mo_discount_amount = round(_mo_subtotal_excl_flete * mo_discount_pct / 100)
        logging.info(
            f"MO discount applied: {mo_discount_pct}% of ${_mo_subtotal_excl_flete} "
            f"(excluding flete) = -${mo_discount_amount}"
        )

    # Totals
    total_sinks_ars = sum(s["unit_price"] * s["quantity"] for s in sinks)
    total_mo_ars = sum(item["total"] for item in mo_items)
    # Subtract MO commercial discount from the MO total (never affects flete).
    total_mo_ars = total_mo_ars - mo_discount_amount

    if currency == "USD":
        total_ars = total_mo_ars + total_sinks_ars
        total_usd = material_total_net + sobrante_total
    else:
        total_ars = total_mo_ars + total_sinks_ars + material_total_net + sobrante_total
        total_usd = 0

    # Build sectors for document generation (group identical pieces)
    sectors = []
    raw_labels = []
    has_m2_override = False
    for pd in piece_details:
        if pd["m2"] > 0:
            desc_lower = (pd["description"] or "").lower().lstrip()
            # Pure zócalo pieces have descriptions that START with "zócalo"
            # (e.g. "Zócalo 1.50 × 0.05"). Pieces like "Mesada recta c/zócalo
            # h:10cm" are MESADAS that happen to include a zócalo in their
            # m² — they must render with the full label, not collapsed to
            # a ZOC row. Check start-of-string only.
            is_zocalo = (
                desc_lower.startswith("zócalo")
                or desc_lower.startswith("zocalo")
                or desc_lower.startswith("zoc ")
            )
            # Alzada: formato simple "L × D Alzada" — descarta detalle del
            # operador (ej: "corrida (fondo completo sin heladera)") y la
            # leyenda TRAMOS. Las alzadas no se listan como mesadas partidas.
            is_alzada = desc_lower.startswith("alzada")
            if is_zocalo:
                label = f'{pd["largo"]:.2f}ML X {pd["dim2"]:.2f} ZOC'
            elif is_alzada:
                label = f'{pd["largo"]:.2f} × {pd["dim2"]:.2f} Alzada'
            else:
                dim2_label = f'{pd["largo"]:.2f} × {pd["dim2"]:.2f}'
                # PR #48 — strip defensivo: si Valentina metió las dimensiones
                # dentro del description (ej: "ME01-B Mesada recta - 2.15m ×
                # 0.60m c/zócalo h:10cm"), se duplican cuando el builder
                # antepone dim2_label. Limpiamos patrones "- N.Nm × N.Nm" /
                # "- N.N m x N.N m" ubicados dentro del description.
                import re as _re_dim
                _clean_desc = _re_dim.sub(
                    r'\s*[-–—]\s*\d+[.,]?\d*\s*m\s*[×xX]\s*\d+[.,]?\d*\s*m\s*',
                    ' ',
                    pd["description"] or "",
                )
                _clean_desc = _re_dim.sub(r'\s{2,}', ' ', _clean_desc).strip()
                label = f'{dim2_label} {_clean_desc}'
                # "SE REALIZA EN 2 TRAMOS" only for residential — edificios
                # already list many pieces by tipología, legend adds noise.
                if pd["largo"] >= 3.0 and not is_edificio:
                    label += " (SE REALIZA EN 2 TRAMOS)"
            # Mark rows whose m² came from operator-declared Planilla de
            # Cómputo. Renderer looks for the trailing '*' to apply footnote.
            if pd.get("override"):
                label = f"{label} *"
                has_m2_override = True
            # PR #14 — multiplicador embebido en el label cuando la pieza
            # tiene cantidad > 1 (caso DINALE: ME04-B × 4, ME04b-B × 2).
            # Antes el grouping deduplicaba por label idéntico y agregaba
            # "(×N)" solo si había duplicados textuales. Cuando el operador
            # pasa una sola pieza con quantity=N, el label tiene que reflejar
            # esa cantidad explícitamente para que el cliente no confunda 1
            # tipología con 1 unidad.
            _qty = pd.get("quantity", 1)
            if _qty and _qty > 1:
                label = f"{label} (×{_qty})"
            raw_labels.append(label)
    # Group duplicates: "0.60 × 0.38 Mesada" × 6 → "0.60 × 0.38 Mesada (×6)"
    piece_labels = []
    seen = {}
    for lbl in raw_labels:
        if lbl in seen:
            seen[lbl] += 1
        else:
            seen[lbl] = 1
            piece_labels.append(lbl)
    piece_labels = [f"{lbl} (×{seen[lbl]})" if seen[lbl] > 1 else lbl for lbl in piece_labels]
    if piece_labels:
        sectors.append({"label": project, "pieces": piece_labels})

    # ── Delivery days: apply tier by m² only if range_enabled in config ──
    import re as _re_plazo
    default_days = cfg("delivery_days.default", 30)
    range_enabled = cfg("delivery_days.range_enabled", False)
    _plazo_match = _re_plazo.search(r'(\d+)', plazo or "")
    _plazo_days = int(_plazo_match.group(1)) if _plazo_match else None
    if range_enabled and _plazo_days == default_days:
        tiers = cfg("delivery_days.tiers", [])
        for tier in sorted(tiers, key=lambda t: t.get("max_m2", 999)):
            if total_m2 <= tier.get("max_m2", 999):
                plazo = tier.get("display", plazo)
                logging.info(f"Delivery tier applied: {total_m2} m² → {plazo}")
                break

    return {
        "ok": True,
        "client_name": client_name,
        "project": project,
        "date": date_str.replace("/", "."),
        "delivery_days": plazo,
        "material_name": mat_result.get("name", material_name),
        "material_type": mat_type,
        "thickness_mm": mat_result.get("thickness_mm", 20),
        "material_m2": total_m2,
        "material_price_unit": price_unit,
        "material_price_base": price_base,
        "material_currency": currency,
        "material_total": material_total_net,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "mo_discount_pct": mo_discount_pct,
        "mo_discount_amount": mo_discount_amount,
        "merma": merma,
        "sobrante_m2": sobrante_m2,
        "sobrante_total": sobrante_total,
        "piece_details": piece_details,
        "mo_items": mo_items,
        # MO subtotal solo (pegado + frentín + flete + ... − mo_discount).
        # Distinto de total_ars que es el GRAND TOTAL (MO + sinks + material si ARS).
        # Se expone para que el render del Paso 2 muestre TOTAL MO ≠ GRAND TOTAL.
        "total_mo_ars": total_mo_ars,
        "total_ars": total_ars,
        "total_usd": total_usd,
        "sectors": sectors,
        "has_m2_override": has_m2_override,
        "sinks": sinks,
        # Persist input params for patch mode reconstruction
        "localidad": localidad,
        "colocacion": colocacion,
        "is_edificio": is_edificio,
        "pileta": pileta,
        "pileta_qty": pileta_qty,
        "anafe": anafe,
        "frentin": frentin,
        "frentin_ml": frentin_ml,
        # PR #401 — regrueso. Persistir en el output para patch mode
        # (re-cálculo con el mismo regrueso sin perderlo).
        "regrueso": regrueso,
        "regrueso_ml": regrueso_ml,
        "inglete": inglete,
        "pulido": pulido,
        "skip_flete": skip_flete,
        **({"warnings": warnings} if warnings else {}),
        **({"fuzzy_corrected_from": mat_result["fuzzy_corrected_from"]} if "fuzzy_corrected_from" in mat_result else {}),
        # PR #396 — metadata de trazabilidad del fuzzy match.
        **({"fuzzy_score": mat_result["fuzzy_score"]} if "fuzzy_score" in mat_result else {}),
        **({"fuzzy_catalog": mat_result["fuzzy_catalog"]} if "fuzzy_catalog" in mat_result else {}),
        **({"fuzzy_family": mat_result["fuzzy_family"]} if "fuzzy_family" in mat_result else {}),
        # Edificio validation checklist
        **({"edificio_checklist": {
            "sin_colocacion": not colocacion,
            "flete_qty": next((m["quantity"] for m in mo_items if "flete" in m["description"].lower()), 0),
            "flete_calculo": f"{next((m['quantity'] for m in mo_items if 'flete' in m['description'].lower()), 0)} fletes",
            "mo_dividido_1_05": True,
            "descuento_18": discount_pct == 18,
            "total_m2": total_m2,
            "pileta_qty": pileta_qty if pileta else 0,
            "frentin_ml": frentin_ml if frentin else 0,
        }} if is_edificio else {}),
    }


def build_deterministic_paso2(calc: dict) -> str:
    """Build Paso 2 markdown from calculate_quote output — 100% deterministic.

    This is the source of truth for Paso 2 display. Claude must use this
    text verbatim and NOT modify prices, MO items, or totals.
    """
    mat_name = calc.get("material_name", "")
    mat_m2 = calc.get("material_m2", 0)
    price_unit = calc.get("material_price_unit", 0)
    price_base = calc.get("material_price_base", 0)
    currency = calc.get("material_currency", "USD")
    mat_total_bruto = round(mat_m2 * price_unit)
    discount_pct = calc.get("discount_pct", 0)
    discount_amount = calc.get("discount_amount", 0)
    mat_total_net = calc.get("material_total", mat_total_bruto)
    delivery = calc.get("delivery_days", "")
    client = calc.get("client_name", "")
    project = calc.get("project", "")
    pieces = calc.get("piece_details", [])
    mo_items = calc.get("mo_items", [])
    sinks = calc.get("sinks", [])
    merma = calc.get("merma", {})
    total_ars = calc.get("total_ars", 0)
    total_usd = calc.get("total_usd", 0)
    warnings = calc.get("warnings", [])

    def fmt_ars(v): return f"${v:,.0f}".replace(",", ".")
    def fmt_usd(v): return f"USD {v:,.0f}".replace(",", ".")

    lines = []
    lines.append(f"## PASO 2 — Validación — {client} / {project}")
    lines.append(f"Fecha: {calc.get('date', '')} | Demora: {delivery} | {calc.get('localidad', 'Rosario')}")
    lines.append("")

    # Material header — display half-up para que coincida con Paso 1.
    # Sin esto f"{1.575:.2f}" → "1.57" porque el float es 1.5749999...
    # El operador veía 1.57 en Paso 2 aunque Paso 1 mostraba 1.58.
    _mat_m2_disp = _round_half_up(mat_m2, 2)
    lines.append(f"**MATERIAL — {mat_name} — {_mat_m2_disp:.2f} m²**".replace(".", ","))
    lines.append("")
    # PR #43 — tabla con columna Cant y m² total (×cant). Antes solo
    # mostraba m² per-unit y el TOTAL sumaba per-unit (wrong: 9.85 vs
    # 20.16 real para EGEA con ME04×4 + ME04b×2).
    lines.append("| Pieza | Medida | Cant | m² |")
    lines.append("|---|---|---|---|")
    _sum_disp = 0.0
    for p in pieces:
        if p.get("_is_frentin"):
            continue
        desc = p.get("description", "") or ""
        # Alzadas: colapsar a "Alzada" — el detalle del operador
        # (ej: "corrida (fondo completo sin heladera)") agrega ruido en la
        # tabla de Paso 2 y es inconsistente con el label del PDF (PR #359).
        # Mesadas/placas mantienen su descripción completa.
        if desc.lower().lstrip().startswith("alzada"):
            desc = "Alzada"
        largo = p.get("largo", 0)
        dim2 = p.get("dim2", p.get("prof", 0))
        qty = p.get("quantity", 1) or 1
        # m² total = per-unit × qty. Antes solo mostraba per-unit.
        m2_unit = p.get("m2", 0)
        m2_total = _round_half_up(m2_unit * qty, 2)
        _sum_disp = _round_half_up(_sum_disp + m2_total, 2)
        _qty_cell = f"×{qty}" if qty > 1 else "—"
        lines.append(
            f"| {desc} | {largo} x {dim2} | {_qty_cell} | {m2_total:.2f} |"
            .replace(".", ",")
        )
    # Total = suma de m² totales por pieza (ya × cant). Coincide con mat_m2.
    _total_show = _sum_disp if _sum_disp > 0 else _mat_m2_disp
    lines.append(f"| **TOTAL** | | | **{_total_show:.2f} m²** |".replace(".", ","))
    lines.append("")

    # Precio
    lines.append("**Precio unitario:**")
    if currency == "USD":
        lines.append(f"- Sin IVA: USD {price_base:.0f} | Con IVA: {fmt_usd(price_unit)} | Total: {fmt_usd(mat_total_bruto)}")
    else:
        lines.append(f"- Con IVA: {fmt_ars(price_unit)} | Total: {fmt_ars(mat_total_bruto)}")
    lines.append("")

    # Merma — se COBRA como línea separada (regla calculation-formulas.md:
    # "Grand total suma principal + sobrante"). Antes se mostraba como info
    # sin sumar al total; ahora explicitamos que va al grand total.
    # Siempre se renderiza el estado (APLICA / NO APLICA) con motivo —
    # paridad con el bloque de DESCUENTOS más abajo. Si aplica=False sin
    # estado, el operador no sabe si falta calcular o si no corresponde.
    if merma.get("aplica"):
        lines.append("**MERMA — APLICA**")
        lines.append(f"- {merma.get('motivo', '')}")
        if merma.get("sobrante_m2"):
            sob_m2 = merma["sobrante_m2"]
            sob_total = round(sob_m2 * price_unit)
            _fmt_sob = fmt_usd(sob_total) if currency == "USD" else fmt_ars(sob_total)
            lines.append(f"- Sobrante facturable: **{sob_m2:.2f} m² × {fmt_usd(price_unit) if currency == 'USD' else fmt_ars(price_unit)} = {_fmt_sob}** (se suma al total)".replace(".", ","))
    else:
        lines.append("**MERMA — NO APLICA**")
        _motivo_nm = (merma.get("motivo") or "").strip()
        if _motivo_nm:
            lines.append(f"- {_motivo_nm}")
    lines.append("")

    # Descuento
    if discount_pct:
        lines.append(f"**DESCUENTO — {discount_pct}%**")
        lines.append(f"- {fmt_usd(discount_amount) if currency == 'USD' else fmt_ars(discount_amount)} sobre material")
        lines.append(f"- Total material neto: {fmt_usd(mat_total_net) if currency == 'USD' else fmt_ars(mat_total_net)}")
    else:
        lines.append("**DESCUENTOS — NO APLICA**")
    lines.append("")

    # Piletas
    if sinks:
        lines.append("**PILETAS**")
        lines.append("| Item | Cant | Precio c/IVA | Total |")
        lines.append("|---|---|---|---|")
        for s in sinks:
            total_s = round(s["unit_price"] * s["quantity"])
            lines.append(f"| {s['name']} | {s['quantity']} | {fmt_ars(s['unit_price'])} | {fmt_ars(total_s)} |")
        lines.append("")

    # Mano de obra — edificio shows ÷1.05 column and MO discount line
    is_edificio = calc.get("is_edificio", False)
    mo_discount_pct = calc.get("mo_discount_pct", 0)
    mo_discount_amount = calc.get("mo_discount_amount", 0)

    # Helper: pick correct unit label per MO item. SKUs cobrados por
    # metro lineal (FALDON, REGRUESO, CORTE45, BUÑA, MOLDURAs) usan "ml"
    # — el resto (Colocación m², piezas count) usan "m²" o sin unidad.
    def _qty_with_unit(mo: dict) -> str:
        q = mo["quantity"]
        d = (mo.get("description") or "").lower()
        is_per_ml = any(
            kw in d for kw in (
                "frentín", "frentin", "faldón", "faldon",
                "regrueso", "corte 45", "corte45", "buña",
                "moldura", "media caña",
            )
        )
        unit = "ml" if is_per_ml else "m²"
        if isinstance(q, float) and q != int(q):
            return f"{q:.2f} {unit}".replace(".", ",")
        return str(int(q))

    # TOTAL MO subtotal: priorizar el campo del calc; fallback al cálculo
    # local sumando mo_items y restando mo_discount (compatibilidad con
    # data legacy persistida sin total_mo_ars).
    _total_mo_subtotal = calc.get(
        "total_mo_ars",
        sum(m["total"] for m in mo_items) - mo_discount_amount,
    )

    lines.append("**MANO DE OBRA**")
    if is_edificio:
        lines.append("| Item | Cant | Base s/IVA | ÷1.05 | Total c/IVA |")
        lines.append("|---|---|---|---|---|")
        for mo in mo_items:
            base = mo.get("base_price", 0)
            is_flete = "flete" in mo["description"].lower()
            div_mark = "—" if is_flete else "✓"
            lines.append(
                f"| {mo['description']} | {_qty_with_unit(mo)} | {fmt_ars(round(base))} | {div_mark} | {fmt_ars(mo['total'])} |"
            )
        if mo_discount_pct:
            lines.append(
                f"| **Descuento {mo_discount_pct}% sobre MO (excluye flete)** | | | | **-{fmt_ars(mo_discount_amount)}** |"
            )
        lines.append(f"| **TOTAL MO** | | | | **{fmt_ars(_total_mo_subtotal)}** |")
    else:
        lines.append("| Item | Cant | Precio c/IVA | Total |")
        lines.append("|---|---|---|---|")
        for mo in mo_items:
            lines.append(f"| {mo['description']} | {_qty_with_unit(mo)} | {fmt_ars(mo['unit_price'])} | {fmt_ars(mo['total'])} |")
        lines.append(f"| **TOTAL MO** | | | **{fmt_ars(_total_mo_subtotal)}** |")
    lines.append("")

    # Grand total — destacado con separador visual y heading
    # Only mention "+ piletas" when there is an actual sink product line (ARS)
    # bundled into total_ars; otherwise it misleads the reader.
    lines.append("---")
    lines.append("")
    lines.append("## 💰 GRAND TOTAL")
    if currency == "USD" and total_usd:
        has_sink_product = bool(sinks) and any(
            (s.get("unit_price", 0) * s.get("quantity", 0)) > 0 for s in sinks
        )
        if has_sink_product:
            lines.append(f"### {fmt_ars(total_ars)} mano de obra + piletas + {fmt_usd(total_usd)} material")
        else:
            lines.append(f"### {fmt_ars(total_ars)} mano de obra + {fmt_usd(total_usd)} material")
    else:
        lines.append(f"### {fmt_ars(total_ars)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Warnings — evitar '⚠️ ⚠️' duplicado cuando el mensaje ya empieza con
    # el emoji (PR #43). Algunas warnings del agente (ej: variant_negated)
    # se agregan con el prefijo; otras no. Uniformar aca.
    for w in warnings:
        _wtext = w.lstrip()
        if _wtext.startswith("⚠️"):
            lines.append(_wtext)
        else:
            lines.append(f"⚠️ {_wtext}")

    lines.append("")
    lines.append("¿Confirmás para generar PDF y Excel?")

    return "\n".join(lines)
