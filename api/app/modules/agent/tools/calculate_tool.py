"""
Calculate tool — helper functions for quote calculations.
These are exposed to Claude as context, not as a tool call,
since Claude does the calculation logic directly using the rules in CONTEXT.md.

This module provides utility functions that can be called by the document_tool
when generating the final quote structure.
"""
import math
from typing import Optional


def apply_iva(price: float) -> float:
    """Apply 21% IVA to a price."""
    return price * 1.21


def price_usd_with_iva(price_usd_base: float) -> int:
    """Truncate USD price with IVA to integer (floor)."""
    return math.floor(price_usd_base * 1.21)


def price_ars_with_iva(price_ars_base: float) -> int:
    """Round ARS price with IVA."""
    return round(price_ars_base * 1.21)


def apply_discount(price: float, discount_pct: float) -> float:
    """Apply discount percentage. NEVER divide — always multiply."""
    return price * (1 - discount_pct / 100)


def calculate_merma(m2_needed: float, m2_reference: float) -> dict:
    """
    Calculate waste/surplus for synthetic materials.
    Returns: desperdicio, has_sobrante, sobrante_m2
    """
    desperdicio = m2_reference - m2_needed
    has_sobrante = desperdicio >= 1.0
    sobrante_m2 = desperdicio / 2 if has_sobrante else 0

    return {
        "desperdicio": round(desperdicio, 4),
        "has_sobrante": has_sobrante,
        "sobrante_m2": round(sobrante_m2, 4),
        "cobrar_m2": round(m2_needed + sobrante_m2, 2),
    }


def calculate_colocacion(total_m2: float) -> float:
    """Minimum 1m² for colocacion."""
    return max(total_m2, 1.0)


def calculate_flete_edificio(physical_pieces: int) -> int:
    """Ceiling division: ceil(pieces / 6)."""
    return math.ceil(physical_pieces / 6)


def format_ars(amount: float) -> str:
    """Format ARS amount for display."""
    return f"${amount:,.0f}".replace(",", ".")


def format_usd(amount: float) -> str:
    """Format USD amount for display."""
    return f"USD {amount:,}"
