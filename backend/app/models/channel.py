"""Modelos SQLModel para el mapeo de canales (`sesiones_canal`) y la
deduplicación de eventos entrantes de webhooks (`eventos_procesados`).

No se usa `from __future__ import annotations`: ver nota en `conversation.py`.
"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class ChannelSessionRecord(SQLModel, table=True):
    """Asocia un usuario de un canal externo (WhatsApp, Telegram, ...) con su
    `session_id` de conversación. Clave primaria compuesta (channel, user_ref).
    """

    __tablename__ = "sesiones_canal"

    channel: str = Field(primary_key=True)
    user_ref: str = Field(primary_key=True)
    session_id: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProcessedEventRecord(SQLModel, table=True):
    """Registro de eventos de webhook ya procesados, para evitar duplicados."""

    __tablename__ = "eventos_procesados"

    event_id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
