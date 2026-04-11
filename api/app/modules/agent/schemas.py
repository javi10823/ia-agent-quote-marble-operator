from pydantic import BaseModel, Field
from typing import Optional, Union, Literal
from datetime import datetime
from app.models.quote import QuoteStatus


class SinkTypeSchema(BaseModel):
    """Tipo de bacha: simple/doble + montaje arriba/abajo."""
    basin_count: Literal["simple", "doble"]
    mount_type: Literal["arriba", "abajo"]


class QuoteListResponse(BaseModel):
    id: str
    client_name: str
    project: str
    material: Optional[str]
    total_ars: Optional[float]
    total_usd: Optional[float]
    status: QuoteStatus
    pdf_url: Optional[str]
    excel_url: Optional[str]
    drive_url: Optional[str]
    drive_pdf_url: Optional[str] = None
    drive_excel_url: Optional[str] = None
    parent_quote_id: Optional[str] = None
    quote_kind: Optional[str] = "standard"
    comparison_group_id: Optional[str] = None
    source: Optional[str] = "operator"
    is_read: bool = True
    client_phone: Optional[str] = None
    client_email: Optional[str] = None
    localidad: Optional[str] = None
    colocacion: Optional[bool] = None
    pileta: Optional[str] = None
    sink_type: Optional[SinkTypeSchema] = None
    anafe: Optional[bool] = None
    pieces: Optional[list] = None
    conversation_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuoteDetailResponse(QuoteListResponse):
    messages: list
    quote_breakdown: Optional[dict] = None
    source_files: Optional[list] = None


class QuoteCompareItem(BaseModel):
    id: str
    material: Optional[str]
    total_ars: Optional[float]
    total_usd: Optional[float]
    status: QuoteStatus
    pdf_url: Optional[str]
    excel_url: Optional[str] = None
    drive_url: Optional[str] = None
    quote_breakdown: Optional[dict] = None

    model_config = {"from_attributes": True}


class QuoteCompareResponse(BaseModel):
    parent_id: str
    client_name: str
    project: str
    quotes: list[QuoteCompareItem]


class CreateQuoteRequest(BaseModel):
    status: Optional[QuoteStatus] = None


class QuoteStatusUpdate(BaseModel):
    status: QuoteStatus


class PatchPieceInput(BaseModel):
    description: str = Field(..., max_length=200)
    largo: float = Field(..., gt=0, le=20)
    prof: Optional[float] = Field(None, gt=0, le=5)
    alto: Optional[float] = Field(None, gt=0, le=5)


class QuotePatchRequest(BaseModel):
    status: Optional[QuoteStatus] = None
    client_name: Optional[str] = Field(None, max_length=500)
    client_phone: Optional[str] = Field(None, max_length=100)
    client_email: Optional[str] = Field(None, max_length=200)
    project: Optional[str] = Field(None, max_length=500)
    material: Optional[Union[str, list[str]]] = None
    pieces: Optional[list[PatchPieceInput]] = None
    localidad: Optional[str] = Field(None, max_length=200)
    colocacion: Optional[bool] = None
    pileta: Optional[str] = Field(None, max_length=50)
    sink_type: Optional[SinkTypeSchema] = None
    anafe: Optional[bool] = None
    conversation_id: Optional[str] = Field(None, max_length=100)
    origin: Optional[str] = Field(None, pattern=r"^(web|operator)$")
    notes: Optional[str] = None
    parent_quote_id: Optional[str] = Field(None, max_length=200)


class DeriveMaterialRequest(BaseModel):
    """Create a new quote derived from an existing one with a different material.
    Copies client/project/pieces/options, recalculates everything from scratch."""
    material: str = Field(..., min_length=1, max_length=500)
    thickness_mm: Optional[int] = Field(None, ge=1, le=100)
