"""Pure Python quote calculator — no LLM, deterministic, fast."""

import math
import logging
from datetime import datetime

from app.modules.agent.tools.catalog_tool import catalog_lookup

# Materials that are sinterized (12mm) — use different MO SKUs
SINTERIZADOS = {"dekton", "neolith", "puraprima", "laminatto"}

# Synthetic materials that have merma
SINTETICOS = {"silestone", "dekton", "neolith", "puraprima", "purastone", "laminatto"}

# Merma reference sizes (m2)
MERMA_MEDIA_PLACA = {"silestone"}  # reference = half plate 2.10 m2
MERMA_PLACA_ENTERA = {"purastone", "puraprima", "dekton", "neolith", "laminatto"}

# Plate sizes
PLATE_SIZES = {
    "silestone": 4.20,    # 3.00 × 1.40
    "purastone": 4.20,    # 3.00 × 1.40
    "dekton": 5.12,       # 3.20 × 1.60
    "neolith": 5.12,      # 3.20 × 1.60
    "puraprima": 5.12,    # 3.20 × 1.60
    "laminatto": 5.12,    # 3.20 × 1.60
}

# Common zone name → SKU mapping
ZONE_SKUS = {
    "rosario": "ENVIOROS",
    "funes": "ENVFUNES",
    "perez": "ENVPEREZ",
    "san lorenzo": "ENVSANLORENZO",
    "villa gobernador galvez": "ENVVILLA",
    "roldan": "FLETEROLD",
    "ibarlucea": "ENVIBAR",
    "soldini": "ENVSOLDINI",
    "ricardone": "ENVRICARDONE",
    "san nicolas": "ENVSANNICO",
    "alvear": "ENVALVEAR",
    "arroyo seco": "ENVARROYO",
    "galvez": "FLEGALVEZ",
    "carcarana": "FLECARRERAS",
    "andino": "FLETEAND",
    "victoria": "ENVVICTORIA",
    "san martin": "ENVSANMARTIN",
    "general lagos": "ENVGRAL",
    "hudsson": "ENVHUD",
    "las parejas": "ENVLASPAREJAS",
    "maciel": "ENVMACIEL",
    "carmen": "ENVCARMEN",
    "baigorria": "ENVBAI",
    "bermudez": "ENVBER",
    "salto grande": "ENVSALTOGDE",
    "esther": "ENVESTHER",
    "aldao": "ENVALDAO",
}


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


def _find_material(material_name: str) -> dict:
    """Search for material across all catalogs."""
    catalogs = [
        "materials-silestone", "materials-purastone",
        "materials-granito-nacional", "materials-granito-importado",
        "materials-dekton", "materials-neolith",
        "materials-marmol", "materials-puraprima", "materials-laminatto",
    ]
    for cat in catalogs:
        result = catalog_lookup(cat, material_name)
        if result.get("found"):
            return result
    return {"found": False, "error": f"Material '{material_name}' no encontrado en ningún catálogo"}


def _find_flete(localidad: str) -> dict:
    """Find flete price for a zone."""
    zone_key = localidad.lower().strip()
    sku = ZONE_SKUS.get(zone_key)
    if sku:
        return catalog_lookup("delivery-zones", sku)
    # Try direct SKU lookup
    result = catalog_lookup("delivery-zones", f"ENVIO{zone_key.upper()[:3]}")
    if result.get("found"):
        return result
    # Try partial match
    result = catalog_lookup("delivery-zones", zone_key.upper())
    if result.get("found"):
        return result
    return {"found": False, "error": f"Zona '{localidad}' no encontrada en delivery-zones"}


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
    details = []
    for p in pieces:
        largo = p.get("largo", 0)
        dim2 = p.get("prof") or p.get("alto") or 0
        raw_m2 = largo * dim2
        total += raw_m2
        details.append({
            "description": p.get("description", ""),
            "largo": largo,
            "dim2": dim2,
            "m2": round(raw_m2, 4),  # display only
        })
    return round(total, 2), details


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

    if desperdicio < 1.0:
        return {
            "aplica": False,
            "desperdicio": desperdicio,
            "sobrante_m2": 0,
            "motivo": f"Desperdicio {desperdicio} m² < 1.0 → sin sobrante (ref: {ref_label})",
        }
    else:
        sobrante = round(desperdicio / 2, 2)
        return {
            "aplica": True,
            "desperdicio": desperdicio,
            "sobrante_m2": sobrante,
            "motivo": f"Desperdicio {desperdicio} m² ≥ 1.0 → sobrante {sobrante} m² (ref: {ref_label})",
        }


