import enum
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, JSON, Enum, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.core.database import Base


class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    VALIDATED = "validated"
    SENT = "sent"


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(500))
    project: Mapped[str] = mapped_column(String(500))
    material: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_ars: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus), default=QuoteStatus.DRAFT
    )

    # Parent quote (for multi-material — links to the quote with the chat history)
    parent_quote_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Quote kind: standard | building_parent | building_child_material | variant_option
    quote_kind: Mapped[str | None] = mapped_column(String(30), nullable=True, default="standard")

    # Comparison group for variant_option quotes (same work, different materials)
    comparison_group_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Source: "operator" (chat with Valentina) or "web" (external API)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True, default="operator")

    # Read status: False for new web quotes, True for operator-created or already opened
    is_read: Mapped[bool] = mapped_column(Boolean, default=True)

    # File URLs
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    excel_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    drive_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    drive_file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    drive_pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    drive_excel_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Structured quote breakdown (pieces, MO, merma, discount)
    quote_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Client contact info
    client_phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Quote details
    localidad: Mapped[str | None] = mapped_column(String(200), nullable=True)
    colocacion: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    pileta: Mapped[str | None] = mapped_column(String(50), nullable=True)
    anafe: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    sink_type: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_building: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)

    # Raw pieces input (as submitted, before calculation)
    pieces: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Conversation link (web sessions)
    conversation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Notes from web client for the operator
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source files (plans, images uploaded by operator)
    source_files: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Change history — log of modifications in patch mode
    change_history: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # Full chat history as JSON array
    messages: Mapped[list] = mapped_column(JSON, default=list)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Optimistic locking — increment on each update to detect concurrent edits
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default="1")
