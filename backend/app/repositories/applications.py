"""Repositorio de solicitudes (`ConsentedApplication`) persistido vía SQLModel.

El documento completo (`ConsentedApplication`, schema Pydantic que circula
entre `services` y `api`) se guarda serializado en la columna `data`
(JSON/JSONB) de `ApplicationRecord`; `evidence_hash`, `handoff_token` y
`consent_timestamp` se desnormalizan como columnas propias porque ya se leen
o filtran por separado (`get_evidence_hash`, `find_by_token`).

`handoff_token` está indexado en el modelo (`ApplicationRecord`), así que
`find_by_token` hace una query (`select(...).where(...)`), no un scan en
memoria.

Nota sobre `save` y `finalize_by_token` (`app.services.consent`): el upsert
escribe tal cual lo que recibe, nunca recalcula nada. `finalize_by_token`
recupera el `evidence_hash` original antes de re-guardar (el hash es
evidencia de lo consentido, no del estado de la demo) y se lo pasa de vuelta
a `save`: el repositorio no tiene que preocuparse de preservarlo.

Decisión de hackathon: sin Alembic, el esquema se crea con
`SQLModel.metadata.create_all` (ver `app.repositories.db.init_db`).

El engine no se resuelve en `__init__` cuando no se pasa uno explícito: se
consulta `db.get_engine()` en cada operación (lazy), para no forzar la
creación del engine global (y su fallback a SQLite en disco) solo por
importar este módulo o instanciar el repositorio, p. ej. en tests.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, func
from sqlmodel import Session, select

from app.models.application import ApplicationRecord
from app.repositories import db
from app.schemas.conversation import ConsentedApplication

logger = logging.getLogger(__name__)


class ApplicationRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine

    def _resolve_engine(self) -> Engine:
        return self._engine or db.get_engine()

    def save(
        self,
        session_id: str,
        evidence_hash: str,
        application: ConsentedApplication,
    ) -> None:
        data = application.model_dump(mode="json")
        handoff_token = getattr(application, "handoff_token", None)
        consent_timestamp = application.consent_timestamp

        with Session(self._resolve_engine()) as db_session:
            record = db_session.get(ApplicationRecord, session_id)
            if record is None:
                record = ApplicationRecord(
                    session_id=session_id,
                    evidence_hash=evidence_hash,
                    handoff_token=handoff_token,
                    consent_timestamp=consent_timestamp,
                    data=data,
                )
            else:
                record.evidence_hash = evidence_hash
                record.handoff_token = handoff_token
                record.consent_timestamp = consent_timestamp
                record.data = data
            db_session.add(record)
            db_session.commit()

    def find(self, session_id: str) -> ConsentedApplication | None:
        with Session(self._resolve_engine()) as db_session:
            record = db_session.get(ApplicationRecord, session_id)
            if record is None:
                return None
            return ConsentedApplication.model_validate(record.data)

    def get_evidence_hash(self, session_id: str) -> str | None:
        with Session(self._resolve_engine()) as db_session:
            record = db_session.get(ApplicationRecord, session_id)
            if record is None:
                return None
            return record.evidence_hash

    def count(self) -> int:
        with Session(self._resolve_engine()) as db_session:
            statement = select(func.count()).select_from(ApplicationRecord)
            return db_session.exec(statement).one()

    def find_by_token(self, token: str) -> ConsentedApplication | None:
        with Session(self._resolve_engine()) as db_session:
            statement = select(ApplicationRecord).where(
                ApplicationRecord.handoff_token == token
            )
            record = db_session.exec(statement).first()
            if record is None:
                return None
            return ConsentedApplication.model_validate(record.data)

    def list_all(self) -> list[ConsentedApplication]:
        """Devuelve todas las solicitudes, más recientes primero.

        Escaneo completo de la tabla `solicitudes` (plan G4, Fase 2: vista de
        clientes/búsqueda): aceptable a escala hackathon, no es un patrón de
        producción. Una fila cuyo `data` no valide como `ConsentedApplication`
        se salta con un warning, en vez de romper el listado completo.
        """
        statement = select(ApplicationRecord).order_by(
            ApplicationRecord.created_at.desc()
        )
        with Session(self._resolve_engine()) as db_session:
            records = db_session.exec(statement).all()

        applications: list[ConsentedApplication] = []
        for record in records:
            try:
                application = ConsentedApplication.model_validate(record.data)
            except Exception:  # noqa: BLE001 - dato corrupto, se salta y se loguea
                logger.warning(
                    "fila corrupta en solicitudes, se omite session_id=%s",
                    record.session_id,
                )
                continue
            applications.append(application)
        return applications
