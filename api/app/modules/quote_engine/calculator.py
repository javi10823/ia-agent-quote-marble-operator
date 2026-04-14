"""Pure Python quote calculator — no LLM, deterministic, fast."""

import math
import logging
from datetime import datetime

from app.modules.agent.tools.catalog_tool import catalog_lookup
from app.core.company_config import get as cfg

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


def _find_material(material_name: str) -> dict:
    """Search for material across all catalogs with fuzzy fallback."""
    from app.modules.agent.tools.catalog_tool import _load_catalog

    # 1. Exact match (case-insensitive via catalog_lookup)
    for cat in MATERIAL_CATALOGS:
        result = catalog_lookup(cat, material_name)
        if result.get("found"):
            return result

    # 2. Try normalized name
    normalized = _normalize_material_name(material_name)
    if normalized != material_name.lower().strip():
        for cat in MATERIAL_CATALOGS:
            result = catalog_lookup(cat, normalized)
            if result.get("found"):
                logging.info(f"[normalize] '{material_name}' → '{result.get('name')}' (normalized)")
                result["fuzzy_corrected_from"] = material_name
                return result

    # 3. Fuzzy match across all material catalogs
    try:
        from thefuzz import process as fuzz_process

        # Build list of all material names with their catalog
        all_materials: list[tuple[str, str]] = []  # (name, catalog)
        for cat in MATERIAL_CATALOGS:
            items = _load_catalog(cat)
            for item in items:
                name = item.get("name", "")
                if name:
                    all_materials.append((name, cat))

        if not all_materials:
            return {"found": False, "error": f"Material '{material_name}' no encontrado — catálogos vacíos"}

        # Filter out acabado variants (LEATHER, FIAMATADO, PULIDO, etc.)
        # unless the operator explicitly requested them. Default acabado =
        # "pulido/extra 2 esp" variant.
        #
        # Rule (PR #4 — pedido del usuario): cuando el brief no especifica
        # variante/acabado y existe un variant "EXTRA 2 ESP" del material,
        # se devuelve esa variante por default. Esto también cubre el caso
        # de espesor no coincidente (ej: brief "25mm" vs catálogo 20mm):
        # el filtrado se queda con el EXTRA 2 ESP y `_find_material` lo
        # retorna sin preguntar. Ver rules/materials-guide.md § Espesor.
        # Strip thickness tokens from input ("25mm", "— 25mm", "- 25 mm") so
        # fuzzy doesn't down-score valid matches just because the brief
        # specifies a thickness the catalog name doesn't carry.
        import re as _re_thk
        _clean_input = _re_thk.sub(
            r'[—\-–]?\s*\d{1,2}\s*mm\b', '', material_name, flags=_re_thk.IGNORECASE,
        ).strip()
        input_lower = material_name.lower()
        has_leather = "leather" in input_lower
        has_fiamatado = "fiamatado" in input_lower or "flameado" in input_lower
        filtered = [
            (n, c) for n, c in all_materials
            if (has_leather or "leather" not in n.lower())
            and (has_fiamatado or "fiamatado" not in n.lower())
        ]
        names = [m[0] for m in (filtered if filtered else all_materials)]
        match = fuzz_process.extractOne(_clean_input, names, score_cutoff=70)

        # If matched a non-EXTRA variant but an EXTRA 2 ESP exists for the
        # same base name, prefer the EXTRA 2 ESP. Detect base name as the
        # matched name minus the variant suffix.
        if match:
            matched_name = match[0]
            m_upper = matched_name.upper()
            if "EXTRA 2" not in m_upper and "EXTRA" not in m_upper:
                # Look for a sibling with EXTRA 2 (ESP) and the same base tokens
                base_tokens = set(
                    t for t in m_upper.split()
                    if t not in {"LEATHER", "FIAMATADO", "FLAMEADO", "PULIDO", "20MM", "-"}
                )
                for n, _c in filtered:
                    n_upper = n.upper()
                    if ("EXTRA 2" in n_upper or "EXTRA" in n_upper) and base_tokens.issubset(set(n_upper.split())):
                        logging.info(
                            f"[variant-default] '{material_name}' → preferring "
                            f"'{n}' (EXTRA 2 ESP) over '{matched_name}'"
                        )
                        match = (n, match[1])
                        break

        if match:
            matched_name, score = match[0], match[1]
            # Find which catalog it belongs to
            matched_cat = next(cat for name, cat in all_materials if name == matched_name)
            result = catalog_lookup(matched_cat, matched_name)
            if result.get("found"):
                logging.info(f"[fuzzy] '{material_name}' → '{matched_name}' (score={score})")
                result["fuzzy_corrected_from"] = material_name
                return result
    except ImportError:
        logging.warning("thefuzz not installed — fuzzy matching disabled")

    return {"found": False, "error": f"Material '{material_name}' no encontrado en ningún catálogo"}


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
        if not is_frentin_piece:
            total += raw_m2 * qty_in  # respect input quantity
        raw_details.append({
            "description": p.get("description", ""),
            "largo": largo,
            "dim2": dim2,
            "m2": round(raw_m2, 4) if not is_frentin_piece else 0,
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
        qty = pd.get("quantity", 1)

        if is_zocalo:
            label = f"{pd['largo']:.2f}ML X {pd['dim2']:.2f} ZOC"
        elif pd.get("_is_frentin"):
            # Faldón/frentín: solo se contabiliza como MO (armado × ml).
            # NO sumar m² al material. Render con ml para que el operador
            # sepa que no aporta al bruto material.
            label = f"{pd['largo']:.2f}ML FALDON"
        else:
            label = f"{desc} — {pd['largo']:.2f} x {pd['dim2']:.2f}"
            if pd["largo"] >= 3.0 and not is_edificio:
                label += " (SE REALIZA EN 2 TRAMOS)"

        m2_display = round(pd["m2"] * qty, 2)
        entry = {"label": label, "m2": m2_display}
        if qty > 1:
            entry["qty"] = qty
        formatted.append(entry)

    return {
        "ok": True,
        "pieces": formatted,
        "total_m2": total_m2,
    }


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

    client_name = input_data["client_name"]
    project = input_data.get("project", "")
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
            auto_pileta_count = sum(
                1 for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces)
                if any(kw in (p.get("description") or "").lower() for kw in ["pileta", "bacha", "lavatorio", "kitchenette", "c/pileta", "c/bacha"])
            )
            if auto_pileta_count > 1:
                pileta_qty = auto_pileta_count
                logging.info(f"Edificio guardrail: auto-detected {pileta_qty} piletas from piece descriptions")

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

    # 5. MO items
    mo_items = []

    # Pileta (supports quantity for edificios)
    if pileta:
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

    # Colocación
    if colocacion:
        sku = "COLOCACIONDEKTON/NEOLITH" if is_sint else "COLOCACION"
        price, base = _get_mo_price(sku)
        qty = max(total_m2, cfg("colocacion.min_quantity", 1.0))
        mo_items.append({"description": "Colocación", "quantity": round(qty, 2), "unit_price": price, "base_price": base, "total": round(price * qty)})

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

    # Toma de corriente — si algún zócalo tiene alto > 10cm O hay revestimiento de pared
    has_tall_zocalo = any(
        (p.get("alto") or 0) > cfg("measurements.tall_zocalo_threshold", 0.10)
        for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces)
    )
    has_revestimiento = any(
        "revestimiento" in (p.get("description") or "").lower()
        for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces)
    )
    # `tomas_qty` override: operador pide "Agujero de toma × N" en el brief.
    # Mantiene compatibilidad con el auto-detect de zócalo alto/revestimiento:
    # si no se pasa el override, se sigue aplicando la regla heurística.
    tomas_qty = input_data.get("tomas_qty")
    if tomas_qty and tomas_qty > 0:
        sku = "TOMASDEKTON/NEO" if is_sint else "TOMAS"
        price, base = _get_mo_price(sku)
        mo_items.append({
            "description": "Agujero toma corriente",
            "quantity": int(tomas_qty),
            "unit_price": price,
            "base_price": base,
            "total": round(price * int(tomas_qty)),
        })
    elif has_tall_zocalo or has_revestimiento:
        sku = "TOMASDEKTON/NEO" if is_sint else "TOMAS"
        price, base = _get_mo_price(sku)
        mo_items.append({"description": "Agujero toma corriente", "quantity": 1, "unit_price": price, "base_price": base, "total": price})

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
                original_total = item["total"]
                item["total"] = round(original_total / 1.05)
                item["unit_price"] = round(item["unit_price"] / 1.05)
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
        total_usd = material_total_net
    else:
        total_ars = total_mo_ars + total_sinks_ars + material_total_net
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
            if is_zocalo:
                label = f'{pd["largo"]:.2f}ML X {pd["dim2"]:.2f} ZOC'
            else:
                dim2_label = f'{pd["largo"]:.2f} × {pd["dim2"]:.2f}'
                label = f'{dim2_label} {pd["description"]}'
                # "SE REALIZA EN 2 TRAMOS" only for residential — edificios
                # already list many pieces by tipología, legend adds noise.
                if pd["largo"] >= 3.0 and not is_edificio:
                    label += " (SE REALIZA EN 2 TRAMOS)"
            # Mark rows whose m² came from operator-declared Planilla de
            # Cómputo. Renderer looks for the trailing '*' to apply footnote.
            if pd.get("override"):
                label = f"{label} *"
                has_m2_override = True
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
        sectors.append({"label": project or "Cocina", "pieces": piece_labels})

    # ── Delivery days: apply tier by m² only if range_enabled in config ──
    import re as _re_plazo
    default_days = cfg("delivery_days.default", 40)
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
        "project": project or "Cocina",
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
        "piece_details": piece_details,
        "mo_items": mo_items,
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
        "inglete": inglete,
        "pulido": pulido,
        "skip_flete": skip_flete,
        **({"warnings": warnings} if warnings else {}),
        **({"fuzzy_corrected_from": mat_result["fuzzy_corrected_from"]} if "fuzzy_corrected_from" in mat_result else {}),
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

    # Material header
    lines.append(f"**MATERIAL — {mat_name} — {mat_m2:.2f} m²**".replace(".", ","))
    lines.append("")
    lines.append("| Pieza | Medida | m² |")
    lines.append("|---|---|---|")
    for p in pieces:
        desc = p.get("description", "")
        largo = p.get("largo", 0)
        dim2 = p.get("dim2", p.get("prof", 0))
        m2 = p.get("m2", 0)
        lines.append(f"| {desc} | {largo} x {dim2} | {m2:.2f} |".replace(".", ","))
    lines.append(f"| **TOTAL** | | **{mat_m2:.2f} m²** |".replace(".", ","))
    lines.append("")

    # Precio
    lines.append("**Precio unitario:**")
    if currency == "USD":
        lines.append(f"- Sin IVA: USD {price_base:.0f} | Con IVA: {fmt_usd(price_unit)} | Total: {fmt_usd(mat_total_bruto)}")
    else:
        lines.append(f"- Con IVA: {fmt_ars(price_unit)} | Total: {fmt_ars(mat_total_bruto)}")
    lines.append("")

    # Merma
    if merma.get("aplica"):
        lines.append("**MERMA — APLICA**")
        lines.append(f"- {merma.get('motivo', '')}")
        if merma.get("sobrante_m2"):
            sob_m2 = merma["sobrante_m2"]
            sob_total = round(sob_m2 * price_unit)
            lines.append(f"- Sobrante disponible: {sob_m2:.2f} m² ({fmt_usd(sob_total) if currency == 'USD' else fmt_ars(sob_total)})".replace(".", ","))
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

    lines.append("**MANO DE OBRA**")
    if is_edificio:
        # Expanded format showing base price (sin IVA), ÷1.05 applied, and final total.
        # Flete row shows ✗ in the ÷1.05 column to make the rule explicit.
        lines.append("| Item | Cant | Base s/IVA | ÷1.05 | Total c/IVA |")
        lines.append("|---|---|---|---|---|")
        for mo in mo_items:
            qty = mo["quantity"]
            qty_str = f"{qty:.2f} m²".replace(".", ",") if isinstance(qty, float) and qty != int(qty) else str(int(qty))
            base = mo.get("base_price", 0)
            is_flete = "flete" in mo["description"].lower()
            div_mark = "—" if is_flete else "✓"
            lines.append(
                f"| {mo['description']} | {qty_str} | {fmt_ars(round(base))} | {div_mark} | {fmt_ars(mo['total'])} |"
            )
        if mo_discount_pct:
            lines.append(
                f"| **Descuento {mo_discount_pct}% sobre MO (excluye flete)** | | | | **-{fmt_ars(mo_discount_amount)}** |"
            )
        lines.append(f"| **TOTAL MO** | | | | **{fmt_ars(total_ars)}** |")
    else:
        lines.append("| Item | Cant | Precio c/IVA | Total |")
        lines.append("|---|---|---|---|")
        for mo in mo_items:
            qty = mo["quantity"]
            qty_str = f"{qty:.2f} m²".replace(".", ",") if isinstance(qty, float) and qty != int(qty) else str(int(qty))
            lines.append(f"| {mo['description']} | {qty_str} | {fmt_ars(mo['unit_price'])} | {fmt_ars(mo['total'])} |")
        lines.append(f"| **TOTAL MO** | | | **{fmt_ars(total_ars)}** |")
    lines.append("")

    # Grand total
    # Only mention "+ piletas" when there is an actual sink product line (ARS)
    # bundled into total_ars; otherwise it misleads the reader.
    lines.append("**GRAND TOTAL**")
    if currency == "USD" and total_usd:
        has_sink_product = bool(sinks) and any(
            (s.get("unit_price", 0) * s.get("quantity", 0)) > 0 for s in sinks
        )
        if has_sink_product:
            lines.append(f"{fmt_ars(total_ars)} mano de obra + piletas + {fmt_usd(total_usd)} material")
        else:
            lines.append(f"{fmt_ars(total_ars)} mano de obra + {fmt_usd(total_usd)} material")
    else:
        lines.append(f"{fmt_ars(total_ars)} total")
    lines.append("")

    # Warnings
    for w in warnings:
        lines.append(f"⚠️ {w}")

    lines.append("")
    lines.append("¿Confirmás para generar PDF y Excel?")

    return "\n".join(lines)