def calculate_quote(input_data: dict) -> dict:
    """
    Calculate a complete quote from input data.
    Returns dict with all quote details, ready for document generation.
    """
    client_name = input_data["client_name"]
    project = input_data.get("project", "")
    material_name = input_data["material"]
    pieces = input_data["pieces"]
    localidad = input_data["localidad"]
    colocacion = input_data.get("colocacion", True)
    pileta = input_data.get("pileta")
    anafe = input_data.get("anafe", False)
    frentin = input_data.get("frentin", False)
    pulido = input_data.get("pulido", False)
    plazo = input_data["plazo"]
    discount_pct = input_data.get("discount_pct", 0)
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

    # Pileta
    if pileta:
        if pileta in ("empotrada_cliente", "empotrada_johnson"):
            sku = "PILETADEKTON/NEOLITH" if is_sint else "PEGADOPILETA"
            price, base = _get_mo_price(sku)
            mo_items.append({"description": "Agujero y pegado pileta", "quantity": 1, "unit_price": price, "base_price": base, "total": price})
        elif pileta == "apoyo":
            sku = "PILETAAPOYODEKTON/NEO" if is_sint else "AGUJEROAPOYO"
            price, base = _get_mo_price(sku)
            mo_items.append({"description": "Agujero pileta apoyo", "quantity": 1, "unit_price": price, "base_price": base, "total": price})

    # Anafe
    if anafe:
        sku = "ANAFEDEKTON/NEOLITH" if is_sint else "ANAFE"
        price, base = _get_mo_price(sku)
        mo_items.append({"description": "Agujero anafe", "quantity": 1, "unit_price": price, "base_price": base, "total": price})

    # Colocación
    if colocacion:
        sku = "COLOCACIONDEKTON/NEOLITH" if is_sint else "COLOCACION"
        price, base = _get_mo_price(sku)
        qty = max(total_m2, 1.0)
        mo_items.append({"description": "Colocación", "quantity": round(qty, 2), "unit_price": price, "base_price": base, "total": round(price * qty)})

    # Flete
    flete_result = _find_flete(localidad)
    if flete_result.get("found"):
        flete_price = flete_result.get("price_ars", 0)
        flete_base = flete_result.get("price_ars_base", 0)
        mo_items.append({"description": f"Flete + toma medidas {localidad}", "quantity": 1, "unit_price": flete_price, "base_price": flete_base, "total": flete_price})
    else:
        logging.warning(f"Flete not found for '{localidad}'")

    # Toma de corriente — si algún zócalo tiene alto > 10cm O hay revestimiento de pared
    has_tall_zocalo = any(
        (p.get("alto") or 0) > 0.10
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

    # Totals
    total_mo_ars = sum(item["total"] for item in mo_items)

    if currency == "USD":
        total_ars = total_mo_ars
        total_usd = material_total_net
    else:
        total_ars = total_mo_ars + material_total_net
        total_usd = 0

    # Build sectors for document generation
    sectors = []
    piece_labels = []
    for pd in piece_details:
        if pd["m2"] > 0:
            dim2_label = f'{pd["largo"]:.2f} × {pd["dim2"]:.2f}'
            piece_labels.append(f'{dim2_label} {pd["description"]}')
    if piece_labels:
        sectors.append({"label": project or "Cocina", "pieces": piece_labels})

    return {
        "ok": True,
        "client_name": client_name,
        "project": project or "Cocina",
        "date": date_str.replace("/", "."),
        "delivery_days": plazo,
        "material_name": mat_result.get("name", material_name),
        "material_type": mat_type,
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
        "sinks": [],
    }
