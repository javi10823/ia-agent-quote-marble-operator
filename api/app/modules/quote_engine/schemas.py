"""Pydantic schemas for the public quote API."""

from pydantic import BaseModel, Field
from typing import Optional, Union
from enum import Enum


class PiletaType(str, Enum):
    EMPOTRADA_CLIENTE = "empotrada_cliente"
    EMPOTRADA_JOHNSON = "empotrada_johnson"
    APOYO = "apoyo"


class PieceInput(BaseModel):
    description: str = Field(..., description="Ej: Mesada cocina, Zócalo trasero")
    largo: float = Field(..., gt=0, description="Largo en metros")
    prof: Optional[float] = Field(None, gt=0, description="Profundidad en metros (para mesadas)")
    alto: Optional[float] = Field(None, gt=0, description="Alto en metros (para zócalos/alzas)")


class QuoteInput(BaseModel):
    client_name: str = Field(..., min_length=1)
    project: str = Field(default="")
    material: Union[str, list[str]] = Field(..., description="Material o lista de materiales")
    pieces: Optional[list[PieceInput]] = Field(default=None, description="Piezas con medidas. Opcional si se adjunta plano.")
    localidad: str = Field(..., min_length=1, description="Zona de flete (ej: Rosario)")
    colocacion: bool = Field(default=True)
    pileta: Optional[PiletaType] = Field(default=None)
    anafe: bool = Field(default=False)
    frentin: bool = Field(default=False)
    pulido: bool = Field(default=False)
    plazo: str = Field(..., min_length=1, description="Ej: 30 días")
    discount_pct: float = Field(default=0, ge=0, le=100)
    date: Optional[str] = Field(default=None, description="DD/MM/YYYY o DD.MM.YYYY")
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
