"""Repositorio de conversaciones persistido en Postgres/SQLite vía SQLModel.

El documento completo de la conversación (`ConversationResponse`, el schema
Pydantic que ya circula entre `services` y `api`) se guarda serializado en la
columna `data` (JSON/JSONB) de `ConversationRecord`; `estado` se desnormaliza
como columna indexada para futuras consultas por estado. `canal` no se setea
en esta fase (queda para cuando el orquestador de canales lo necesite) y se
conserva el valor existente en actualizaciones para no perder esa información
si otra parte del sistema ya la llenó.

Decisión de hackathon: sin Alembic, el esquema se crea con
`SQLModel.metadata.create_all` (ver `app.repositories.db.init_db`).

El engine no se resuelve en `__init__` cuando no se pasa uno explícito: se
consulta `db.get_engine()` en cada operación (lazy), para no forzar la
creación del engine global (y su fallback a SQLite en disco) solo por
importar este módulo o instanciar el repositorio, p. ej. en tests.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import Engine, func
from sqlmodel import Session, select

from app.models.conversation import ConversationRecord
from app.repositories import db
from app.schemas.conversation import ConversationResponse

logger = logging.getLogger(__name__)


class ConversationRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine

    def _resolve_engine(self) -> Engine:
        return self._engine or db.get_engine()

    def save(self, session_id: str, session: ConversationResponse) -> None:
        data = session.model_dump(mode="json")
        estado = session.state.value
        now = datetime.now(timezone.utc)

        with Session(self._resolve_engine()) as db_session:
            record = db_session.get(ConversationRecord, session_id)
            if record is None:
                record = ConversationRecord(
                    session_id=session_id,
                    canal=None,
                    estado=estado,
                    data=data,
                    created_at=now,
                    updated_at=now,
                )
            else:
                record.estado = estado
                record.data = data
                record.updated_at = now
            db_session.add(record)
            db_session.commit()

    def find(self, session_id: str) -> ConversationResponse | None:
        with Session(self._resolve_engine()) as db_session:
            record = db_session.get(ConversationRecord, session_id)
            if record is None:
                return None
            return ConversationResponse.model_validate(record.data)

    def delete(self, session_id: str) -> None:
        with Session(self._resolve_engine()) as db_session:
            record = db_session.get(ConversationRecord, session_id)
            if record is not None:
                db_session.delete(record)
                db_session.commit()

    def count(self) -> int:
        with Session(self._resolve_engine()) as db_session:
            statement = select(func.count()).select_from(ConversationRecord)
            return db_session.exec(statement).one()

    def list_all(self) -> list[dict]:
        """Devuelve todas las conversaciones, más recientes primero.

        Escaneo completo de la tabla `conversaciones` (plan G4, Fase 2: vista
        de clientes/búsqueda): aceptable a escala hackathon, no es un patrón
        de producción (falta paginación/índices para volúmenes grandes).

        Cada item es un dict `{"session", "canal", "created_at",
        "updated_at"}`, con `session` ya deserializada a `ConversationResponse`.
        Una fila cuyo `data` no valide como `ConversationResponse` (dato
        corrupto o de un shape viejo) se salta con un warning, en vez de
        romper el listado completo.
        """
        statement = select(ConversationRecord).order_by(
            ConversationRecord.updated_at.desc()
        )
        with Session(self._resolve_engine()) as db_session:
            records = db_session.exec(statement).all()

        items: list[dict] = []
        for record in records:
            try:
                session = ConversationResponse.model_validate(record.data)
            except Exception:  # noqa: BLE001 - dato corrupto, se salta y se loguea
                logger.warning(
                    "fila corrupta en conversaciones, se omite session_id=%s",
                    record.session_id,
                )
                continue
            items.append(
                {
                    "session": session,
                    "canal": record.canal,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
            )
        return items
