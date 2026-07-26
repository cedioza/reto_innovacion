"""Repositorio de sesiones de canal y deduplicación de eventos de webhook.

Dos responsabilidades relacionadas que comparten el mismo repositorio porque
ambas son estado efímero de la integración con canales externos (WhatsApp,
Telegram, ...), persistido en Postgres/SQLite para sobrevivir reinicios:

- Mapear `(channel, user_ref) -> session_id`, reemplazando el dict en memoria
  que tenía `ChannelHandler` (se perdía en cada redeploy).
- Registrar eventos de webhook ya procesados (`event_id`) para no reenviar
  una respuesta duplicada si el proveedor reintenta la entrega.

Idempotencia atómica: `mark_event_processed` no hace un chequeo previo
("check-then-set") porque eso es una carrera bajo concurrencia (dos requests
casi simultáneas podrían leer "no procesado" antes de que ninguna alcance a
insertar). En su lugar se intenta el INSERT directamente y se captura
`IntegrityError` por violación de la PK (`event_id` duplicado): si falla, el
evento ya estaba marcado y la operación es un no-op (rollback + `False`).

El engine no se resuelve en `__init__` cuando no se pasa uno explícito: igual
que en `ConversationRepository`, se consulta `db.get_engine()` en cada
operación (lazy) para no forzar la creación del engine global solo por
instanciar el repositorio.
"""

from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models.channel import ChannelSessionRecord, ProcessedEventRecord
from app.repositories import db


class ChannelSessionRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine

    def _resolve_engine(self) -> Engine:
        return self._engine or db.get_engine()

    def find(self, channel: str, user_ref: str) -> str | None:
        with Session(self._resolve_engine()) as db_session:
            record = db_session.get(ChannelSessionRecord, (channel, user_ref))
            if record is None:
                return None
            return record.session_id

    def save(self, channel: str, user_ref: str, session_id: str) -> None:
        with Session(self._resolve_engine()) as db_session:
            record = db_session.get(ChannelSessionRecord, (channel, user_ref))
            if record is None:
                record = ChannelSessionRecord(
                    channel=channel,
                    user_ref=user_ref,
                    session_id=session_id,
                )
            else:
                record.session_id = session_id
            db_session.add(record)
            db_session.commit()

    def is_event_processed(self, event_id: str) -> bool:
        with Session(self._resolve_engine()) as db_session:
            statement = select(ProcessedEventRecord).where(
                ProcessedEventRecord.event_id == event_id
            )
            return db_session.exec(statement).first() is not None

    def mark_event_processed(self, event_id: str) -> bool:
        with Session(self._resolve_engine()) as db_session:
            db_session.add(ProcessedEventRecord(event_id=event_id))
            try:
                db_session.commit()
            except IntegrityError:
                db_session.rollback()
                return False
            return True
