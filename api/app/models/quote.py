import enum
from datetime import datetime
from sqlalchemy import String, Float, DateTime, JSON, Enum, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    SENT = "sent"


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(500))
    project: Mapped[str] = mapped_column(String(500))
    material: Mapped[str | None] = mapped_column(String(500), nullable=True)
    total_ars: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus), default=QuoteStatus.DRAFT
    )

    # Parent quote (for multi-material — links to the quote with the chat history)
    parent_quote_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # File URLs
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    excel_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    drive_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Full chat history as JSON array
    messages: Mapped[list] = mapped_column(JSON, default=list)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
