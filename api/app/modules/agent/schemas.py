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
    created_at: datetime

    class Config:
        from_attributes = True


class QuoteDetailResponse(QuoteListResponse):
    messages: list

    class Config:
        from_attributes = True


class QuoteStatusUpdate(BaseModel):
    status: QuoteStatus
