from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.quote import QuoteStatus


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
    parent_quote_id: Optional[str] = None
    source: Optional[str] = "operator"
    is_read: bool = True
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
    quote_breakdown: Optional[dict] = None

    model_config = {"from_attributes": True}


class QuoteCompareResponse(BaseModel):
    parent_id: str
    client_name: str
    project: str
    quotes: list[QuoteCompareItem]


class QuoteStatusUpdate(BaseModel):
    status: QuoteStatus
