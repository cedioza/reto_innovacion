"""Modelo SQLModel para la tabla `solicitudes` (persistencia de solicitudes/handoff).

No se usa `from __future__ import annotations`: ver nota en `conversation.py`.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ApplicationRecord(SQLModel, table=True):
    """Solicitud generada al final del flujo de conversación."""

    __tablename__ = "solicitudes"

    session_id: str = Field(primary_key=True)
    evidence_hash: str
    handoff_token: Optional[str] = Field(default=None, index=True)
    consent_timestamp: str
    data: dict = Field(
        sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
