"""Pydantic schemas for the public quote API."""

from pydantic import BaseModel, Field
from typing import Optional, Union, Literal
from enum import Enum


class PiletaType(str, Enum):
    EMPOTRADA_CLIENTE = "empotrada_cliente"
    EMPOTRADA_JOHNSON = "empotrada_johnson"
    APOYO = "apoyo"


class SinkTypeInput(BaseModel):
    """Tipo de bacha: simple/doble + montaje arriba/abajo."""
    basin_count: Literal["simple", "doble"]
    mount_type: Literal["arriba", "abajo"]


class PieceInput(BaseModel):
    description: str = Field(..., max_length=200, description="Ej: Mesada cocina, Zócalo trasero")
    largo: float = Field(..., gt=0, le=20, description="Largo en metros (max 20m)")
    prof: Optional[float] = Field(None, gt=0, le=5, description="Profundidad en metros (max 5m)")
    alto: Optional[float] = Field(None, gt=0, le=5, description="Alto en metros (max 5m)")


class QuoteInput(BaseModel):
    client_name: str = Field(..., min_length=1, max_length=200)
    project: str = Field(default="", max_length=200)
    material: Union[str, list[str]] = Field(..., description="Material o lista de materiales")
    pieces: Optional[list[PieceInput]] = Field(default=None, description="Piezas con medidas. Opcional si se adjunta plano.")
    localidad: str = Field(..., min_length=1, max_length=100, description="Zona de flete (ej: Rosario)")
    colocacion: bool = Field(default=True)
    pileta: Optional[PiletaType] = Field(default=None)
    sink_type: Optional[SinkTypeInput] = Field(default=None, description="Tipo de bacha: basin_count (simple/doble), mount_type (arriba/abajo)")
    # PR #397 — SKU específico de pileta Johnson (ej: "LUXOR171", "ON30A").
    # Si se envía, se intenta matchear contra `sinks.json` y se agrega como
    # producto físico a la cotización (además del MO PEGADOPILETA). Si no
    # matchea, el quote se crea igual con warning. Si no se envía, el
    # comportamiento actual se mantiene (solo MO, sin producto).
    pileta_sku: Optional[str] = Field(default=None, max_length=64, description="SKU de pileta Johnson del catálogo (opcional)")
    anafe: bool = Field(default=False)
    frentin: bool = Field(default=False)
    pulido: bool = Field(default=False)
    skip_flete: bool = Field(default=False, description="True solo si el cliente retira el trabajo en fábrica")
    plazo: Optional[str] = Field(default=None, max_length=100, description="Ej: 30 días. Si no se envía, usa default de config.json")
    discount_pct: float = Field(default=0, ge=0, le=100)
    date: Optional[str] = Field(default=None, description="DD/MM/YYYY o DD.MM.YYYY")
    conversation: Optional[list[dict]] = Field(default=None, description="Chat history from web chatbot [{role, content}]")
    notes: Optional[str] = Field(default=None, description="Notas u observaciones del cliente para el operador")


class MOItemOutput(BaseModel):
    description: str
    quantity: float
    unit_price: int
    total: int


class MermaOutput(BaseModel):
    aplica: bool
    desperdicio: float = 0
    sobrante_m2: float = 0
    motivo: str = ""


class DiscountOutput(BaseModel):
    aplica: bool
    porcentaje: float = 0
    monto: float = 0


class QuoteResultItem(BaseModel):
    quote_id: str
    material: str
    material_m2: float
    material_price_unit: int
    material_currency: str
    material_total: int
    mo_items: list[MOItemOutput]
    total_ars: int
    total_usd: int
    merma: MermaOutput
    discount: DiscountOutput
    pdf_url: Optional[str] = None
    excel_url: Optional[str] = None
    drive_url: Optional[str] = None


class QuoteResponse(BaseModel):
    ok: bool
    quotes: list[QuoteResultItem] = []
    error: Optional[str] = None
