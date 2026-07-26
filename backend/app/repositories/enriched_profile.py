"""Repositorio EAV de `perfil_enriquecido` persistido en Postgres/SQLite vía SQLModel.

Cada dato del perfil enriquecido se guarda como una fila independiente
(`session_id`/`serie`/`campo`/`valor`); no hay upsert: al leer, la última fila
insertada para un campo dado gana (se recorre en orden de `id` ascendente y se
sobrescribe en el dict de salida).

El engine no se resuelve en `__init__` cuando no se pasa uno explícito: se
consulta `db.get_engine()` en cada operación (lazy), para no forzar la
creación del engine global (y su fallback a SQLite en disco) solo por
importar este módulo o instanciar el repositorio, p. ej. en tests.
"""

from __future__ import annotations

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.models.enriched_field import EnrichedFieldRecord
from app.repositories import db


class EnrichedProfileRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine

    def _resolve_engine(self) -> Engine:
        return self._engine or db.get_engine()

    def add(self, session_id: str, serie: str | None, campo: str, valor: str) -> None:
        record = EnrichedFieldRecord(
            session_id=session_id,
            serie=serie,
            campo=campo,
            valor=valor,
        )
        with Session(self._resolve_engine()) as db_session:
            db_session.add(record)
            db_session.commit()

    def fields_for_session(self, session_id: str) -> dict[str, str]:
        statement = (
            select(EnrichedFieldRecord)
            .where(EnrichedFieldRecord.session_id == session_id)
            .order_by(EnrichedFieldRecord.id.asc())
        )
        with Session(self._resolve_engine()) as db_session:
            records = db_session.exec(statement).all()
        return {record.campo: record.valor for record in records}

    def fields_for_serie(self, serie: str) -> dict[str, str]:
        statement = (
            select(EnrichedFieldRecord)
            .where(EnrichedFieldRecord.serie == serie)
            .order_by(EnrichedFieldRecord.id.asc())
        )
        with Session(self._resolve_engine()) as db_session:
            records = db_session.exec(statement).all()
        return {record.campo: record.valor for record in records}
