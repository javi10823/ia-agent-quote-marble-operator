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


# ─── Sprint 4 audit-trail-copy ──────────────────────────────────────────
# Response del endpoint `GET /api/quotes/{id}/audit-log`. Agrega eventos
# timeline + token usage + breakdown snapshot · wire-only sin migración.


class AuditLogEventItem(BaseModel):
    """Una fila de la timeline (audit_events row · subset relevante)."""
    created_at: datetime
    event_type: str
    source: str
    summary: str
    payload: dict
    success: bool
    error_message: Optional[str] = None
    elapsed_ms: Optional[int] = None
    turn_index: Optional[int] = None
    request_id: Optional[str] = None

    class Config:
        from_attributes = True


class AuditLogTokensSummary(BaseModel):
    """Suma de TokenUsage rows para este quote (todas las turnas)."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    iterations: int = 0
    models_used: list[str] = Field(default_factory=list)


class AuditLogToolUsage(BaseModel):
    """Agregación por tool_name (derivada de eventos agent.tool_result)."""
    tool_name: str
    count: int
    total_ms: int
    error_count: int = 0


class AuditLogMeta(BaseModel):
    """Cabecera con metadatos del quote."""
    quote_id: str
    status: str
    client_name: Optional[str] = None
    project: Optional[str] = None
    material: Optional[str] = None
    total_ars: Optional[float] = None
    total_usd: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class AuditLogResponse(BaseModel):
    """Response del endpoint `GET /api/quotes/{id}/audit-log`. Agrega 3
    tablas (audit_events + token_usage + Quote) en payload único para
    el botón "Copiar audit" del topbar y la página /audit.

    Cuando `full=false` (default), el array `events` se trunca a un
    máximo razonable (events_limit) y `events_truncated=True` para
    evitar payloads enormes en quotes con >150 eventos (debug activado).
    Errors se reportan siempre completos (sin trunc)."""
    meta: AuditLogMeta
    input_message: Optional[str] = None
    plan_files: list[str] = Field(default_factory=list)
    events: list[AuditLogEventItem]
    events_total: int
    events_truncated: bool = False
    chat_duration_ms: Optional[int] = None
    tokens: AuditLogTokensSummary
    tools_used: list[AuditLogToolUsage] = Field(default_factory=list)
    quote_breakdown: Optional[dict] = None
    errors: list[AuditLogEventItem] = Field(default_factory=list)


# ── PieceList REST · sub-PR sprint-4/despiece-real-wire ──────────────────
# Cierra el gap del frontend `useDespiece` hook que usaba 100% mocks. Sólo
# `listPiecesForQuote` se cablea real en este sub-PR; las 4 mutaciones
# (update/add/delete/regenerate) siguen mock-only hasta sub-PR siguiente
# que migre al modelo agentic via /chat (no CRUD plano).
# Shape mirroreado del frontend `web/src/lib/api/types.ts:172-212`.


class PieceOptionsSchema(BaseModel):
    pileta: Optional[dict] = None
    anafe: bool = False
    tomas: Optional[int] = None
    alzada: bool = False
    regrueso_mm: Optional[int] = None


class PieceSchema(BaseModel):
    id: str
    type: str  # "encimera" | "zocalo" | "alzada" | "frente" | "isla" | string
    label: str
    sublabel: Optional[str] = None
    width_mm: float
    depth_mm: float
    quantity: int = 1
    options: PieceOptionsSchema = Field(default_factory=PieceOptionsSchema)
    origin: str = "IA"  # "IA" | "EDITADO" | "AGREGADO_MANUAL"
    confidence: Optional[float] = None
    extracted_from: Optional[str] = None
    edited: bool = False


class PieceListResponse(BaseModel):
    pieces: list[PieceSchema] = Field(default_factory=list)
    status: str  # "pending" | "inferring" | "done" | "failed"
    timeline: list = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Calculation Response · sub-PR sprint-4/calculation-real-wire ──────────
# Cierra el gap del paso 4 que consumía 100% mocks. Solo `getCalculationForQuote`
# se cablea real en este sub-PR; `triggerCalculation` y `applyAutoFix` siguen
# mock-only hasta sub-PR siguiente (decisión: trigger ya está cubierto por
# agent loop · applyAutoFix es caso nicho mockup 08 patch error).
# Shape mirroreado del frontend `web/src/lib/api/types.ts:267-342` (CalcStatus,
# MaterialRow, LaborRowData, MermaSection, PiletaSection, FleteRow, GrandTotals,
# DatosPdfDefaults, ValentinaAdjustment, CalculationResult).


class AuditEntrySchema(BaseModel):
    kind: str  # "SOURCE" | "REGLA" | "CALC" | "IVA" | "SUMA"
    text: str


class MaterialRowSchema(BaseModel):
    label: str
    sub: Optional[str] = None
    qty: str
    unit: str
    total: str
    variant: Optional[str] = None  # "default" | "discount" | "subtotal"
    audit: Optional[list[AuditEntrySchema]] = None


class LaborRowDataSchema(BaseModel):
    sku: str
    label: str
    sub: Optional[str] = None
    qty: str
    basePrice: str
    iva: str
    total: str
    audit: Optional[list[AuditEntrySchema]] = None


class MermaSobranteToggleSchema(BaseModel):
    label: str
    defaultChecked: bool


class MermaErrorRowSchema(BaseModel):
    label: str
    detail: str
    fixLabel: str


class MermaSectionSchema(BaseModel):
    status: str  # "na" | "aplica" | "error"
    chipLabel: str
    sub: Optional[str] = None
    rows: Optional[list[MaterialRowSchema]] = None
    sobranteToggle: Optional[MermaSobranteToggleSchema] = None
    stockToggle: Optional[MermaSobranteToggleSchema] = None
    errorRow: Optional[MermaErrorRowSchema] = None


class PiletaSectionSchema(BaseModel):
    chipLabel: str
    variant: str  # "na" | "info"
    sub: Optional[str] = None


class FleteRowSchema(BaseModel):
    zona: str
    qty: str
    basePrice: str
    total: str
    audit: Optional[list[AuditEntrySchema]] = None


class GrandTotalsCurrencySchema(BaseModel):
    value: str
    meta: str


class GrandTotalsSchema(BaseModel):
    ars: GrandTotalsCurrencySchema
    usd: GrandTotalsCurrencySchema
    warnDetail: Optional[str] = None


class DatosPdfDefaultsSchema(BaseModel):
    plazo: str
    anticipoPct: str
    saldo: str
    envio: str
    notas: str
    vigenciaDias: str


class ValentinaAdjustmentSchema(BaseModel):
    text: str


class CalculationResponse(BaseModel):
    quoteId: str
    status: str  # "pending" | "ok" | "error"
    bannerSummary: str
    bannerAdjustments: list[ValentinaAdjustmentSchema] = Field(default_factory=list)
    material: dict  # {"rows": list[MaterialRowSchema], "subtotal": str}
    merma: MermaSectionSchema
    labor: dict  # {"rows": list[LaborRowDataSchema], "subtotal": str}
    piletas: PiletaSectionSchema
    flete: FleteRowSchema
    totals: GrandTotalsSchema
    patchError: Optional[dict] = None
    datosPdf: DatosPdfDefaultsSchema
