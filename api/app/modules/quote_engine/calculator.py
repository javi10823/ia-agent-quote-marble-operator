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

        # Filter out LEATHER variants unless explicitly requested
        input_lower = material_name.lower()
        has_leather = "leather" in input_lower
        filtered = [(n, c) for n, c in all_materials if has_leather or "leather" not in n.lower()]
        names = [m[0] for m in (filtered if filtered else all_materials)]
        match = fuzz_process.extractOne(material_name, names, score_cutoff=70)

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
        raw_m2 = largo * dim2
        total += raw_m2
        raw_details.append({
            "description": p.get("description", ""),
            "largo": largo,
            "dim2": dim2,
            "m2": round(raw_m2, 4),
        })
    # Group identical pieces by description+dimensions
    details = []
    seen = {}
    for d in raw_details:
        key = f'{d["largo"]:.4f}_{d["dim2"]:.4f}_{d["description"]}'
        if key in seen:
            seen[key]["quantity"] += 1
        else:
            entry = {**d, "quantity": 1}
            seen[key] = entry
            details.append(entry)
    return round(total, 2), details


def list_pieces(pieces: list) -> dict:
    """Format pieces for Paso 1 display: correct labels + total m² (deterministic).

    Returns structured data that the agent must use verbatim in Paso 1.
    Zócalos use "ml" format, mesadas use "largo × prof", >3m gets "2 TRAMOS".
    """
    total_m2, piece_details = calculate_m2(
        [p if isinstance(p, dict) else p for p in pieces]
    )

    formatted = []
    for pd in piece_details:
        desc = pd.get("description", "")
        desc_lower = desc.lower()
        is_zocalo = "zócalo" in desc_lower or "zocalo" in desc_lower
        qty = pd.get("quantity", 1)

        if is_zocalo:
            label = f"{pd['largo']:.2f}ML X {pd['dim2']:.2f} ZOC"
        else:
            label = f"{desc} — {pd['largo']:.2f} x {pd['dim2']:.2f}"
            if pd["largo"] >= 3.0:
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


def calculate_merma(m2_needed: float, material_type: str) -> dict:
    """Calculate merma for synthetic materials."""
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
    frentin = input_data.get("frentin", False)
    inglete = input_data.get("inglete", False)
    pulido = input_data.get("pulido", False)
    plazo = input_data["plazo"]
    discount_pct = input_data.get("discount_pct", 0)

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
    merma = calculate_merma(total_m2, mat_result.get("name", material_name))

    # 4. Material total
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

    # Anafe
    if anafe:
        sku = "ANAFEDEKTON/NEOLITH" if is_sint else "ANAFE"
        price, base = _get_mo_price(sku)
        mo_items.append({"description": "Agujero anafe", "quantity": 1, "unit_price": price, "base_price": base, "total": price})

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
            if is_edificio:
                physical_pieces = [p for p in (pp if isinstance(pp, dict) else pp.model_dump() for pp in pieces)
                                   if not any(kw in (p.get("description") or "").lower() for kw in ["faldón", "faldon", "frentín", "frentin"])]
                num_pieces = len(physical_pieces)
                _per_trip = cfg("building.flete_mesadas_per_trip", 8)
                flete_qty = math.ceil(num_pieces / _per_trip)
                flete_qty = max(1, flete_qty)
                logging.info(f"Edificio flete: {num_pieces} piezas físicas ÷ {_per_trip} = {flete_qty} fletes")
            else:
                flete_qty = 1
            mo_items.append({"description": f"Flete + toma medidas {localidad}", "quantity": flete_qty, "unit_price": flete_price, "base_price": flete_base, "total": round(flete_price * flete_qty)})

            # Pulido de cantos extra: if zone has pulido_extra=true AND colocación is on
            if colocacion and flete_result.get("pulido_extra", False):
                pulido_extra_price = round(flete_price / 2)
                pulido_extra_base = round(flete_base / 2)
                mo_items.append({"description": "Pulido de cantos (colocación fuera de zona)", "quantity": 1, "unit_price": pulido_extra_price, "base_price": pulido_extra_base, "total": pulido_extra_price})
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
    if has_tall_zocalo or has_revestimiento:
        sku = "TOMASDEKTON/NEO" if is_sint else "TOMAS"
        price, base = _get_mo_price(sku)
        mo_items.append({"description": "Agujero toma corriente", "quantity": 1, "unit_price": price, "base_price": base, "total": price})

    # Sink product (physical sink, not just labor)
    sinks = []
    if pileta == "empotrada_johnson":
        sink_result = None
        if pileta_sku:
            # Specific model requested
            sink_result = catalog_lookup("sinks", pileta_sku)
        if not sink_result or not sink_result.get("found"):
            # Try default Johnson search
            sink_result = catalog_lookup("sinks", "QUADRAQ71A")
        if sink_result and sink_result.get("found"):
            sink_price = sink_result.get("price_ars", 0)
            sinks.append({
                "name": sink_result.get("name", "Pileta Johnson"),
                "quantity": 1,
                "unit_price": sink_price,
            })
            logging.info(f"Added sink product: {sink_result.get('name')} @ ${sink_price}")

    # Edificio: MO ÷1.05 (except flete)
    if is_edificio:
        for item in mo_items:
            if "flete" not in item["description"].lower():
                original_total = item["total"]
                item["total"] = round(original_total / 1.05)
                item["unit_price"] = round(item["unit_price"] / 1.05)
                item["edificio_discount"] = True
        logging.info(f"Edificio MO ÷1.05 applied (except flete)")

    # Totals
    total_sinks_ars = sum(s["unit_price"] * s["quantity"] for s in sinks)
    total_mo_ars = sum(item["total"] for item in mo_items)

    if currency == "USD":
        total_ars = total_mo_ars + total_sinks_ars
        total_usd = material_total_net
    else:
        total_ars = total_mo_ars + total_sinks_ars + material_total_net
        total_usd = 0

    # Build sectors for document generation (group identical pieces)
    sectors = []
    raw_labels = []
    for pd in piece_details:
        if pd["m2"] > 0:
            desc_lower = (pd["description"] or "").lower()
            is_zocalo = "zócalo" in desc_lower or "zocalo" in desc_lower
            if is_zocalo:
                label = f'{pd["largo"]:.2f}ML X {pd["dim2"]:.2f} ZOC'
            else:
                dim2_label = f'{pd["largo"]:.2f} × {pd["dim2"]:.2f}'
                label = f'{dim2_label} {pd["description"]}'
                if pd["largo"] >= 3.0:
                    label += " (SE REALIZA EN 2 TRAMOS)"
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

    # ── Delivery days: apply tier by m² if plazo matches the config default (numeric) ──
    import re as _re_plazo
    default_days = cfg("delivery_days.default", 40)
    _plazo_match = _re_plazo.search(r'(\d+)', plazo or "")
    _plazo_days = int(_plazo_match.group(1)) if _plazo_match else None
    if _plazo_days == default_days:
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
        "merma": merma,
        "piece_details": piece_details,
        "mo_items": mo_items,
        "total_ars": total_ars,
        "total_usd": total_usd,
        "sectors": sectors,
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
