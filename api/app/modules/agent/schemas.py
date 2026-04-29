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
    # PR #19 — flag para mostrar badge OBRA en dashboard. Antes solo se
    # mostraba para quote_kind='building_parent' (edificios multi-material),
    # dejando los edificios single-material sin marca visible.
    is_building: Optional[bool] = False
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
    # PR #18 — expuestos al frontend para que ResumenObraCard y
    # EmailDraftCard rendericen. Antes quedaban en la DB pero el
    # endpoint /api/quotes/:id no los devolvía → cards invisibles.
    resumen_obra: Optional[dict] = None
    email_draft: Optional[dict] = None
    # PR #24 — PDF de Condiciones (solo edificios). Frontend lo muestra
    # como card debajo del PDF principal cuando is_building=True.
    condiciones_pdf: Optional[dict] = None
    # PR #400 — Payload crudo del POST /api/v1/quote (solo source="web").
    # El frontend lo usa para el botón "Copiar solicitud web" — dump literal
    # de lo que mandó el bot externo, útil para debug del bot vs backend.
    web_input: Optional[dict] = None
    # PR #442 — flag computado: True si el operador editó el quote
    # después de la última generación/regenerate del PDF. Frontend
    # muestra banner "PDF desactualizado · Regenerar" cuando se
    # cumple. Computado en `GET /quotes/{id}` desde change_history
    # vs updated_at — no es columna persistida.
    pdf_outdated: Optional[bool] = None
    pdf_generated_at: Optional[datetime] = None


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
    # PR #437 (P1.2) — delivery_days NO existe como columna en Quote;
    # vive solo en `quote_breakdown.delivery_days` (JSON). El endpoint
    # PATCH lo acepta y el handler lo persiste en el JSON. Sin esto,
    # el frontend no podía agregar EditableField de demora — el fix
    # del PR #436 (en `update_quote` del agent) cubría solo la ruta
    # de chat con Sonnet.
    delivery_days: Optional[str] = Field(None, max_length=200)


class DeriveMaterialRequest(BaseModel):
    """Create a new quote derived from an existing one with a different material.
    Copies client/project/pieces/options, recalculates everything from scratch."""
    material: str = Field(..., min_length=1, max_length=500)
    thickness_mm: Optional[int] = Field(None, ge=1, le=100)
