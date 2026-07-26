"""Modelo SQLModel para la tabla `conversaciones` (persistencia de sesiones de chat).

No se usa `from __future__ import annotations` aquí: SQLModel con `table=True`
necesita resolver los tipos en tiempo de definición para construir las
columnas SQL, y los strings diferidos rompen esa resolución.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ConversationRecord(SQLModel, table=True):
    """Estado persistido de una conversación, indexado por `session_id`."""

    __tablename__ = "conversaciones"

    session_id: str = Field(primary_key=True)
    canal: Optional[str] = None
    estado: str = Field(index=True)
    data: dict = Field(
        sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
