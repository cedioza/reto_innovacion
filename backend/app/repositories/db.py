"""Capa de persistencia SQLModel: engine, sesiones e inicialización de tablas.

Decisiones de hackathon:
- El engine es un singleton perezoso a nivel de módulo (`get_engine`): se crea
  una sola vez, en la primera llamada, a partir de `settings.database_url`.
- Si `DATABASE_URL` no está configurada (entorno local sin Postgres), se cae a
  un archivo SQLite en `backend/app/data/local.db`. Es solo para desarrollo;
  en Dokploy siempre habrá un `DATABASE_URL` de Postgres real.
- El venv de este proyecto trae `psycopg` (v3), no `psycopg2`. Si la URL viene
  con el prefijo clásico `postgresql://` (el que entregan la mayoría de
  proveedores), se reescribe a `postgresql+psycopg://` para que SQLAlchemy use
  el driver correcto. Si ya viene con `postgresql+psycopg://` se deja igual.
- Las tablas se crean con `SQLModel.metadata.create_all` (`init_db`), sin
  Alembic: para un hackathon no se justifica el costo de migraciones
  versionadas; basta con crear el esquema si no existe al arrancar.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

_engine: Engine | None = None


def _normalize_database_url(url: str) -> str:
    """Reescribe `postgresql://` a `postgresql+psycopg://` (driver psycopg 3)."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _default_sqlite_url() -> str:
    """URL de fallback: SQLite en `backend/app/data/local.db`."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "local.db"
    return f"sqlite:///{db_path}"


def get_engine() -> Engine:
    """Devuelve el engine singleton, creándolo perezosamente si no existe."""
    global _engine
    if _engine is not None:
        return _engine

    database_url = settings.database_url
    if database_url:
        url = _normalize_database_url(database_url)
        _engine = create_engine(url)
    else:
        url = _default_sqlite_url()
        _engine = create_engine(url, connect_args={"check_same_thread": False})
    return _engine


def init_db(engine: Engine | None = None) -> None:
    """Crea las tablas registradas en `SQLModel.metadata` si no existen.

    Importa los módulos de modelos para que su metadata quede registrada
    antes de llamar a `create_all`.
    """
    from app.models import affiliate_record, application, channel, conversation  # noqa: F401

    SQLModel.metadata.create_all(engine or get_engine())


@contextmanager
def get_session(engine: Engine | None = None) -> Iterator[Session]:
    """Context manager que abre y cierra una sesión SQLModel."""
    session = Session(engine or get_engine())
    try:
        yield session
    finally:
        session.close()
